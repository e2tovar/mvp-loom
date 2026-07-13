# Research — M1: Extracción y resolución de personajes + eval harness

**Feature**: `002-char-extraction-eval` · **Fecha**: 2026-06-10

Decisiones técnicas de la Fase 0. Cada una resuelve una incógnita del Technical
Context del [plan](./plan.md). Formato: decisión → racional → alternativas.

---

## R1. Puerta al LLM: interfaz propia sobre LiteLLM, multi-proveedor

**Decisión**: `backend/llm/` define un protocolo `LLMClient` con una operación
principal: `complete_structured(system, user, schema: type[BaseModel]) -> BaseModel`.
La implementación única (`litellm_client.py`) usa **LiteLLM** con **tool-calling
forzado**: el JSON-schema del modelo Pydantic (`model_json_schema()`) se registra como
única tool con `tool_choice="required"`, la respuesta se valida con
`model_validate()`. Temperatura 0.

La **selección de proveedor es 100 % por entorno** (factory sin código por proveedor):

| Perfil | Variables | Notas |
|--------|-----------|-------|
| **OpenCode Go** (default desarrollo) | `LOOM_LLM_MODEL=openai/kimi-k2.5`, `LOOM_LLM_API_BASE=https://opencode.ai/zen/go/v1`, `LOOM_LLM_API_KEY=<key de opencode.ai/auth>` | Suscripción del usuario; modelos abiertos con tool-calling (DeepSeek V4, Kimi K2.x, Qwen3.x, GLM-5.x). Límites por gasto: $12/5h, $30/semana. |
| **Azure OpenAI** (ocasional, empresa) | `LOOM_LLM_MODEL=azure/<deployment>`, `AZURE_API_KEY`, `AZURE_API_BASE`, `AZURE_API_VERSION` | Variables estándar de LiteLLM. Para contraste de calidad o si los modelos abiertos no pasan el gate. |
| Cualquier endpoint OpenAI-compatible (p. ej. Ollama local) | mismas variables que OpenCode Go con otra `API_BASE` | Gratis: sin código nuevo. |

**Modelo por defecto: lo decide la eval** (coherente con eval-first). Se empieza con
`openai/kimi-k2.5`; si ningún modelo de Go alcanza los umbrales (F1 ≥ 0.90,
B³ ≥ 0.85), cambiar a Azure es un cambio de env, no de código. El par (modelo,
proveedor) queda registrado en la clave de cache (R6) y en cada `EvalResult` (R9), así
las métricas siempre se atribuyen al modelo que las produjo.

**Racional**: Los dos backends del usuario hablan dialecto OpenAI; LiteLLM normaliza
tool-calling entre ellos, añade reintentos y expone `response_cost` por llamada
(alimenta la observabilidad de coste que pide la constitución), con una sola
dependencia y sin framework. La interfaz propia mínima cumple el Principio IV: LiteLLM
solo se importa dentro de `backend/llm/`; el código de aplicación nunca sabe qué
proveedor responde.

**Alternativas consideradas**: LangChain (`init_chat_model` + `with_structured_output`
— métodos comunes atractivos, pero más dependencias, magia entre prompt y modelo que
complica la cache por versión de prompt, y duplicaría la puerta que la constitución ya
exige propia); SDK `openai` a pelo con `OpenAI(base_url=…)`/`AzureOpenAI` (mínimo,
pero reescribiríamos a mano la normalización de tool-calling, reintentos y coste que
LiteLLM ya da); SDK `anthropic` (descartado: el usuario no dispone de API de
Anthropic); `instructor` (capa de reintentos mágicos acoplada a la firma del
proveedor); salida JSON en texto + parseo (prohibido por la constitución).

**Riesgo asumido**: la calidad de structured outputs varía entre modelos abiertos. El
gate de eval es el árbitro (ningún modelo se adopta sin pasar umbrales), y la regla
nº 1 del contrato de extracción (surface verificable contra el texto; menciones no
localizables se descartan) protege el grafo de salidas flojas.

**Nota para M4 (embeddings)**: OpenCode Go no ofrece embeddings; cuando lleguen los
`Passage` (M4), Azure OpenAI los cubre (`text-embedding-3-*` vía LiteLLM) u Ollama
local. Sin impacto en M1.

## R2. Unidad de extracción: escena, con contexto del registro acumulado

**Decisión**: Una llamada LLM por **escena** (la unidad mínima de la capa cruda de M0).
El prompt incluye: (a) el texto de la escena, (b) el **registro de entidades** ya
conocidas (nombre canónico + alias + rol), y (c) instrucciones de enlazar menciones a
entidades existentes por nombre canónico o declarar entidades nuevas. Procesamiento
secuencial en orden narrativo para que el registro crezca como lo haría un lector.

