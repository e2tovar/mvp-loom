# Tasks: M1 — Extracción y resolución de personajes + eval harness

**Input**: Design documents from `specs/002-char-extraction-eval/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Incluidos — el proyecto es eval-first (constitución, Principio I) y los
invariantes del data-model (INV-M1-1..5) exigen verificación automatizada.

**Organization**: Tareas agrupadas por user story para que cada una sea un incremento
independiente y verificable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: paralelizable (archivos distintos, sin dependencias pendientes)
- **[Story]**: US1 (extracción), US2 (eval), US3 (cola de fusiones), US4 (cache)

## Path Conventions

Monorepo `backend/` + `eval/` + `tests/` según plan.md (§ Project Structure).

---

## Phase 1: Setup

**Purpose**: Dependencias, configuración y esqueleto de módulos nuevos.

- [x] T001 Añadir `litellm` a `pyproject.toml` (dependencies) y ejecutar `uv sync`
- [x] T002 [P] Añadir a `.env.example` los dos perfiles del factory LLM (research R1): `LOOM_LLM_MODEL`, `LOOM_LLM_API_BASE`, `LOOM_LLM_API_KEY` (OpenCode Go) y `AZURE_API_KEY`/`AZURE_API_BASE`/`AZURE_API_VERSION` (Azure), comentados con su uso
- [x] T003 [P] Añadir `.cache/` a `.gitignore` y crear esqueletos de paquete con `__init__.py`: `backend/llm/`, `backend/extraction/`, `eval/characters/`, `eval/results/` (con `.gitkeep`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: La puerta LLM, los contratos tipados y el esquema de grafo que todas las
stories necesitan.

**⚠️ CRITICAL**: Ninguna user story puede empezar sin esta fase.

- [x] T004 Errores de dominio de M1 en `backend/core/errors.py`: `ExtractionError`, `NotExtractedError`, `AlreadyResolvedError`, `LLMUnavailableError`
- [x] T005 Protocolo `LLMClient` en `backend/llm/interface.py`: `complete_structured(system: str, user: str, schema: type[BaseModel]) -> BaseModel`, excepciones y configuración por env (contracts/extraction-schema.md)
- [x] T006 Implementación LiteLLM en `backend/llm/litellm_client.py`: tool-calling forzado (`tool_choice="required"`), `temperature=0`, proveedor por env (research R1), validación Pydantic con un reintento ante `ValidationError`, log de coste por llamada (`response_cost`)
- [x] T007 [P] Contratos de extracción en `backend/extraction/schemas.py`: `SCHEMA_VERSION`, `RegistryEntry`, `SceneContext`, `MentionOut`, `CharacterCandidateOut`, `SceneExtraction`, `MergeJudgement` (contracts/extraction-schema.md)
- [x] T008 [P] Delta de esquema M1 en `backend/graph/schema.py`: constraints `character_id_unique`, `mention_id_unique`, `merge_candidate_id_unique` e índices de apoyo (contracts/graph-schema.cypher)
- [x] T009 [P] Tests unitarios de la puerta LLM en `tests/unit/test_llm_client.py`: validación de salida contra esquema, reintento ante respuesta inválida, error claro sin API key (con transporte falso, sin red)

**Checkpoint**: Puerta LLM operativa y tipada; esquema de grafo aplicado.

---

## Phase 3: User Story 1 — Extraer los personajes de un manuscrito ingerido (Priority: P1) 🎯 MVP

**Goal**: De un manuscrito segmentado (M0) a entidades `Character` en el grafo con
alias consolidados, apariciones por escena y procedencia verificable.

**Independent Test**: Extraer una obra de fixtures y cotejar la lista de personajes,
alias y apariciones contra el libro; cada hecho rastreable a escena + cita (quickstart §2).

### Implementation for User Story 1

- [x] T010 [P] [US1] Prompt de extracción versionado en `backend/extraction/prompts.py`: `PROMPT_VERSION`, system prompt con defensa de inyección (texto de escena delimitado como no confiable, research R8), instrucciones de registro/enlace y exclusión de colectivos
- [x] T011 [P] [US1] Registro acumulado de entidades en `backend/extraction/registry.py`: alta de entidades, búsqueda por nombre/alias normalizado, serialización a `list[RegistryEntry]` para el contexto del prompt (research R2)
- [x] T012 [US1] Resolución en `backend/extraction/resolution.py`: normalización de nombres (casefold, acentos, honoríficos), nivel 1 determinista (match exacto/alias → auto-merge), nivel 2 heurístico (candidatos por similitud + `MergeJudgement` vía LLM); confianza ≥ 0.9 fusiona, < 0.9 deja separado (la cola llega en US3) (research R3)
- [x] T013 [US1] Escritura/lectura de personajes en `backend/graph/characters.py`: upsert `MERGE` idempotente de `Character`/`Mention`/`APPEARS_IN` con ids deterministas, y consultas nombradas para la lista y el detalle (contracts/graph-schema.cypher)
- [x] T014 [US1] Pipeline en `backend/extraction/pipeline.py`: escenas en orden narrativo → `SceneContext` con registro → LLM → verificación de `surface` y derivación de offsets (regla 1 del contrato; menciones no localizables se descartan con log) → resolución → escritura al grafo
- [x] T015 [US1] CLI en `backend/extraction/run.py`: `python -m backend.extraction.run <manuscript_id>` con progreso por escena, resumen final (personajes, menciones, coste) y exit codes claros (contracts/api.md)
- [x] T016 [US1] Endpoints de inspección en `backend/api/routes_characters.py`: `GET /manuscripts/{id}/characters` (filtros y orden según contrato) y `GET /manuscripts/{id}/characters/{character_id}` (detalle con menciones), errores `not_found`/`not_extracted`; registrar router en `backend/api/app.py`
- [x] T017 [P] [US1] Tests unitarios de resolución en `tests/unit/test_resolution.py`: normalización, auto-merge determinista, homónimos NO fusionados por similitud, colectivos filtrados, zona gris queda separada
- [x] T018 [P] [US1] Tests unitarios de pipeline en `tests/unit/test_extraction_pipeline.py`: verificación de surfaces/offsets contra texto de escena, descarte de menciones no localizables, construcción del contexto con registro (LLM falso)
- [x] T019 [US1] Tests de integración en `tests/integration/test_characters_flow.py`: pipeline con LLM falso determinista + Neo4j real → grafo con `Character`/`Mention`/`APPEARS_IN` correctos, INV-M1-2 (procedencia verificable), INV-M1-3 (sin huérfanos), INV-M1-5 (capa cruda intacta); endpoints GET devuelven el contrato

**Checkpoint**: US1 funcional — extraer un libro y verlo en `GET /characters`.

---

## Phase 4: User Story 2 — Medir la calidad con un dataset de oro (Priority: P2)

**Goal**: Golden dataset (≥2 obras) + harness con F1 de detección y B-cubed de
resolución, resultados comparables y gate de CI.

**Independent Test**: Con un gold y salidas sintéticas (perfecta, vacía, con errores
conocidos) el harness produce las métricas esperadas y falla bajo umbral.

### Implementation for User Story 2

- [x] T020 [P] [US2] Golden dataset de las obras artesanales en `eval/fixtures/crafted-three-chapters.txt.characters.gold.json` y `crafted-two-chapters.epub.characters.gold.json` (anotación exacta por construcción; incluir un caso de homónimos y uno de alias) (data-model: CharacterGold)
- [x] T021 [P] [US2] Golden dataset de Pride and Prejudice en `eval/fixtures/pride-and-prejudice.txt.characters.gold.json`: personajes, alias y apariciones por `c{chapter}/s{scene}`; documentar criterios de frontera (mascotas, colectivos, solo-mencionados) en `eval/fixtures/README.md`
- [x] T022 [P] [US2] Métricas en `eval/characters/metrics.py`: precision/recall/F1 de detección (matching de entidades por solapamiento de alias, research R4) y B-cubed P/R/F1 sobre menciones; conteo de `silent_bad_merges`
- [x] T023 [P] [US2] Umbrales versionados en `eval/characters/thresholds.py`: `DETECTION_F1 = 0.90`, `RESOLUTION_B3_F1 = 0.85`, `SILENT_BAD_MERGES = 0`, con nota de recalibración justificada (spec Assumptions)
- [x] T024 [US2] Runner en `eval/characters/runner.py`: carga gold + salida del grafo, mapea apariciones `c/s` → `scene_id`, calcula métricas, escribe `eval/results/characters-<obra>-<fecha>-<sha>.json` (data-model: EvalResult), `--compare` contra el último resultado, exit ≠ 0 bajo umbral
- [x] T025 [P] [US2] Tests unitarios de métricas en `tests/unit/test_character_metrics.py`: salida perfecta → 1.0, vacía → 0.0, sobre-fusión y sub-fusión penalizadas por B-cubed, matching por alias correcto
- [x] T026 [US2] Gate de CI en `tests/eval/test_characters_gate.py` (marker `eval`): ejecuta el harness sobre las obras con extracción presente en el grafo; falla bajo umbral; skip claro si no hay extracción (documentado en el test)

**Checkpoint**: `uv run python -m eval.characters.runner` produce métricas y el gate
bloquea regresiones.

---

## Phase 5: User Story 3 — Revisar fusiones dudosas (Priority: P3)

**Goal**: Zona gris (0.5 ≤ c < 0.9) → `MergeCandidate` en el grafo, consultable y
resoluble por API; decisiones humanas finales que sobreviven re-ejecuciones.

**Independent Test**: Texto con homónimos ambiguos → entidades separadas + caso en la
cola con contexto; accept aplica el merge, reject es permanente.

### Implementation for User Story 3

- [x] T027 [US3] Cola de fusiones en `backend/graph/merge_candidates.py`: crear (id determinista, evidencia JSON), listar por estado, resolver — `accept` aplica el merge (mover menciones/apariciones, fusionar alias, `merged_from`, `DETACH DELETE` de B), `reject` marca permanente (contracts/graph-schema.cypher)
- [x] T028 [US3] Integrar la zona gris en `backend/extraction/resolution.py` y `pipeline.py`: confianza en [0.5, 0.9) crea `MergeCandidate` con evidencia (menciones, escenas, citas); antes de proponer o fusionar, consultar decisiones previas (rejected no se re-propone, accepted no se re-separa) (INV-M1-4)
- [x] T029 [US3] Endpoints en `backend/api/routes_characters.py`: `GET /manuscripts/{id}/merge-candidates?status=` y `POST /merge-candidates/{id}/resolve` con `{"decision": "accept"|"reject"}`, errores `already_resolved`/`invalid_decision` (contracts/api.md)
- [x] T030 [P] [US3] Tests unitarios en `tests/unit/test_merge_candidates.py`: id determinista del par, zona gris encola en vez de fusionar, decisiones previas respetadas por la resolución
- [x] T031 [US3] Tests de integración en `tests/integration/test_merge_review_flow.py`: flujo completo accept (menciones movidas, B eliminado, alias fusionados) y reject (par no re-propuesto tras re-ejecutar el pipeline con LLM falso) — INV-M1-4

**Checkpoint**: Human-in-the-loop operativo; ninguna fusión dudosa silenciosa.

---

## Phase 6: User Story 4 — Re-extracción idempotente y barata (Priority: P4)

**Goal**: Cache contenido-direccionada que hace la re-ejecución casi gratuita y el
pipeline reanudable.

**Independent Test**: Segunda ejecución sin cambios no llama al LLM (contador del
cliente falso = 0) y produce el mismo grafo.

### Implementation for User Story 4

- [x] T032 [US4] Cache en `backend/llm/cache.py`: store JSON contenido-direccionado en `.cache/extraction/` con clave `SHA-256(scene_text + PROMPT_VERSION + model + SCHEMA_VERSION)` (research R6)
- [x] T033 [US4] Integrar cache en `backend/extraction/pipeline.py` y `run.py`: consulta antes de llamar, escritura tras validar, flag `--force` (ignora cache, respeta decisiones humanas), log de hit/miss por escena
- [x] T034 [P] [US4] Tests unitarios en `tests/unit/test_extraction_cache.py`: clave estable, invalidación al cambiar `PROMPT_VERSION`/modelo/`SCHEMA_VERSION`, round-trip de `SceneExtraction`
- [x] T035 [US4] Test de integración en `tests/integration/test_idempotent_rerun.py`: dos ejecuciones con LLM falso — la segunda con 0 llamadas y grafo idéntico (mismos `character_id`/`mention_id`, INV-M1-1); `--force` re-llama pero converge

**Checkpoint**: SC-005 verificable — re-ejecutar cuesta < 10 % y converge.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T036 [P] Test adversarial de prompt injection en `tests/unit/test_prompt_injection.py`: fixture con instrucciones embebidas → el prompt construido las mantiene delimitadas en el bloque de usuario, nunca en el system (FR-013, research R8)
- [x] T037 [P] ADR del factory LLM en `docs/adr/0002-llm-gateway-litellm.md`: decisión LiteLLM multi-proveedor (OpenCode Go + Azure), alternativas (LangChain, SDK directo, Anthropic) y el modelo-lo-decide-la-eval (research R1)
- [x] T038 Ejecutar el quickstart completo contra una obra real (extracción con OpenCode Go + inspección + eval) y corregir fricciones; verificar SC-006 (eval < 10 min) y SC-008 (revisión < 15 min)
- [x] T039 `uv run ruff check backend eval tests` y suite completa `uv run pytest` en verde; revisar cumplimiento de la constitución (LiteLLM solo en `backend/llm/`, Cypher solo en `backend/graph/`)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (P1)**: sin dependencias.
- **Foundational (P2)**: requiere Setup. **Bloquea todas las stories.**
- **US1 (P3)**: requiere Foundational. Sin dependencias de otras stories.
- **US2 (P4)**: requiere Foundational; para el gate end-to-end (T026) necesita la
  extracción de US1, pero T020–T025 solo dependen de Foundational.
- **US3 (P5)**: requiere US1 (extiende `resolution.py`/`pipeline.py` y el router).
- **US4 (P6)**: requiere US1 (integra la cache en el pipeline).
- **Polish (P7)**: requiere las stories deseadas completas.

### Within Each User Story

Modelos/contratos → servicios → endpoints/CLI → tests de integración. Los tests
unitarios marcados [P] pueden escribirse en paralelo a la implementación de otros
archivos.

### Parallel Opportunities

- T002–T003 en paralelo tras T001.
- T007, T008, T009 en paralelo tras T006.
- En US1: T010, T011 en paralelo; T017, T018 en paralelo entre sí.
- En US2: T020, T021, T022, T023 en paralelo (archivos distintos); T025 tras T022.
- US2 (T020–T025) puede avanzar en paralelo con US1 si hay capacidad (solo T026
  necesita US1 terminada).

---

## Parallel Example: User Story 2

```bash
# Anotaciones y métricas en paralelo (archivos distintos):
Task: "Golden dataset obras artesanales (T020)"
Task: "Golden dataset Pride and Prejudice (T021)"
Task: "Métricas detección + B-cubed (T022)"
Task: "Umbrales versionados (T023)"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 → Phase 2 (puerta LLM + contratos + esquema).
2. Phase 3 (US1): extraer una obra artesanal y verla en `GET /characters`.
3. **STOP and VALIDATE**: cotejar el reparto contra el libro (quickstart §2).

### Incremental Delivery

1. US1 → demo: el reparto de un libro real con procedencia. (MVP)
2. US2 → las métricas dicen si el MVP es *bueno*; el gate protege el avance.
3. US3 → human-in-the-loop sobre fusiones dudosas.
4. US4 → iterar sobre prompts/modelos se vuelve barato.
5. Cierre de milestone: DoD del quickstart §5 (las 6 casillas).

### Notas

- El modelo LLM lo decide la eval (research R1): si Kimi K2.5 no pasa umbrales,
  probar DeepSeek V4/Qwen3.7 de Go y, en último término, Azure — todo por env.
- Los tests de integración usan **LLM falso determinista** (sin red, sin coste); las
  llamadas reales solo ocurren en la extracción manual (T038) y se cachean.
- Commit por tarea o grupo lógico; los checkpoints son puntos de validación.
