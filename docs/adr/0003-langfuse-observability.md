# ADR-0003 — Observabilidad de producción con Langfuse (self-hosted)

**Estado**: Aceptada · **Fecha**: 2026-07-31 · **Milestone**: cross-cutting (no ligado a M3)

## Contexto

El pipeline de extracción (`backend/extraction/{pipeline,relations,attributes}.py`)
llama al LLM por un solo camino real hoy: los tres CLI
(`backend/extraction/{run,relations/run,attributes/run}.py`). Ningún módulo de
`backend/api/` invoca las pipelines de extracción todavía; cuando se expongan por
HTTP, heredarán la instrumentación sin cambios porque cuelga de las funciones de
entrada de las pipelines, no del transporte. Hoy la única
observabilidad de esas llamadas es un `log.debug("LLM cost=...")` en
`litellm_client.py` — sin trazas, sin agrupación por manuscrito, sin forma de ver
qué prompt/respuesta produjo un resultado concreto en una corrida real.

El eval harness (`eval/`) ya resuelve un problema distinto: reproducibilidad y
métricas contra datasets de oro, con sus propias respuestas LLM congeladas
(`eval/fixtures/llm-cache/`, ver ADR implícito en `docs/superpowers/plans/2026-07-30-eval-gates-no-skip.md`).
Este ADR no toca eso — cubre exclusivamente la depuración de corridas reales contra
manuscritos reales, que el eval harness nunca ejecuta.

Restricciones de la constitución del proyecto (`README.md` §2) relevantes aquí:

- **Principio IV — una sola puerta por dependencia externa.** `backend/llm/` es la
  única puerta al LLM; Langfuse no es un proveedor de LLM, pero sigue siendo una
  dependencia externa nueva y debe entrar por una puerta igual de estrecha, no
  esparcida como imports sueltos de `langfuse` por el código de aplicación.
- **Principio VI — idempotencia y cache por hash.** La clave de cache ya incluye
  `PROMPT_VERSION`/`SCHEMA_VERSION`/modelo; las trazas deben poder cruzarse con esos
  mismos campos sin duplicar ese mecanismo.

## Decisión

Instrumentar las tres corridas de extracción con **Langfuse self-hosted**, en dos
capas independientes que Langfuse anida automáticamente:

**1. Callback nativo de litellm — vive solo en `backend/llm/litellm_client.py`.**
Captura cada llamada cruda al LLM (system/user prompt, respuesta, coste, latencia,
modelo) sin que ningún otro módulo lo sepa. Cambio mínimo, contenido en el
constructor de `LiteLLMClient`: añadir `"langfuse_otel"` a
`litellm.success_callback`, condicionado a que Langfuse esté habilitado (ver
aislamiento de eval, abajo), más el puente `LANGFUSE_BASE_URL` →
`LANGFUSE_OTEL_HOST` que litellm necesita para no caer al SaaS público (ver
«Consecuencias»).

Cada llamada real a `complete_structured` pasa `metadata={"generation_name":
schema.__name__}` a `litellm.completion()`: litellm usa ese valor para nombrar el
span (en vez del genérico `raw_gen_ai_request` por defecto), así que en Langfuse se
distinguen por nombre las llamadas de extracción por escena (`SceneExtraction`,
`SceneRelations`, `SceneAttributes`) de las de resolución de personajes
(`MergeJudgement`) — sin cambiar la firma de `complete_structured`, porque `schema`
ya es un parámetro del protocolo (Principio IV intacto). Deliberadamente **no**
identifica por escena/manuscrito individual: eso sí exigiría pasar un identificador
nuevo (ver la alternativa rechazada más abajo). El
nombre importa: el callback `"langfuse"` de litellm es la integración legacy atada al
SDK `langfuse` 2.x y no funciona con el pin `langfuse>=3.0,<4` de este repo;
`"langfuse_otel"` es el logger compatible con v3. Se añade a la lista en vez de
reasignarla, para no pisar callbacks de terceros. Ese callback arrastra una dependencia
que litellm no declara fuera de su extra `proxy`: `pydantic-settings`, que
`litellm.integrations.otel` importa sin condicionar. Sin ella el callback no se
inicializa (error no bloqueante en el log) y esta capa no emite nada, así que
`pydantic-settings` es dependencia directa del proyecto.

**2. Módulo propio `backend/observability/tracing.py`** — la puerta única para
Langfuse fuera de `backend/llm/`, en el mismo espíritu que `backend/llm/` y
`backend/graph/`. Expone un único decorador `traced(name, metadata_fn=None)` que
envuelve `langfuse.observe` (o es un no-op si Langfuse está deshabilitado):
`name` es el nombre de la traza y `metadata_fn`, si se pasa, recibe los mismos
argumentos que la función decorada y su dict resultante se adjunta a la traza. Solo
`backend/extraction/pipeline.py`, `relations/pipeline.py` y `attributes/pipeline.py`
lo importan, decorando su función de entrada (`run_pipeline`,
`run_relations_pipeline`, `run_attributes_pipeline`) con
`@traced("extraction.characters", metadata_fn=_trace_metadata)` (y análogos).

