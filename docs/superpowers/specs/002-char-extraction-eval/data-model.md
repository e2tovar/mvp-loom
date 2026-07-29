# Data Model — M1: Personajes, menciones y cola de revisión

**Feature**: `002-char-extraction-eval` · **Fecha**: 2026-06-10

Tres representaciones que deben mantenerse coherentes:

1. **Contrato Pydantic de extracción** (`backend/extraction/schemas.py`) — lo que el
   LLM devuelve por escena, validado (Principio III). Ver
   [contracts/extraction-schema.md](./contracts/extraction-schema.md).
2. **Modelos de dominio** (`backend/extraction/`) — entidades resueltas tras la
   cascada de resolución.
3. **Esquema de grafo Neo4j** (`backend/graph/`, ver
   [contracts/graph-schema.cypher](./contracts/graph-schema.cypher)) — persistencia,
   única fuente de verdad (Principio II).

Se construye **sobre** la capa cruda de M0 (`Manuscript`/`Chapter`/`Scene`): ningún
nodo de M0 se modifica; M1 solo añade nodos y relaciones nuevos.

---

## Entidades

### Character

Entidad de conocimiento: un personaje de la obra con identidad consolidada.

| Campo | Tipo | Reglas / Notas |
|-------|------|----------------|
| `character_id` | `str` | `{manuscript_id}:ch:{slug}` donde `slug` deriva del nombre canónico normalizado de la **primera aparición**. Estable entre re-ejecuciones (FR-012). |
| `canonical_name` | `str` | Nombre canónico (la designación más completa/informativa vista). |
| `aliases` | `list[str]` | Todas las designaciones consolidadas (nombres, diminutivos, títulos, descripciones resolubles). Sin duplicados, no incluye `canonical_name`. |
| `role` | `Literal["protagonist","antagonist","secondary","minor","unknown"]` | Rol aproximado; refinable, default `"unknown"`. |
| `is_mentioned_only` | `bool` | `True` si el personaje jamás aparece en escena (solo se habla de él) (edge case "solo mencionados"). |
| `first_scene_id` | `str` | Escena de primera aparición/mención — procedencia de la entidad (FR-004). |
| `appearance_count` | `int` | Nº de escenas con presencia. Derivado, `≥ 0`. |
| `mention_count` | `int` | Nº total de menciones. Derivado, `≥ 1`. |

**Reglas**:
- Un `Character` existe solo si lo sustenta ≥ 1 `Mention` (sin menciones, no hay
  entidad — nada se inventa).
- `character_id` es determinista: re-extraer sin cambios converge al mismo id (INV-M1-1).
- Las menciones colectivas ("los soldados") **no** generan `Character`.

### Mention

Evidencia: una ocurrencia concreta de un personaje en el texto. Es la unidad sobre la
que se mide la resolución (B-cubed) y la base de la procedencia.

| Campo | Tipo | Reglas / Notas |
|-------|------|----------------|
| `mention_id` | `str` | `{scene_id}:m{start_offset}` — determinista por posición. |
| `surface` | `str` | Texto literal de la mención ("Eli", "la doctora"). |
| `kind` | `Literal["name","alias","title","description","pronoun_resolved"]` | Tipo de designación. |
| `scene_id` | `str` | Escena de origen (FK a capa cruda). |
| `start_offset` | `int` | Offset dentro del `text` de la escena. `≥ 0`. |
| `end_offset` | `int` | `end_offset > start_offset`. El fragmento `text[start:end]` debe contener `surface` (verificable). |
| `quote` | `str` | Fragmento de contexto (la frase que contiene la mención) — la "cita" de M1, convertible a `Passage` en M4 (FR-004, SC-004). |

**Reglas**:
- Toda `Mention` pertenece a exactamente un `Character` (tras resolución) y exactamente
  una `Scene`.
- Los offsets anclan la mención al texto inmutable de M0: la procedencia es verificable
  contra la capa cruda (SC-004).

### Appearance (relación con propiedades)

Vínculo personaje→escena. Se materializa como relación, no como nodo.

| Propiedad | Tipo | Reglas / Notas |
|-----------|------|----------------|
| `kind` | `Literal["appears","mentioned"]` | Presencia física en escena vs solo nombrado (FR-003). |
| `mention_count` | `int` | Menciones del personaje en esa escena. `≥ 1`. |
| `first_mention_id` | `str` | Procedencia: primera mención en la escena (FR-004). |

### MergeCandidate

Caso de fusión dudosa pendiente de decisión humana (FR-005, US3).

