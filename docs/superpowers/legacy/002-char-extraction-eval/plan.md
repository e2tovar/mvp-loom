# Implementation Plan: M1 — Extracción y resolución de personajes + eval harness

**Branch**: `002-char-extraction-eval` | **Date**: 2026-06-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-char-extraction-eval/spec.md`

## Summary

M1 construye la primera capa de conocimiento sobre la capa cruda de M0: identifica los
**personajes** de un manuscrito ya segmentado, consolida sus menciones (nombres, alias,
títulos) en entidades únicas, registra sus apariciones por escena con **procedencia
rastreable** (escena + fragmento), y persiste todo como nodos `Character` en Neo4j. La
extracción usa un LLM a través de la **única puerta** `backend/llm/` (nueva en M1), con
salidas estructuradas validadas por Pydantic, un **registro de entidades acumulado** que
se pasa como contexto por escena, y cache por hash de contenido para idempotencia. Las
fusiones con confianza bajo umbral **no se aplican**: quedan como casos de revisión
humana consultables y resolubles vía API. La calidad se mide con un **eval harness**
contra un golden dataset anotado (≥2 obras): F1 de detección y B-cubed de resolución,
registrados de forma comparable y actuando como gate de CI.

## Technical Context

**Language/Version**: Python 3.12+

**Primary Dependencies**: FastAPI + Pydantic v2 (contratos de extracción y API),
`neo4j` (driver oficial), `litellm` (motor multi-proveedor, **solo** dentro de
`backend/llm/`), `python-dotenv` (configuración). Sin `instructor` ni LangChain: la
puerta propia usa tool-calling/JSON-schema normalizado por LiteLLM y valida con
Pydantic (Principio III/IV). Proveedores por configuración: OpenCode Go
(OpenAI-compatible, default de desarrollo) y Azure OpenAI (ocasional); ver research R1.

**Storage**: Neo4j 5.x. M1 añade al grafo: `Character`, `Mention` (evidencia),
relaciones `APPEARS_IN`/`MENTIONED_IN` (personaje→escena, con procedencia) y
`MergeCandidate` (cola de revisión). La cache de extracción por escena es
contenido-direccionada en disco (`.cache/extraction/`, gitignored): es estado
operacional, no conocimiento, y no compite con el grafo como fuente de verdad.

**Testing**: `pytest` en tres niveles como en M0 — `unit` (resolución, normalización de
nombres, métricas), `integration` (pipeline + Neo4j + API), `eval` (harness contra el
golden dataset; **gate de CI**). El harness calcula precisión/recall/F1 de detección y
B-cubed de resolución, y compara contra umbrales versionados.

**Target Platform**: Servicio backend local/contenedorizado igual que M0 (Neo4j en
Docker o Desktop, API con uvicorn). La extracción de un libro completo se lanza como
comando CLI (proceso largo); la API expone la inspección y la resolución de fusiones.

**Project Type**: Servicio web (API backend) + CLI de extracción + eval harness.
Monorepo `backend/` + `eval/` + `tests/` según §11 del README.

**Performance Goals**: Extracción completa de una novela de ~120k palabras en
< 30 min (una llamada por escena, map-reduce, sin reprocesos). Coste: con OpenCode Go
el marginal es la cuota mensual; sus límites de gasto ($12/5h) absorben con holgura
las ~61 llamadas de un libro. Azure se reserva para contraste de calidad. Eval completa
en < 10 min sin llamadas LLM (SC-006: compara salida persistida vs anotación).
Re-ejecución sin cambios: < 10 % del coste original (SC-005), servida desde cache.

**Constraints**: Salidas LLM 100 % tipadas (Principio III); todas las llamadas vía
`backend/llm/` (Principio IV); procedencia obligatoria escena+fragmento en cada hecho
(FR-004, preparando `Passage` de M4); fusiones dudosas nunca automáticas (FR-005);
texto del manuscrito tratado como no confiable — defensa de prompt injection (FR-013);
temperatura 0 y cache por hash para máxima reproducibilidad (FR-012).

**Scale/Scope**: Novelas de 50k–200k palabras, 60–200 escenas, repartos de 10–100
personajes con decenas de alias. Golden dataset inicial: *Pride and Prejudice* (61
capítulos) + las obras artesanales de fixtures de M0.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principio | Estado | Cómo lo cumple M1 |
|---|-----------|--------|-------------------|
| I | Eval-first (NO NEGOCIABLE) | ✅ PASS | M1 **es** el milestone que inaugura el eval harness: golden dataset anotado (≥2 obras), F1 de detección, B-cubed de resolución, resultados versionados y gate de CI (US2, FR-008..011, SC-001/002/007). |
| II | El grafo es la columna vertebral | ✅ PASS | `Character`, `Mention` y apariciones viven en Neo4j enlazados a las `Scene` de M0. La cache de disco es operacional (resultados crudos por escena), nunca se consulta como conocimiento. |
| III | Contratos tipados (Pydantic) | ✅ PASS | La extracción devuelve modelos Pydantic validados vía tool-use/JSON-schema; ningún parsing de texto libre (FR-007). |
| IV | Una sola puerta al LLM | ✅ PASS | M1 crea `backend/llm/` (interfaz agnóstica + implementación LiteLLM multi-proveedor: OpenCode Go / Azure OpenAI por env). LiteLLM solo se importa ahí; `extraction/` consume la interfaz y nunca sabe qué proveedor responde. |
| V | Citas obligatorias (anclaje en Passage) | ✅ PASS (adaptado) | M1 no emite afirmaciones analíticas; los hechos extraídos llevan procedencia obligatoria `scene_id` + offsets/cita del fragmento (FR-004, SC-004). Los nodos `Passage` con embeddings llegan en M4; los offsets de M1 son convertibles a `Passage` sin re-extracción. |
| VI | Idempotencia y cache por hash | ✅ PASS | Cache por SHA-256(texto de escena + versión de prompt + modelo + versión de esquema); escrituras `MERGE` idempotentes; re-ejecutar sin cambios no llama al LLM (US4, FR-012, SC-005). |
| VII | Profundidad antes que amplitud | ✅ PASS | Solo personajes: sin relaciones, atributos, eventos ni `knows/unaware_of` (M2+). Sin embeddings ni recuperación (M4). Sin UI de revisión (M7): la cola se opera vía API. |

**Restricciones de stack**: Python 3.12+, FastAPI + Pydantic v2, Neo4j 5.x, Cypher
nombrado en `backend/graph/` — todo se respeta. **Desviación consciente**: la
constitución pide orquestación con estado (Prefect/Temporal) para el pipeline largo;
M1 lo difiere a M8 (igual que M0) usando un pipeline secuencial **reanudable por la
cache por escena** (cada escena es un checkpoint). Justificación en Complexity
Tracking.

**Resultado del gate: PASS con una desviación justificada (orquestación diferida).**

## Project Structure

### Documentation (this feature)

```text
specs/002-char-extraction-eval/
├── plan.md              # Este archivo (/speckit-plan)
├── research.md          # Fase 0 (/speckit-plan)
├── data-model.md        # Fase 1 (/speckit-plan)
├── quickstart.md        # Fase 1 (/speckit-plan)
├── contracts/           # Fase 1 (/speckit-plan)
│   ├── api.md                 # Contrato REST (personajes, merge candidates) + CLI
│   ├── extraction-schema.md   # Contratos Pydantic de la salida del LLM
│   └── graph-schema.cypher    # Delta de esquema: Character, Mention, MergeCandidate
├── checklists/
│   └── requirements.md  # Checklist de calidad de la spec (en verde)
└── tasks.md             # Fase 2 (/speckit-tasks — NO lo crea /speckit-plan)
```

### Source Code (repository root)

```text
backend/
├── llm/                             # NUEVO — la única puerta al LLM (Principio IV)
│   ├── __init__.py
│   ├── interface.py                 # Protocolo LLMClient: complete_structured(schema) → Pydantic
│   ├── litellm_client.py            # implementación LiteLLM (tool-calling forzado, temperature 0,
│   │                                #   proveedor por env: OpenCode Go / Azure / compatible-OpenAI)
│   └── cache.py                     # cache contenido-direccionada de respuestas
├── extraction/                      # NUEVO — extracción y resolución de personajes
│   ├── __init__.py
│   ├── schemas.py                   # Pydantic: SceneExtraction, MentionOut, CharacterCandidate
│   ├── prompts.py                   # prompt de extracción versionado (PROMPT_VERSION)
│   ├── registry.py                  # registro acumulado de entidades (contexto entre escenas)
│   ├── resolution.py                # normalización, matching, confianza, decisión merge/queue
│   ├── pipeline.py                  # orquesta: escenas → LLM → resolución → grafo (reanudable)
│   └── run.py                       # CLI: python -m backend.extraction.run <manuscript_id>
├── graph/
│   ├── characters.py                # NUEVO — escritura/lectura idempotente de Character/Mention
│   ├── merge_candidates.py          # NUEVO — cola de revisión: crear, listar, resolver
│   └── schema.py                    # + constraints/índices de M1
└── api/
    └── routes_characters.py         # NUEVO — GET characters, GET/POST merge-candidates

