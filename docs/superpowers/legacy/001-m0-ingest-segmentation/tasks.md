---

description: "Task list — M0: Ingestión y segmentación de manuscritos"
---

# Tasks: M0 — Ingestión y segmentación de manuscritos

**Input**: Design documents from `specs/001-m0-ingest-segmentation/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: SÍ se incluyen. El Principio I de la constitución (Eval-first, NO NEGOCIABLE)
hace de los tests y del proto-eval un gate de CI obligatorio para este proyecto.

**Organization**: Tareas agrupadas por historia de usuario para implementación y prueba
independientes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Puede ejecutarse en paralelo (archivos distintos, sin dependencias pendientes)
- **[Story]**: Historia de usuario a la que pertenece (US1, US2, US3)
- Las descripciones incluyen rutas de archivo exactas

## Path Conventions

Servicio backend monorepo (plan.md §Project Structure): `backend/`, `eval/`, `tests/` en
la raíz del repositorio.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Inicialización del proyecto y estructura base.

- [x] T001 Crear la estructura de directorios del backend con `__init__.py` en `backend/ingest/`, `backend/ingest/parsers/`, `backend/ingest/segmentation/`, `backend/graph/`, `backend/api/`, `backend/core/`, y crear `eval/fixtures/`, `eval/segmentation/`, `tests/unit/`, `tests/integration/`, `tests/eval/` (per plan.md)
- [x] T002 Añadir dependencias del backend en `pyproject.toml` (`fastapi`, `uvicorn[standard]`, `pydantic>=2`, `neo4j`, `ebooklib`, `beautifulsoup4`, `lxml`, `python-docx`; dev: `pytest`, `httpx`) y ejecutar `uv sync`
- [x] T003 [P] Crear `docker-compose.yml` en la raíz con servicio Neo4j 5.x (puertos 7474/7687, APOC habilitado, volumen de datos en `neo4j/data/` ya ignorado) y servicio de la API
- [x] T004 [P] Configurar `ruff` y `pytest` en `pyproject.toml` (incluyendo markers para `unit`/`integration`/`eval`) y crear `.env.example` con `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
- [x] T005 [P] Crear `eval/fixtures/README.md` documentando procedencia y licencia, y descargar ≥2 novelas de dominio público (al menos una `.epub` y una `.txt` de Project Gutenberg, una de ellas con separadores de escena explícitos) en `eval/fixtures/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Infraestructura núcleo que DEBE existir antes de cualquier historia.

**⚠️ CRITICAL**: Ninguna historia de usuario puede empezar hasta completar esta fase.

- [x] T006 [P] Implementar errores de dominio en `backend/core/errors.py` (`UnsupportedFormatError`, `InvalidFileError`, `NoNarrativeContentError`, `ManuscriptNotFoundError`)
- [x] T007 [P] Implementar hashing de contenido en `backend/core/hashing.py` (`sha256` del contenido narrativo normalizado → `manuscript_id`, per research.md D6)
- [x] T008 Implementar los modelos Pydantic v2 de la capa cruda en `backend/ingest/models.py` (`Manuscript`, `Chapter`, `Scene`, `NonNarrativeBlock` con sus campos y validadores, per data-model.md)
- [x] T009 [P] Implementar el cliente Neo4j en `backend/graph/client.py` (conexión desde entorno, helpers de sesión, cierre limpio)
- [x] T010 Implementar la aplicación idempotente del esquema en `backend/graph/schema.py` ejecutando las constraints/índices de `contracts/graph-schema.cypher` (depende de T009)
- [x] T011 Crear el esqueleto de la app FastAPI en `backend/api/app.py` (instancia, aplica el esquema del grafo en `startup`, configura logging estructurado básico) (depende de T010)

**Checkpoint**: Fundación lista — las historias de usuario pueden comenzar.

---

## Phase 3: User Story 1 - Ingerir y segmentar en capítulos y escenas (Priority: P1) 🎯 MVP

**Goal**: Subir un manuscrito (`.epub`/`.txt`/`.docx`) y obtener la capa cruda inmutable
(capítulos → escenas, Nivel 0 + Nivel 1) persistida en Neo4j, con boilerplate excluido y
texto íntegro.

**Independent Test**: Ingerir una novela de fixture vía `POST /manuscripts` y comprobar
en el grafo que los capítulos (en orden), las escenas por capítulo y el texto coinciden
con el original, sin contenido no-narrativo, cumpliendo SC-001/002/003/004/007.

### Tests for User Story 1 ⚠️ (escribir primero, deben FALLAR antes de implementar)

- [x] T012 [P] [US1] Tests unitarios de parsers (epub/txt/docx) en `tests/unit/test_parsers.py` usando fixtures pequeñas
- [x] T013 [P] [US1] Tests unitarios de segmentación (Nivel 0, Nivel 1, separador vs salto de párrafo FR-004a, capítulo sin marcadores) en `tests/unit/test_segmentation.py`
- [x] T014 [P] [US1] Test de contrato de `POST /manuscripts` (201/200/400/415/422) en `tests/integration/test_post_manuscripts.py`
- [x] T015 [P] [US1] Test de integración pipeline→grafo (capítulos, escenas, orden global, no duplicados) en `tests/integration/test_ingest_pipeline.py`

### Implementation for User Story 1

- [x] T016 [P] [US1] Definir el protocolo/base de parser en `backend/ingest/parsers/base.py` (entrada → bloques normalizados con metadatos de posición)
- [x] T017 [P] [US1] Implementar el parser EPUB en `backend/ingest/parsers/epub_parser.py` (`ebooklib` + `BeautifulSoup`, recorrido del spine en orden de lectura)
- [x] T018 [P] [US1] Implementar el parser TXT en `backend/ingest/parsers/txt_parser.py` (detección de codificación + stripping del boilerplate Gutenberg)
- [x] T019 [P] [US1] Implementar el parser DOCX en `backend/ingest/parsers/docx_parser.py` (`python-docx`, estilos de encabezado y estilo/alineación de separador)
- [x] T020 [US1] Implementar la detección de contenido no-narrativo en `backend/ingest/non_narrative.py` (marcadores Gutenberg, TOC/portada/copyright; produce `NonNarrativeBlock`) (depende de T008)
- [x] T021 [US1] Implementar la detección de capítulos por formato en `backend/ingest/segmentation/chapters.py` (spine/nav en epub, regex de encabezado en txt, estilos en docx; conserva prólogo/epílogo FR-012) (depende de T016-T019)
- [x] T022 [US1] Implementar la segmentación de escenas Nivel 0 + Nivel 1 en `backend/ingest/segmentation/scenes.py` (frontera de capítulo + separadores tipográficos deterministas, `boundary_reason`) (depende de T008, T021)
- [x] T023 [US1] Implementar el pipeline de ingestión en `backend/ingest/pipeline.py` (parse → no-narrativo → capítulos → escenas → construir modelos + `manuscript_id` por hash) (depende de T007, T008, T020, T021, T022)
- [x] T024 [US1] Implementar la escritura idempotente de la capa cruda (MERGE de `Manuscript`/`Chapter`/`Scene`/`NonNarrativeBlock` y relaciones de orden) en `backend/graph/raw_layer.py` (depende de T008, T009, T010)
- [x] T025 [US1] Implementar la ruta `POST /manuscripts` en `backend/api/routes_manuscripts.py` (multipart, mapeo de errores a 400/415/422, respuesta con recuentos) (depende de T023, T024, T006)
- [x] T026 [US1] Registrar el router e integrarlo en `backend/api/app.py` (depende de T011, T025)

### Validación medible (proto-eval — gate de CI, Principio I)

- [x] T027 [P] [US1] Crear la anotación de referencia de cada fixture en `eval/fixtures/<obra>.annotation.json` (capítulos esperados y posiciones de separadores de escena, per research.md D10)
- [x] T028 [US1] Implementar el runner de exactitud en `eval/segmentation/accuracy.py` (exactitud de capítulos SC-002 y de separadores de escena SC-003 frente a la anotación) (depende de T023)
- [x] T029 [US1] Implementar el test-gate del proto-eval en `tests/eval/test_segmentation_accuracy.py` (falla si capítulos < 95 % o separadores < 90 %) (depende de T027, T028)

**Checkpoint**: US1 funcional e independientemente testable — MVP de M0.

---

## Phase 4: User Story 2 - Inspeccionar y verificar la segmentación (Priority: P2)

**Goal**: Exponer un resumen estructural inspeccionable (jerarquía capítulo→escena,
conteos, fragmentos) que permita confirmar visualmente la corrección (DoD, SC-008).

**Independent Test**: Tras ingerir una fixture, llamar a
`GET /manuscripts/{id}/structure` y comprobar que el resumen permite cotejar capítulos,
escenas y fragmentos contra el original y localizar un error de segmentación.

### Tests for User Story 2 ⚠️

- [x] T030 [P] [US2] Test de contrato de `GET /manuscripts/{id}/structure` (200 con jerarquía/conteos/snippets, 404) en `tests/integration/test_get_structure.py`

### Implementation for User Story 2

- [x] T031 [US2] Implementar la consulta de lectura del resumen estructural en `backend/graph/raw_layer.py` (jerarquía capítulo→escena con conteos y `snippet`, Cypher nombrado) (depende de T024)
- [x] T032 [US2] Implementar la ruta `GET /manuscripts/{id}/structure` en `backend/api/routes_manuscripts.py` (params `include_snippets`, `snippet_len`; 404 con error de dominio) (depende de T031, T006)

**Checkpoint**: US1 y US2 funcionan de forma independiente.

---

## Phase 5: User Story 3 - Re-ingestión determinista e idempotente (Priority: P3)

**Goal**: Garantizar que re-ingerir el mismo contenido produce un resultado idéntico sin
duplicar, y que dos archivos con el mismo contenido narrativo comparten `manuscript_id`.

**Independent Test**: Ingerir dos veces el mismo archivo → resultado idéntico y
`created: false`; ingerir dos archivos con idéntico contenido y distinto nombre → mismo
`manuscript_id` (US3, SC-005, FR-009).

### Tests for User Story 3 ⚠️

- [x] T033 [P] [US3] Test de integración: re-ingerir el mismo archivo → grafo idéntico, sin duplicados, `created: false` en `tests/integration/test_idempotency.py`
- [x] T034 [P] [US3] Test de integración: dos archivos con mismo contenido y distinto nombre → mismo `manuscript_id` en `tests/integration/test_idempotency.py`

### Implementation for User Story 3

- [x] T035 [US3] Añadir la detección de manuscrito existente y el flag `created` (200 vs 201) en `backend/graph/raw_layer.py` y `backend/api/routes_manuscripts.py` (depende de T024, T025)
- [x] T036 [US3] Asegurar que el hashing normalizado ignora diferencias de contenedor/nombre en `backend/core/hashing.py` y `backend/ingest/pipeline.py` (normalización previa al hash, per D6) (depende de T007, T023)

**Checkpoint**: Las tres historias funcionan de forma independiente.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Garantías transversales y cierre del DoD de M0.

- [x] T037 [P] Test de invariante de no-pérdida (SC-004): el texto narrativo reconstruido desde las escenas coincide con el original menos separadores y bloques no-narrativos, en `tests/integration/test_no_loss.py`
- [x] T038 [P] Verificación de rendimiento (SC-006): ingerir una novela de ~150k palabras en < 5 min, en `tests/eval/test_performance.py`
- [x] T039 [P] Añadir ADR en `docs/` justificando "capa cruda en Neo4j desde M0" y notas de ingestión (patrón de docs vivas de la constitución)
- [x] T040 Validar el recorrido completo de `quickstart.md` (docker compose up → ingestión epub/txt/docx → GET structure → pytest) y corregir desviaciones
- [x] T041 Ejecutar la suite completa (`uv run pytest`) y confirmar que el gate del proto-eval pasa los umbrales SC-002/SC-003

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias — empieza de inmediato.
- **Foundational (Phase 2)**: depende de Setup — BLOQUEA todas las historias.
- **User Stories (Phase 3-5)**: dependen de Foundational. US1 (P1) es el MVP.
- **Polish (Phase 6)**: depende de las historias deseadas completadas.

### User Story Dependencies

- **US1 (P1)**: tras Foundational. Sin dependencias de otras historias.
- **US2 (P2)**: tras Foundational; lee la capa cruda escrita por US1 (T024). Testable
  de forma independiente ingiriendo una fixture primero.
- **US3 (P3)**: tras Foundational; refina la escritura/identidad de US1 (T024, T025).
  Testable de forma independiente.

### Within Each User Story

- Los tests se escriben y FALLAN antes de implementar.
- Modelos → parsers → segmentación → pipeline → escritura al grafo → endpoint.
- Núcleo antes que la integración; historia completa antes de pasar a la siguiente.

### Parallel Opportunities

- Setup: T003, T004, T005 en paralelo (tras T001/T002).
- Foundational: T006, T007, T009 en paralelo; T008 independiente; T010→T011 secuenciales.
- US1 tests (T012-T015) en paralelo; parsers (T016-T019) en paralelo entre sí.
- Distintas historias pueden abordarse en paralelo una vez completada la Fundación.

---

## Parallel Example: User Story 1

```bash
# Tests de US1 juntos (deben fallar primero):
Task: "T012 Unit tests de parsers en tests/unit/test_parsers.py"
Task: "T013 Unit tests de segmentación en tests/unit/test_segmentation.py"
Task: "T014 Contract test POST /manuscripts en tests/integration/test_post_manuscripts.py"
Task: "T015 Integration test pipeline→grafo en tests/integration/test_ingest_pipeline.py"