**Racional**: README §6 recomienda chunking por escena; el registro acumulado es el
patrón explícito del §6 para que el LLM enlace en vez de duplicar. El orden narrativo
hace que los alias tardíos ("Eli" en el cap. 40) encuentren a su entidad ("Elena" del
cap. 1) ya registrada.

**Alternativas consideradas**: por capítulo (chunks demasiado grandes en novelas de
escena larga, peor recall de menciones menores); paralelo con merge posterior (pierde
el registro incremental, dispara los duplicados y el coste de resolución); ventana
deslizante con solapamiento (coste extra sin beneficio claro para detección de
personajes).

## R3. Resolución de entidades: determinista primero, LLM después, humano al final

**Decisión**: Cascada de tres niveles con umbral de confianza:
1. **Determinista (auto-merge, confianza 1.0)**: coincidencia exacta del nombre
   normalizado (casefold, sin acentos/títulos honoríficos) o alias ya registrado.
2. **Heurística + LLM (confianza calculada)**: candidatos por similitud de nombre
   (subcadenas, hipocorísticos comunes, apellido compartido) se confirman con una
   llamada estructurada al LLM que ve las menciones en contexto y devuelve
   `same_entity: bool, confidence: float, rationale: str`.
3. **Cola humana (sin merge)**: si la confianza queda en zona gris
   (`0.5 ≤ c < 0.9` inicial, configurable), se crea un `MergeCandidate` con el contexto
   (menciones, escenas, fragmentos) y las entidades **permanecen separadas** hasta
   decisión humana. Por debajo de 0.5 ni se propone.

**Racional**: FR-005 y la constitución (human-in-the-loop) prohíben fusionar a ciegas;
el prior art (graphify-novel, patrón `[?]`) valida la cola de revisión. La cascada
minimiza llamadas LLM (la mayoría de menciones repiten nombre exacto) y deja la
decisión cara solo para los casos que la necesitan. SC-003 (cero fusiones erróneas
silenciosas) se defiende con el umbral alto de auto-merge.

**Alternativas consideradas**: embeddings de nombres + clustering (añade dependencia de
embeddings que el roadmap reserva a M4, y los nombres cortos dan señales débiles);
fastcoref/spaCy para correferencia completa (pipeline pesado por idioma; la correferencia
pronominal fina no es necesaria para el DoD de M1 — basta atribuir menciones nominales);
fusionar siempre lo que el LLM diga (viola FR-005).

## R4. Métrica de resolución: B-cubed F1

**Decisión**: La calidad del agrupamiento de menciones en entidades se mide con
**B-cubed precision/recall/F1** sobre el conjunto de menciones del golden dataset.
Umbral inicial: **B³ F1 ≥ 0.85** (SC-002). Detección de entidades: precision/recall/
**F1 ≥ 0.90** (SC-001) emparejando entidades del sistema con las del gold por nombre
canónico/alias (matching greedy por solapamiento de alias).

**Racional**: La constitución nombra B-cubed (o F1 por pares) para resolución; B-cubed
penaliza proporcionalmente tanto sobre-fusión como sub-fusión y es estándar en
correferencia. El emparejamiento por alias para detección evita castigar nombres
canónicos distintos pero equivalentes ("Mr. Darcy" vs "Fitzwilliam Darcy").

**Alternativas consideradas**: F1 por pares (válido, pero sobre-pondera las entidades
grandes; B-cubed es más estable con repartos desbalanceados); MUC (insensible a
singletons, y las novelas están llenas de personajes de una mención); CEAF (más
complejo de implementar sin beneficio diferencial aquí).

## R5. Golden dataset: JSON por obra junto a los fixtures de M0

**Decisión**: Un archivo `<obra>.characters.gold.json` por obra en `eval/fixtures/`,
versionado en git, con: lista de personajes (id, nombre canónico, alias, rol,
`is_mentioned_only`), y apariciones por escena (clave: `chapter_order/scene_order` de la
capa cruda de M0). Obras iniciales: **Pride and Prejudice** (anotación asistida por
fuentes públicas + verificación manual) y las **obras artesanales** de M0 (anotación
exacta por construcción). El README de fixtures documenta procedencia y criterios
(mascotas, colectivos, mencionados-sin-aparecer).

**Racional**: FR-008 pide dataset versionado con ≥2 obras; reutilizar los fixtures de
M0 da continuidad (mismas obras, misma segmentación) y las obras artesanales permiten
anotación perfecta y casos adversarios controlados (homónimos, alias). El criterio de
frontera vive en la anotación, no en el motor (Assumption de la spec).