**Captura de inputs desactivada (`capture_input=False`).** La captura automática de
`observe` serializa los kwargs tal cual, y las pipelines reciben el propio
`llm_client`, cuyo `__dict__` incluye `_api_key`: dejarla activa escribiría la clave
del proveedor en claro en Postgres, ClickHouse y los blobs de MinIO. `metadata_fn` ya
aporta lo que interesa de las entradas (`manuscript_id`, modelo, versiones), así que
capturarlas de nuevo sería riesgo sin beneficio.

**Anidado automático, sin tocar el protocolo.** El SDK de Langfuse propaga contexto
vía OpenTelemetry: si `run_pipeline` (decorado) llama internamente a
`complete_structured` (con el callback nativo activo), ambas capas aparecen anidadas
en una sola traza sin que `LLMClient.complete_structured` cambie de firma ni sepa
nada de Langfuse.

**Granularidad: una traza por manuscrito por pipeline.** Cada invocación de
`run_pipeline`/`run_relations_pipeline`/`run_attributes_pipeline` abre una traza de
nivel superior, taggeada con `manuscript_id`, nombre del pipeline, modelo,
`PROMPT_VERSION` y `SCHEMA_VERSION` — los mismos campos que ya componen la clave de
cache (Principio VI), así que una traza siempre es cruzable con la entrada de cache
que la originó (o la evitó).

**Aislamiento del eval harness (obligatorio, no opcional).** `eval/seed.py` fija
`LOOM_DISABLE_LANGFUSE=1` **antes** de instanciar `LiteLLMClient`, con una asignación
dura (`os.environ[...] = "1"`, no `setdefault`): sin importar qué haya en el entorno y
sin escape hatch. Es el único punto que hace falta, porque es el único del harness que
construye un `LiteLLMClient`: los runners de
`eval/{characters,relations,attributes}/runner.py` leen el grafo ya sembrado y nunca
llaman al LLM. `litellm_client.py` y
`backend/observability/tracing.py` respetan ese flag: ni el callback nativo ni
`traced` hacen nada si está a `"1"`. Así CI y los gates nunca dependen de que
Langfuse esté arriba, y una máquina de desarrollo con Langfuse configurado para
depurar producción no contamina sus corridas de eval con trazas.

**Fail-open, siempre.** Si Langfuse está caído o inalcanzable, ninguna extracción
real debe fallar por eso. La inicialización del callback y de `traced` va envuelta en
`try/except`, logueando en `WARNING` y continuando sin trazas. Se pierde
observabilidad de esa corrida, nunca el resultado en el grafo.

**Hosting: self-hosted, stack oficial completo, archivo de compose separado.** El
propio `docker-compose.yml` de Langfuse (Postgres + ClickHouse + Redis + MinIO + los
dos servicios de Langfuse) se referencia como `docker-compose.langfuse.yml`, opt-in:

```bash
docker compose -f docker-compose.yml -f docker-compose.langfuse.yml up
```

El `docker-compose.yml` del proyecto (Neo4j) no cambia. La mayoría de sesiones de
desarrollo y el CI nunca levantan Langfuse ni pagan su coste de RAM.

Todos los puertos del stack se publican en `127.0.0.1` (el upstream deja la UI en 3000
y MinIO en 9090 abiertos a la red; con las credenciales por defecto del archivo eso
expondría los prompts —fragmentos de novela— a cualquiera en la LAN), y cada línea de
puerto lleva un comentario inline con lo que sirve, igual que los de Neo4j en
`docker-compose.yml`.

**Variables de entorno nuevas** (documentadas en `.env.example`, sin valores por
defecto commiteados):

```bash
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=http://localhost:3000   # instancia self-hosted local (LANGFUSE_HOST es alias deprecado del SDK)
LOOM_DISABLE_LANGFUSE=1               # el eval harness lo fija por código, no por .env
```

## Alternativas consideradas

