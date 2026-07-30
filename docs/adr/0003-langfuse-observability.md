# ADR-0003 — Observabilidad de producción con Langfuse (self-hosted)

**Estado**: Aceptada · **Fecha**: 2026-07-31 · **Milestone**: cross-cutting (no ligado a M3)

## Contexto

El pipeline de extracción (`backend/extraction/{pipeline,relations,attributes}.py`)
llama al LLM en dos caminos reales: los endpoints FastAPI (`backend/api/routes_*`) y
los CLI (`backend/extraction/{run,relations/run,attributes/run}.py`). Hoy la única
observabilidad de esas llamadas es un `log.debug("LLM cost=...")` en
`litellm_client.py:105` — sin trazas, sin agrupación por manuscrito, sin forma de ver
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
modelo) sin que ningún otro módulo lo sepa. Cambio de una línea: registrar
`litellm.success_callback = ["langfuse"]` en el constructor de `LiteLLMClient`,
condicionado a que Langfuse esté habilitado (ver aislamiento de eval, abajo).

**2. Módulo propio `backend/observability/tracing.py`** — la puerta única para
Langfuse fuera de `backend/llm/`, en el mismo espíritu que `backend/llm/` y
`backend/graph/`. Expone un único decorador `traced(name: str)` que envuelve
`langfuse.observe` (o es un no-op si Langfuse está deshabilitado). Solo
`backend/extraction/pipeline.py`, `relations/pipeline.py` y `attributes/pipeline.py`
lo importan, decorando su función de entrada (`run_pipeline`,
`run_relations_pipeline`, `run_attributes_pipeline`) con
`@traced("extraction.characters")` (y análogos).

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

**Aislamiento del eval harness (obligatorio, no opcional).** `eval/seed.py` y los
runners de `eval/{characters,relations,attributes}/runner.py` fijan
`LOOM_DISABLE_LANGFUSE=1` **antes** de instanciar `LiteLLMClient`, sin importar si
`LANGFUSE_*` está configurado en el entorno. `litellm_client.py` y
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

**Variables de entorno nuevas** (documentadas en `.env.example`, sin valores por
defecto commiteados):

```bash
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=http://localhost:3000   # instancia self-hosted local
LOOM_DISABLE_LANGFUSE=1               # el eval harness lo fija por código, no por .env
```

## Alternativas consideradas

| Opción | Rechazada por |
|--------|--------------|
| **Langfuse Cloud** | El texto que pasa por el LLM son fragmentos de novelas, potencialmente manuscritos con derechos de terceros. Mandarlos a un SaaS externo exige revisar sus términos caso por caso; self-hosted lo evita de raíz. |
| **Solo callback nativo de litellm, sin `@observe`** | No agrupa las llamadas de un mismo manuscrito bajo una traza — que es justo el problema a resolver (depurar una extracción real que salió mal). Más barato de montar, pero no resuelve la motivación declarada. |
| **Instrumentar también el eval harness** | Mezclaría trazas de CI/gates con las de uso real y acoplaría la disponibilidad de los gates a que Langfuse esté arriba — contradice que el CI no dependa de secretos ni de servicios externos (ver `docs/superpowers/plans/2026-07-30-eval-gates-no-skip.md`). |
| **Meterlo dentro del alcance de M3** | Langfuse toca el gateway LLM completo (`backend/llm/`) y las tres pipelines de extracción, no el esquema de atributos. Es ortogonal a M3; merece su propio ADR y plan, igual que ADR-0002 (gateway LiteLLM) se escribió aparte de la spec de M1. |
| **Pasar el `trace_id`/`session_id` a mano por `LLMClient.complete_structured`** | Cambiaría la firma del protocolo por una preocupación de observabilidad, no de dominio. El SDK de Langfuse ya propaga contexto vía OpenTelemetry sin necesidad de tocarla. |

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
- El aislamiento de eval depende de que `eval/seed.py` y los tres runners fijen el
  flag correctamente — un olvido ahí filtraría trazas de eval a Langfuse (mitigado:
  se cubre con un test unitario que lo verifique, ver mini-plan).

## Notas

Plan de implementación:
`docs/superpowers/plans/2026-07-31-langfuse-observability.md`.
