# Data Model — M0: Capa cruda (capítulos y escenas)

**Feature**: `001-m0-ingest-segmentation` · **Fecha**: 2026-06-04

La capa cruda se modela en dos representaciones que deben mantenerse coherentes:

1. **Contrato Pydantic v2** (`backend/ingest/models.py`) — la salida validada del
   pipeline de ingestión, antes de escribir al grafo (Principio III).
2. **Esquema de grafo Neo4j** (`backend/graph/`, ver `contracts/graph-schema.cypher`) —
   la persistencia, única fuente de verdad (Principio II).

Solo se incluyen las entidades necesarias para M0. El esquema completo del README
(`Event`, `PlotThread`, `Theme`, `Attribute`, `Passage`, `CommunitySummary`, etc.) llega
en milestones posteriores y no se materializa aquí.

---

## Entidades

### Manuscript

La fuente inmutable. Su identidad deriva del contenido (D6).

| Campo | Tipo | Reglas / Notas |
|-------|------|----------------|
| `manuscript_id` | `str` | SHA-256 del contenido narrativo normalizado. Clave primaria. Determinista (FR-009, SC-005). |
| `title` | `str \| None` | Título de la obra si se puede determinar del contenedor/encabezado. |
| `source_format` | `Literal["epub","txt","docx"]` | Formato de origen (FR-001). |
| `word_count` | `int` | Conteo total de palabras narrativas. `≥ 0`. |
| `chapter_count` | `int` | Número de capítulos. `≥ 1` para un manuscrito válido. |
| `ingested_at` | `datetime` | Marca de ingestión (metadato operativo; **no** entra en el hash). |

**Reglas**:
- Un `Manuscript` válido tiene `chapter_count ≥ 1` (FR-002); si no se detectan
  encabezados, hay un capítulo único (edge case "sin marcadores").
- Re-ingerir el mismo contenido produce el mismo `manuscript_id` (idempotencia).

---

### Chapter

Unidad estructural de primer nivel.

| Campo | Tipo | Reglas / Notas |
|-------|------|----------------|
| `chapter_id` | `str` | `{manuscript_id}:c{order_narrative}` — estable y derivado. |
| `order_narrative` | `int` | Orden de lectura, base 0 o 1 consistente. Único dentro del manuscrito. Monótono creciente. |
| `title` | `str \| None` | Título si existe (FR-002). |
| `kind` | `Literal["chapter","prologue","epilogue","interlude","other"]` | Conserva unidades no estándar en su orden (FR-012). Default `"chapter"`. |
| `word_count` | `int` | `≥ 0`. |
| `start_offset` | `int` | Offset de inicio en el texto narrativo normalizado (FR-005). |
| `end_offset` | `int` | Offset de fin. `end_offset > start_offset`. |

**Reglas**:
- Los `order_narrative` de los capítulos de un manuscrito forman una secuencia sin
  huecos ni duplicados.
- `[start_offset, end_offset)` de capítulos consecutivos no se solapan.

---

### Scene

Unidad mínima de la capa cruda; vive dentro de un capítulo.

| Campo | Tipo | Reglas / Notas |
|-------|------|----------------|
| `scene_id` | `str` | `{chapter_id}:s{order_in_chapter}`. |
| `order_in_chapter` | `int` | Orden dentro del capítulo (base consistente). |
| `order_narrative_global` | `int` | Orden de la escena en todo el manuscrito (FR-003). Único y monótono. |
| `text` | `str` | Texto narrativo íntegro de la escena (FR-008). No incluye el separador. |
| `char_count` | `int` | `len(text)`, `≥ 0`. |
| `start_offset` | `int` | Offset de inicio en el texto narrativo normalizado (FR-005). |
| `end_offset` | `int` | `end_offset > start_offset`. |
| `boundary_reason` | `Literal["chapter_start","separator"]` | Por qué empieza aquí: Nivel 0 (`chapter_start`) o Nivel 1 (`separator`). |
| `snippet` | `str` | Primeras N (p. ej. 120) caracteres, para el resumen inspeccionable (FR-010). Derivado de `text`. |

