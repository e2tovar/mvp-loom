# Implementation Plan: M0 — Ingestión y segmentación de manuscritos

**Branch**: `001-m0-ingest-segmentation` | **Date**: 2026-06-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-m0-ingest-segmentation/spec.md`

## Summary

M0 toma un manuscrito completo (`.epub`, `.txt`, `.docx`) y produce la **capa cruda
inmutable** del proyecto: el texto normalizado descompuesto en capítulos y, dentro de
cada capítulo, en escenas, preservando el orden de lectura y la posición de origen. La
segmentación de escenas es **determinista** (Nivel 0: frontera de capítulo = inicio de
escena; Nivel 1: separadores tipográficos explícitos); la detección semántica (Nivel 2,
LLM) queda fuera de alcance. La capa cruda se persiste como el sustrato del grafo
(nodos `Manuscript`/`Chapter`/`Scene` en Neo4j), se escribe de forma idempotente por
hash de contenido, y se expone un resumen estructural inspeccionable vía API para la
verificación manual que constituye el DoD de M0. La corrección se mide automáticamente
contra novelas de dominio público anotadas, y esos checks actúan como gate de CI.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: FastAPI + Pydantic v2 (contrato tipado de la capa cruda),
`neo4j` (driver oficial), `ebooklib` + `beautifulsoup4`/`lxml` (EPUB → HTML → texto),
`python-docx` (DOCX, incluido estilo/alineación de párrafo), lector de texto plano para
`.txt`. `pytest` para lógica y para los checks de exactitud de segmentación.

**Storage**: Neo4j 5.x como sustrato del grafo (Principio II). En M0 solo se materializa
la capa cruda: `Manuscript`, `Chapter`, `Scene`, `NonNarrativeBlock` y sus relaciones de
orden. El índice vectorial y `Passage` llegan en milestones posteriores.

**Testing**: `pytest` (unidad + integración con Neo4j vía docker-compose) y un
**proto-eval** de segmentación: fixtures de novelas de dominio público con anotación de
referencia (capítulos y separadores de escena) sobre las que se calculan las exactitudes
de SC-002/SC-003. Estos checks corren en CI y bloquean el merge si caen bajo umbral.

**Target Platform**: Servicio backend en Linux contenedorizado; desarrollo local en
Windows vía `docker-compose` (Neo4j + API). Sin frontend en M0 (se aborda en M7).

**Project Type**: Servicio web (API backend). Estructura monorepo `backend/` + `eval/`
+ `tests/`, alineada con §11 del README.

**Performance Goals**: Ingerir y segmentar una novela de hasta 150 000 palabras en
< 5 minutos en el entorno de desarrollo (SC-006). Sin llamadas a LLM, el coste dominante
es parsing + I/O a Neo4j, holgadamente dentro del objetivo.

**Constraints**: Segmentación 100 % determinista (sin LLM en M0) para preservar la
re-ingestión idéntica (SC-005); escritura idempotente por hash de contenido (FR-009);
preservación de codificación y texto íntegro (FR-008); rechazo limpio de entradas
inválidas (FR-011).

**Scale/Scope**: Un manuscrito por ingestión; novelas de ~50k–200k palabras; decenas a
~cien capítulos; cientos a miles de escenas por libro.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principio | Estado | Cómo lo cumple M0 |
|---|-----------|--------|-------------------|
| I | Eval-first (NO NEGOCIABLE) | ✅ PASS | M0 no usa el golden dataset de M1, pero define métricas objetivas (SC-002/003/004/005) y las verifica con un proto-eval automatizado sobre novelas anotadas que actúa de **gate de CI**. La extracción semántica que requiere el harness completo no existe aún en M0. |
| II | El grafo es la columna vertebral | ✅ PASS | La capa cruda se persiste como nodos `Manuscript`/`Chapter`/`Scene` en Neo4j; es la única fuente de verdad desde el día uno. No se introducen stores paralelos. |
| III | Contratos tipados (Pydantic) | ✅ PASS | Toda la capa cruda se modela con Pydantic v2; el parsing produce y valida estos modelos antes de escribir al grafo. |
| IV | Una sola puerta al LLM | ✅ PASS (vacuo) | M0 **no realiza ninguna llamada a LLM**. No se introducen SDKs de proveedor. La interfaz `backend/llm/` se crea cuando M1 la necesite. |
| V | Citas obligatorias (anclaje en Passage) | ✅ PASS (preparado) | M0 no produce afirmaciones analíticas, así que no hay nada que citar. Las `Scene` guardan metadatos de posición (FR-005) que habilitan el anclaje a `Passage` en milestones futuros. |
| VI | Idempotencia y cache por hash | ✅ PASS | `manuscript_id` deriva del hash SHA-256 del contenido normalizado; las escrituras usan `MERGE`. Re-ingerir es determinista y no duplica (US3, FR-009, SC-005). |
| VII | Profundidad antes que amplitud | ✅ PASS | M0 es el cimiento depth-first; se resiste explícitamente el Nivel 2 semántico, el frontend, y toda extracción de entidades, difiriéndolos a sus milestones. |

**Restricciones de stack** (sección "Restricciones técnicas" de la constitución): se
respetan — Python 3.12+, FastAPI + Pydantic v2, Neo4j 5.x, Cypher nombrado en
`backend/graph/`. Sin Qdrant/pgvector. Orquestación (Prefect) y observabilidad completa
se difieren a M8 conforme al roadmap; en M0 basta con logging estructurado básico.

**Resultado del gate: PASS. Sin violaciones que justificar.**

## Project Structure

### Documentation (this feature)

```text
specs/001-m0-ingest-segmentation/
├── plan.md              # Este archivo (/speckit-plan)
├── research.md          # Fase 0 (/speckit-plan)
├── data-model.md        # Fase 1 (/speckit-plan)
├── quickstart.md        # Fase 1 (/speckit-plan)
├── contracts/           # Fase 1 (/speckit-plan)
│   ├── api.md                 # Contrato REST (ingest + inspección)
│   └── graph-schema.cypher    # Constraints/índices y esquema de nodos/relaciones
├── checklists/
│   └── requirements.md  # Checklist de calidad de la spec (ya en verde)
└── tasks.md             # Fase 2 (/speckit-tasks — NO lo crea /speckit-plan)
```

### Source Code (repository root)

```text
docker-compose.yml               # Neo4j 5.x + API (DoD de M0)