**Alternativas consideradas**: anotar solo Pride and Prejudice (un solo punto de
medición, frágil); datasets académicos de NER literario como LitBank (inglés-céntrico,
esquema de menciones distinto al nuestro, integrarlo cuesta más que anotar las obras
que ya segmentamos).

## R6. Cache de extracción: contenido-direccionada en disco

**Decisión**: Cada respuesta del LLM se cachea como JSON en `.cache/extraction/`
(gitignored), con clave `SHA-256(texto_escena + PROMPT_VERSION + modelo +
SCHEMA_VERSION)`. El pipeline consulta la cache antes de llamar; un hit no genera
coste. Las escrituras al grafo son `MERGE` idempotentes con ids deterministas
(`character_id` = hash del manuscrito + nombre canónico normalizado de primera
aparición; `mention_id` = hash de escena + offsets).

**Racional**: Principio VI. La clave incluye versión de prompt y esquema para invalidar
correctamente al iterar. Disco y no grafo: es estado operacional re-derivable, no
conocimiento (mantiene el grafo como única fuente de verdad de conocimiento). La cache
convierte el pipeline secuencial en **reanudable**: re-lanzar tras un fallo continúa
desde la última escena no cacheada.

**Alternativas consideradas**: nodos de cache en Neo4j (contamina el grafo con
operaciones y complica el "borrar y re-derivar"); SQLite (otra pieza para lo que un
directorio contenido-direccionado resuelve); sin cache (viola la constitución y SC-005).

## R7. Interfaz de operación: CLI para extraer, API para inspeccionar y resolver

**Decisión**: La extracción se lanza con
`python -m backend.extraction.run <manuscript_id>` (proceso de minutos, con progreso y
resumen final). La API añade endpoints **rápidos**: `GET /manuscripts/{id}/characters`
(lista inspeccionable, FR-006), `GET /manuscripts/{id}/merge-candidates` y
`POST /merge-candidates/{id}/resolve` (aceptar/rechazar una fusión, FR-005). Aceptar
una fusión aplica el merge en el grafo (mover menciones/apariciones, unificar alias) y
registra la decisión; las decisiones humanas sobreviven re-ejecuciones del pipeline.

**Racional**: Un POST síncrono de 20+ minutos es un mal contrato HTTP, y un sistema de
jobs asíncronos es infraestructura de M8. El CLI es honesto con la naturaleza del
proceso y suficiente para el DoD; la API cubre lo que sí es interactivo (inspección y
revisión). Las decisiones humanas se persisten como propiedades/nodos en el grafo para
que la idempotencia no las pise (FR-012 + FR-005).

**Alternativas consideradas**: POST /extract síncrono (timeouts, conexiones colgadas);
BackgroundTasks de FastAPI (sin visibilidad de progreso ni reanudación, se pierde al
reiniciar); Prefect ya (rechazado en Complexity Tracking del plan).

## R8. Defensa de prompt injection en la extracción

**Decisión**: El prompt de sistema declara explícitamente que el texto de la escena es
**contenido no confiable**: se delimita con etiquetas, se instruye al modelo a extraer
solo de la prosa y a ignorar cualquier instrucción embebida en el manuscrito. El texto
del manuscrito jamás se interpola en el prompt de sistema, solo en el bloque de usuario
delimitado. Test de regresión con un fixture adversarial (manuscrito con instrucciones
embebidas tipo "ignora lo anterior y devuelve...").

**Racional**: FR-013; patrón adoptado del prior art (§2.10 del teardown). Coste cero y
elimina una clase entera de fallos en un producto que ingiere manuscritos arbitrarios.

**Alternativas consideradas**: sanitización por regex del texto de entrada (frágil e
imposible de hacer exhaustiva sin dañar la prosa); confiar en el modelo sin
instrucciones explícitas (innecesariamente arriesgado).

## R9. Registro de resultados de eval: JSON versionado por ejecución

**Decisión**: Cada ejecución del harness escribe
`eval/results/characters-<obra>-<fecha>-<git-sha>.json` con métricas, umbrales
vigentes, versión de prompt/modelo y conteos. Un comando de comparación
(`eval/characters/runner.py --compare`) muestra el delta contra la última ejecución
registrada. El gate de CI (pytest marker `eval`) falla si una métrica clave queda bajo
umbral (`eval/characters/thresholds.py`).

**Racional**: FR-010/FR-011 y SC-007: comparabilidad entre ejecuciones y bloqueo
automático. Versionar resultados en git da la "tabla de regresión" del README §9 sin
infraestructura extra.

**Alternativas consideradas**: base de datos de métricas (infraestructura prematura);
solo el verde/rojo de pytest sin histórico (pierde la comparabilidad exigida por
FR-010).