**Reglas**:
- La primera escena de cada capítulo tiene `boundary_reason = "chapter_start"`.
- Concatenar el `text` de todas las escenas de un capítulo (en orden) reconstruye el
  texto narrativo del capítulo salvo los separadores eliminados (base de SC-004).
- `order_narrative_global` es consistente con el orden de capítulos y escenas.

---

### NonNarrativeBlock

Contenido detectado como no narrativo (licencia, índice, portada). Se conserva marcado,
nunca contamina capítulos/escenas (FR-007, SC-007).

| Campo | Tipo | Reglas / Notas |
|-------|------|----------------|
| `block_id` | `str` | `{manuscript_id}:nn{order}`. |
| `kind` | `Literal["license","toc","cover","frontmatter","backmatter","other"]` | Tipo detectado. |
| `text` | `str` | Texto del bloque (conservado para trazabilidad). |
| `detected_by` | `str` | Regla que lo marcó (p. ej. `"gutenberg_marker"`, `"toc_heuristic"`). |
| `position` | `Literal["before","between","after"]` | Posición relativa a la narrativa. |

---

## Relaciones (Neo4j)

Subconjunto de §5 del README necesario para M0:

```
(Manuscript)-[:HAS_CHAPTER]->(Chapter)
(Chapter)-[:HAS_SCENE]->(Scene)
(Chapter)-[:NEXT_CHAPTER]->(Chapter)     // orden narrativo de capítulos
(Scene)-[:NEXT_SCENE]->(Scene)           // orden narrativo global de escenas
(Manuscript)-[:HAS_NON_NARRATIVE]->(NonNarrativeBlock)
```

- `NEXT_CHAPTER` y `NEXT_SCENE` materializan el orden de lectura para recorridos baratos.
- Las relaciones se escriben de forma idempotente (`MERGE`); re-ingerir no las duplica.

---

## Invariantes de integridad (verificables en tests)

- **INV-1 (determinismo)**: dos ingestiones del mismo contenido producen grafos
  isomorfos con los mismos ids (SC-005).
- **INV-2 (sin pérdida)**: el texto narrativo reconstruido desde las escenas coincide
  con el original menos separadores y bloques no narrativos (SC-004).
- **INV-3 (orden total)**: `order_narrative_global` de las escenas es una permutación
  `0..N-1` sin huecos, coherente con el orden de capítulos.
- **INV-4 (no contaminación)**: ningún `Scene.text` contiene texto de un
  `NonNarrativeBlock` (SC-007).
- **INV-5 (capítulo mínimo)**: todo `Manuscript` válido tiene `chapter_count ≥ 1` y cada
  capítulo tiene `≥ 1` escena.

---

## Notas de evolución (fuera de M0)

> **Desfasado — revisar contra README §5 y §12 (roadmap revisado el 2026-08-02).**
> Estas notas se escribieron durante M0 y anticipaban un modelo que ya no es el vigente.
> Se conservan como registro; lo que sigue en vigor está marcado abajo.

- ~~`Scene` ganará `summary`, `tension_score`, `sentiment`, `time_marker`, `pov_character`~~
  → **vigente**: `Scene` ganará `summary` (jerárquico), `place` y `time_marker` en M6.
  `tension_score`, `sentiment` y `pov_character` fueron **descartados** del modelo.
- Aparecerá `Passage` (texto + embedding, índice vectorial) como unidad de recuperación
  y fuente de citas (**M4**, adelantado desde M5); las `Scene` de M0 ya guardan los
  offsets que lo habilitan. **Sigue en vigor.**
- La identidad por hash de M0 se reutiliza para el re-procesamiento incremental
  diff-aware (**M8/M11** en la numeración nueva). **Sigue en vigor.**