backend/
├── ingest/
│   ├── __init__.py
│   ├── models.py                # Pydantic: Manuscript, Chapter, Scene, NonNarrativeBlock
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── base.py              # Protocolo Parser → documento normalizado por bloques
│   │   ├── epub_parser.py       # ebooklib + BeautifulSoup
│   │   ├── txt_parser.py        # texto plano + stripping de boilerplate Gutenberg
│   │   └── docx_parser.py       # python-docx (estilos/alineación)
│   ├── segmentation/
│   │   ├── __init__.py
│   │   ├── chapters.py          # detección de capítulos por formato
│   │   └── scenes.py            # Nivel 0 + Nivel 1 (separadores), determinista
│   ├── non_narrative.py         # detección/marcado de boilerplate, índices, portadas
│   └── pipeline.py              # orquesta parse → segmentar → construir capa cruda
├── graph/
│   ├── __init__.py
│   ├── client.py                # cliente Neo4j (conexión, sesiones)
│   ├── schema.py                # aplica constraints/índices (graph-schema.cypher)
│   └── raw_layer.py             # escritura idempotente (MERGE) y lectura del resumen
├── api/
│   ├── __init__.py
│   ├── app.py                   # FastAPI app
│   └── routes_manuscripts.py    # POST /manuscripts, GET /manuscripts/{id}/structure
└── core/
    ├── __init__.py
    ├── hashing.py               # SHA-256 del contenido normalizado → manuscript_id
    └── errors.py                # errores de dominio (formato no soportado, corrupto…)

eval/
├── fixtures/                    # novelas de dominio público + anotaciones de referencia
│   └── README.md                # procedencia y licencia de cada obra
└── segmentation/
    └── accuracy.py              # cálculo de exactitud capítulo/escena vs anotación

tests/
├── unit/                        # parsers, segmentación, hashing
├── integration/                 # pipeline + Neo4j (docker-compose) + API
└── eval/                        # ejecuta eval/segmentation contra fixtures (gate CI)
```

**Structure Decision**: Servicio backend monorepo siguiendo §11 del README, pero
incluyendo en M0 **solo** los módulos que la segmentación necesita (`ingest`, `graph`,
`api`, `core`) más `eval/` y `tests/`. Los módulos `extraction/`, `retrieval/`, `wiki/`,
`analysis/`, `llm/`, `orchestration/` y `frontend/` se crearán en sus milestones
respectivos. La capa cruda vive en Neo4j desde M0 para establecer el grafo como columna
vertebral (Principio II) y evitar una migración posterior desde un store intermedio.

## Complexity Tracking

> No hay violaciones de la constitución que justificar. M0 pasa el gate sin desviaciones.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