| Opción | Rechazada por |
|--------|--------------|
| **Langfuse Cloud** | El texto que pasa por el LLM son fragmentos de novelas, potencialmente manuscritos con derechos de terceros. Mandarlos a un SaaS externo exige revisar sus términos caso por caso; self-hosted lo evita de raíz. |
| **Solo callback nativo de litellm, sin `@observe`** | No agrupa las llamadas de un mismo manuscrito bajo una traza — que es justo el problema a resolver (depurar una extracción real que salió mal). Más barato de montar, pero no resuelve la motivación declarada. |
| **Instrumentar también el eval harness** | Mezclaría trazas de CI/gates con las de uso real y acoplaría la disponibilidad de los gates a que Langfuse esté arriba — contradice que el CI no dependa de secretos ni de servicios externos (ver `docs/superpowers/plans/2026-07-30-eval-gates-no-skip.md`). |
| **Meterlo dentro del alcance de M3** | Langfuse toca el gateway LLM completo (`backend/llm/`) y las tres pipelines de extracción, no el esquema de atributos. Es ortogonal a M3; merece su propio ADR y plan, igual que ADR-0002 (gateway LiteLLM) se escribió aparte de la spec de M1. |
| **Pasar el `trace_id`/`session_id` a mano por `LLMClient.complete_structured`** | Cambiaría la firma del protocolo por una preocupación de observabilidad, no de dominio. El SDK de Langfuse ya propaga contexto vía OpenTelemetry sin necesidad de tocarla. Distinto de nombrar por `schema.__name__` (sí adoptado, ver capa 1 arriba): eso reutiliza un parámetro que el protocolo ya tenía, no agrega uno nuevo para identificar la escena/manuscrito individual. |

## Consecuencias

**A favor**
- Cero cambios en `LLMClient`/`LiteLLMClient` más allá de registrar el callback: el
  protocolo del Principio IV queda intacto.
- Langfuse entra por una puerta tan estrecha como el LLM o el grafo
  (`backend/observability/tracing.py`), coherente con el resto de la arquitectura.
- El eval harness y CI quedan estructuralmente aislados de Langfuse: no hay forma de
  que una corrida de gates dependa de que el contenedor esté arriba.
- El contenido de las novelas nunca sale de la infraestructura propia.

**En contra / costes**
- ~6 contenedores nuevos (Postgres, ClickHouse, Redis, MinIO, 2 servicios Langfuse)
  cuando se decide observar una corrida real — coste de RAM/CPU real, mitigado por
  ser opt-in (archivo de compose separado).
- Un módulo nuevo (`backend/observability/`) y tres puntos de instrumentación
  (`pipeline.py`, `relations/pipeline.py`, `attributes/pipeline.py`) que mantener.
- El aislamiento de eval depende de que `eval/seed.py` fije el flag correctamente — un
  olvido ahí filtraría trazas de eval a Langfuse (mitigado: se cubre con tests
  unitarios en `tests/unit/test_eval_disables_langfuse.py`). Si en el futuro algún
  runner llega a construir un `LiteLLMClient`, tendrá que fijar el flag igual.
- La imagen de MinIO va pinneada por digest porque Chainguard no publica tags de
  versión estable. Chainguard poda digests viejos, así que ese pin caducará y habrá
  que refrescarlo a mano cada cierto tiempo (síntoma: `docker compose pull` falla con
  manifest desconocido para `cgr.dev/chainguard/minio@sha256:…`).
- `container_name` es global al daemon Docker, no al proyecto de compose: si el
  `docker-compose.yml` principal (Neo4j) ya está arriba desde el checkout normal del
  repo, correr `docker compose -f docker-compose.yml -f docker-compose.langfuse.yml up`
  desde un worktree falla (colisión de nombre de contenedor). Workaround verificado:
  levantar solo `-f docker-compose.langfuse.yml` cuando Neo4j ya esté arriba por
  separado.
- **litellm no conoce `LANGFUSE_BASE_URL` (puenteado en código).** El SDK
  `langfuse` (capa 2, `backend/observability/tracing.py`) prioriza
  `LANGFUSE_BASE_URL` sobre el `LANGFUSE_HOST` deprecado, pero el callback nativo
  `langfuse_otel` de litellm (capa 1) resuelve su host leyendo él mismo, de forma
  hardcodeada, `LANGFUSE_OTEL_HOST`/`LANGFUSE_HOST` (litellm/integrations/langfuse/
  langfuse_otel.py) — sin fallback a `LANGFUSE_BASE_URL`. Sin puentear esto, con
  solo `LANGFUSE_BASE_URL` fijada la capa 1 caería en silencio al SaaS público
  (`https://cloud.langfuse.com`), justo el escenario que este ADR rechazó (ver
  «Alternativas consideradas»). `LiteLLMClient.__init__` traduce
  `LANGFUSE_BASE_URL` → `LANGFUSE_OTEL_HOST` en el entorno del proceso (en memoria,
  no reescribe `.env`) antes de registrar el callback, solo si litellm no trae ya
  una de sus dos variables — así `.env` mantiene una sola variable de host y la
  limitación queda contenida en `backend/llm/`, que es su puerta única. Cubierto
  por `tests/unit/test_llm_client.py::test_langfuse_base_url_bridges_to_otel_host`.

## Notas

Plan de implementación:
`docs/superpowers/plans/2026-07-31-langfuse-observability.md`.