| Campo | Tipo | Reglas / Notas |
|-------|------|----------------|
| `candidate_id` | `str` | `{manuscript_id}:mc:{slug_a}+{slug_b}` — determinista, no se duplica al re-ejecutar. |
| `character_a_id` | `str` | Entidad A (orden lexicográfico de slugs para estabilidad). |
| `character_b_id` | `str` | Entidad B. |
| `confidence` | `float` | Confianza del sistema en que son la misma entidad. `0.5 ≤ c < 0.9` (zona gris configurable). |
| `rationale` | `str` | Explicación del sistema (por qué podrían ser la misma). |
| `evidence` | `list[dict]` | Menciones/escenas/citas de ambas entidades, suficiente para decidir (US3-AC2). |
| `status` | `Literal["pending","accepted","rejected"]` | Estado del caso. Default `"pending"`. |
| `resolved_at` | `datetime \| None` | Marca de decisión (metadato operativo). |

**Transiciones de estado**:

```
pending ──accept──▶ accepted   (se aplica el merge: menciones, apariciones y alias
                                de B pasan a A; B se elimina; decisión persistida)
pending ──reject──▶ rejected   (las entidades quedan separadas permanentemente;
                                re-ejecuciones NO vuelven a proponer este par)
```

- Las decisiones humanas son **inmutables ante el pipeline**: una re-extracción jamás
  re-fusiona un par rechazado ni separa un merge aceptado (FR-012 + FR-005).

### CharacterGold (eval, fuera del grafo)

Anotación de referencia por obra, en `eval/fixtures/<obra>.characters.gold.json`:

```json
{
  "work": "pride-and-prejudice",
  "annotation_criteria": "vínculo a eval/fixtures/README.md",
  "characters": [
    {
      "gold_id": "elizabeth-bennet",
      "canonical_name": "Elizabeth Bennet",
      "aliases": ["Lizzy", "Eliza", "Miss Bennet", "Miss Elizabeth"],
      "role": "protagonist",
      "is_mentioned_only": false,
      "appearances": ["c1/s0", "c2/s0"]
    }
  ]
}
```

- `appearances` usa coordenadas estructurales (`c{chapter_order}/s{scene_order}`) en
  vez de ids de hash, para que la anotación sobreviva a re-ingestas.

### EvalResult (eval, fuera del grafo)

Salida de una ejecución del harness, en `eval/results/`:

| Campo | Tipo | Notas |
|-------|------|-------|
| `work` | `str` | Obra evaluada. |
| `run_at`, `git_sha`, `prompt_version`, `model` | `str` | Reproducibilidad (FR-010). |
| `detection` | `{precision, recall, f1}` | SC-001. |
| `resolution_b3` | `{precision, recall, f1}` | SC-002. |
| `silent_bad_merges` | `int` | Pares del gold fusionados sin pasar por la cola — debe ser 0 (SC-003). |
| `thresholds` | `{detection_f1, resolution_f1}` | Umbrales vigentes al ejecutar. |
| `passed` | `bool` | Gate (SC-007). |

---

## Relaciones (Neo4j)

```
(Manuscript)-[:HAS_CHARACTER]->(Character)
(Character)-[:APPEARS_IN {kind, mention_count, first_mention_id}]->(Scene)
(Character)-[:HAS_MENTION]->(Mention)
(Mention)-[:IN_SCENE]->(Scene)
(MergeCandidate)-[:PROPOSES_MERGE]->(Character)    // x2 (entidades A y B)
(Manuscript)-[:HAS_MERGE_CANDIDATE]->(MergeCandidate)
```

- `APPEARS_IN` con `kind` preserva la distinción aparece/mencionado (FR-003) —
  alineado con el esquema objetivo del README §5.
- Todas las escrituras son `MERGE` por id determinista: re-ejecutar converge al mismo
  grafo (FR-012).

---

## Invariantes de integridad (verificables en tests)

- **INV-M1-1 (determinismo)**: dos extracciones del mismo manuscrito (cache caliente)
  producen el mismo conjunto de `character_id` y `mention_id`.
- **INV-M1-2 (procedencia total)**: todo `Character` tiene `first_scene_id` válido y
  toda `Mention` tiene offsets verificables contra el `text` de su `Scene` (SC-004).
- **INV-M1-3 (sin huérfanos)**: todo `Character` tiene ≥ 1 `Mention`; toda `Mention`
  pertenece a exactamente un `Character`.
- **INV-M1-4 (no fusión silenciosa)**: ningún par de `Character` con
  `MergeCandidate.status = "rejected"` aparece fusionado tras una re-ejecución; ningún
  merge en zona gris se aplica sin `status = "accepted"` (SC-003).
- **INV-M1-5 (capa cruda intacta)**: M1 no modifica ninguna propiedad de
  `Manuscript`/`Chapter`/`Scene`/`NonNarrativeBlock`.

---

## Notas de evolución (fuera de M1)

- `Character` ganará `knows/unaware_of`, `open_wounds`, `status` (alive/dead/...) y
  `voice_profile` en M2+ (continuidad y relaciones), según el teardown de prior art.
- `Mention.quote` + offsets son el precursor directo de `Passage` (M4): la conversión
  no requiere re-extraer.
- `RELATES_TO` entre personajes llega en M2; M1 no extrae relaciones.