# Parsers de US1 juntos:
Task: "T017 EPUB parser en backend/ingest/parsers/epub_parser.py"
Task: "T018 TXT parser en backend/ingest/parsers/txt_parser.py"
Task: "T019 DOCX parser en backend/ingest/parsers/docx_parser.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Completar Phase 1: Setup.
2. Completar Phase 2: Foundational (CRÍTICO — bloquea todo).
3. Completar Phase 3: US1 (incluido el proto-eval T027-T029).
4. **PARAR y VALIDAR**: ingerir una novela real y verificar la segmentación + gate verde.
5. Demo del MVP.

### Incremental Delivery

1. Setup + Foundational → Fundación lista.
2. US1 → ingestión + segmentación + grafo + proto-eval (MVP) → demo.
3. US2 → inspección vía API → demo (cierra el DoD de "ver el libro segmentado").
4. US3 → idempotencia/determinismo → demo.
5. Polish → no-pérdida, rendimiento, ADR, quickstart, suite completa.

---

## Notes

- [P] = archivos distintos, sin dependencias pendientes.
- La etiqueta [Story] mapea cada tarea a su historia para trazabilidad.
- Verificar que los tests fallan antes de implementar (eval-first, Principio I).
- Commit tras cada tarea o grupo lógico.
- El gate del proto-eval (T029) bloquea el merge si la exactitud cae bajo umbral.
- Sin llamadas a LLM en M0 (Principio IV, vacuo): no se introduce `backend/llm/`.