eval/
├── fixtures/
│   ├── *.characters.gold.json      # NUEVO — golden dataset de personajes por obra
│   └── README.md                    # + procedencia de las anotaciones
└── characters/                      # NUEVO — harness de M1
    ├── __init__.py
    ├── metrics.py                   # precision/recall/F1 detección; B-cubed resolución
    ├── runner.py                    # carga gold + salida del sistema → reporte comparable
    └── thresholds.py                # umbrales versionados (F1 ≥ 0.90, B³ ≥ 0.85)

tests/
├── unit/                            # resolución, normalización, métricas, registry
├── integration/                     # pipeline con LLM falso + Neo4j + API
└── eval/                            # gate CI: harness vs golden dataset
```

**Structure Decision**: Se crean exactamente los dos módulos nuevos que M1 exige
(`backend/llm/`, `backend/extraction/`) más el harness `eval/characters/`, siguiendo
§11 del README. `retrieval/`, `wiki/`, `analysis/`, `orchestration/` y `frontend/`
siguen difiriéndose a sus milestones. La extracción se lanza por CLI (proceso largo,
minutos); la API solo expone inspección y resolución de fusiones — así el contrato REST
se mantiene rápido y sin jobs asíncronos prematuros.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Orquestación con estado (Prefect/Temporal) diferida a M8; M1 usa pipeline secuencial reanudable por cache | Adoptar Prefect hoy añade infraestructura (server/agente, deployment) que no aporta al DoD de M1; la cache por escena ya da checkpoints y reanudación (re-lanzar el CLI continúa donde falló sin re-coste) | "Adoptarlo ya" se rechaza por Principio VII (profundidad): el esfuerzo de M1 debe ir a la calidad de extracción y al eval, no a infraestructura de workflow que M8 instalará con requisitos reales (puertas humanas, multi-libro) |
