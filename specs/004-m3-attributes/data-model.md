# Data Model — M3: Atributos de personaje

**Feature**: `004-m3-attributes` · **Fecha**: 2026-07-19

Mismo triple contrato que M1/M2, que debe mantenerse coherente:

1. **Contrato Pydantic de extracción** (`backend/extraction/attributes/schemas.py`) —
   lo que el LLM devuelve por escena, validado.
2. **Agregación de dominio** (`backend/extraction/attributes/aggregation.py`) —
   evidencias → nodos de atributo, reglas deterministas sin LLM.
3. **Esquema de grafo Neo4j** (`backend/graph/attributes.py`) — persistencia.

Se construye **sobre** las capas M0 (`Manuscript`/`Chapter`/`Scene`), M1
(`Character`/`Mention`/`APPEARS_IN`) y M2 (`RELATES_TO`/`RelationEvidence`):
ningún nodo previo se modifica; M3 solo añade. M3 **lee** de M1: el cast por
escena sale de `APPEARS_IN` (presentes y mencionados), filtrando
`entity_kind = "person"` — igual que M2, los animales no participan.

A DIFERENCIA de M2 (que agrega a un `rel_type` dominante por par), M3 **no
colapsa**: cada `value_norm` distinto de un (personaje, `key`) produce su
propio nodo `Attribute`. Esa multiplicidad es la señal que consumirá el futuro
detector de continuidad (`docs/graph-north.md` §2).

---

## Catálogo cerrado de `key`

`AttrKey = Literal["eye_color", "hair", "height", "scar", "age", "gender", "status"]`
(`backend/extraction/attributes/schemas.py`). Un `key` fuera del catálogo se
rechaza en validación (FR-002).

Cada `key` tiene una **clase**, calculada por `key_class(key)`:

| Clase | Keys | Semántica |
|-------|------|-----------|
| `static` | `eye_color`, `hair`, `height`, `scar`, `age`, `gender` | Comparable por igualdad; un valor distinto en otra escena es candidato a gazapo. |
| `stateful` | `status` | Comparable por **transición** (p. ej. vivo→muerto), no por igualdad. |

La clase se persiste en el nodo `Attribute` (`attr_class`); la **lógica** de
comparación/transición queda fuera de esta spec — la aplica el detector de
continuidad posterior (FR-004, FR-017).

---

## Entidades

### AttributeEvidence (nodo)

El hecho crudo: un atributo afirmado de un personaje en una escena. Es al
atributo lo que `Mention` es a `Character` y `RelationEvidence` a `RELATES_TO`.

| Campo | Tipo | Reglas / Notas |
|-------|------|----------------|
| `evidence_id` | `str` | `{scene_id}:ae:{digest}` — `digest` = sha256(`character_id::key`)[:16]. Determinista (máx. 1 evidencia por (personaje, key) por escena). |
| `manuscript_id` | `str` | FK al manuscrito. |
| `scene_id` | `str` | Escena de origen (FK a capa cruda). |
| `character_id` | `str` | Personaje afirmado. Debe existir en la capa M1 y pertenecer al cast de la escena. |
| `key` | `AttrKey` | Catálogo cerrado (ver arriba). |
| `value_norm` | `str` | Valor normalizado (token canónico, independiente del idioma), en minúsculas y sin espacios sobrantes (`field_validator` de Pydantic). |
| `value_quote` | `str` | Cita literal de la escena que sustenta el valor (procedencia). |
| `confidence` | `float` | `[0,1]`. |

**Reglas**:
- El personaje debe pertenecer al **cast entregado al LLM** para esa escena
  (presentes o mencionados vía `APPEARS_IN`). Referencia fuera del cast →
  rechazo en validación (FR-001, SC-003).
- Máximo una evidencia por (personaje, `key`) por escena: el LLM consolida las
  señales de la escena. Dos escenas distintas con el mismo (personaje, `key`)
  y `value_norm` distinto producen dos evidencias — eso es lo esperado.
- El contrato Pydantic (`SceneAttributeEvidence`) valida todo lo anterior antes
  de aceptar la salida del modelo.

### Attribute (nodo agregado)

Un valor afirmado de un (personaje, `key`), con sus evidencias. Nunca colapsa:
un mismo (personaje, `key`) con `N` valores distintos produce `N` nodos.

| Campo | Tipo | Reglas / Notas |
|-------|------|----------------|
| `attribute_id` | `str` | `{character_id}:attr:{key}:{digest}` — `digest` = sha256(`value_norm`)[:16]. Determinista por (personaje, key, valor). |
| `manuscript_id` | `str` | FK al manuscrito. |
| `character_id` | `str` | Personaje. |
| `key` | `AttrKey` | Catálogo cerrado. |
| `value_norm` | `str` | El valor normalizado que este nodo representa. |
| `attr_class` | `Literal["static","stateful"]` | `key_class(key)`, persistida. |
| `confidence` | `float` | Máxima entre las evidencias de este (personaje, key, valor). |
| `evidence_count` | `int` | Nº de evidencias de este (personaje, key, valor). `≥ 1`. |
| `first_evidence_id` | `str` | Procedencia: `evidence_id` de la primera evidencia en orden narrativo. |

**Reglas de agregación** (`aggregate_character_attributes`, deterministas,
recomputables desde las evidencias, sin umbral de escritura — se escribe
siempre y la confianza queda como dato, para no ocultar un posible gazapo):

1. Agrupar evidencias por `(character_id, key, value_norm)` — la clave exacta,
   sin fusionar valores distintos.
2. `confidence` del nodo: máxima confianza entre las evidencias del grupo.
3. `evidence_count`: tamaño del grupo.
4. `first_evidence_id`: `evidence_id` de la evidencia con menor
   `narrative_order` (orden de escena) del grupo.
5. `attr_class`: `key_class(key)`, no depende del grupo.

### AttributesGold (eval, fuera del grafo)

`eval/fixtures/<obra>.attributes.gold.json` — referencia por obra. Reusa los
`gold_id` de personaje (`character`) del gold de M1 (`<obra>.characters.gold.json`):

```json
{
  "work": "crafted-attributes.txt",
  "annotation_criteria": "eval/fixtures/README.md#attributes",
  "attributes": [
    {"character": "ana", "key": "eye_color", "value_norm": "green", "class": "static"},
    {"character": "ana", "key": "eye_color", "value_norm": "blue", "class": "static"},
    {"character": "daniel", "key": "status", "value_norm": "dead", "class": "stateful"}
  ]
}
```

Nótese que el gold usa la clave `class` (no `attr_class`); el harness lee
`g["class"]` del gold y `p["attr_class"]` de la predicción — son campos
distintos con el mismo significado, no un error de naming (verificado en
`eval/attributes/metrics.py`).

### EvalResult (eval, fuera del grafo)

`eval/results/attributes-<obra>-<fecha>-<sha>.json`:

| Campo | Tipo | Notas |
|-------|------|-------|
| `work`, `run_at`, `git_sha`, `prompt_version`, `model` | `str` | Reproducibilidad. |
| `triple_detection` | `{precision, recall, f1}` × {static, stateful, all} | SC-001; tripletas `(character_id, key, value_norm)`. |
| `thresholds` | `{triple_detection_f1}` | Umbral vigente (0.90). |
| `passed` | `bool` | Gate sobre el F1 de `all` (`eval/attributes/thresholds.py`). |

La cita literal (`value_quote`) no se evalúa en el gate (FR-010): la métrica
compara solo la tripleta `(personaje, key, value_norm)`.

---

## Relaciones (Neo4j, delta — solo añade)

```
(c:Character)-[:HAS_ATTRIBUTE]->(a:Attribute)
(ae:AttributeEvidence)-[:ABOUT]->(:Character)      // exactamente 1
(ae:AttributeEvidence)-[:IN_SCENE]->(:Scene)
(Manuscript)-[:HAS_ATTRIBUTE_EVIDENCE]->(ae)
```

- Constraint: `Attribute.attribute_id` UNIQUE, `AttributeEvidence.evidence_id`
  UNIQUE. Índices por `manuscript_id` (ambos nodos) y por `scene_id`
  (`AttributeEvidence`).
- Escritura de evidencias: `MERGE` por id determinista — re-ejecutar converge
  al mismo grafo.
- Escritura de atributos: los nodos `Attribute` son **derivados** de las
  evidencias, igual que `RELATES_TO` en M2 — se borran y reescriben en cada
  agregación (`replace_attributes`), para que un valor que dejó de afirmarse en
  una re-agregación no deje nodo fantasma.

---

## Data flow

```
Grafo M1 (Character + APPEARS_IN)  ── solo lectura ──┐
                                                      ▼
por escena (orden narrativo):
  texto escena + cast (ids + nombres/alias) ──▶ LLM ──▶ SceneAttributeEvidence[]
  · cache por hash(escena + cast + versión prompt + versión schema)
  · validación: key del catálogo cerrado, personaje dentro del cast,
    máx 1 evidencia por (personaje, key) por escena
                                                      ▼
agregación determinista por (personaje, key, value_norm) ──▶ Attribute (siempre)
                                                      ▼
backend/graph/attributes.py ──▶ MERGE evidencias + replace_attributes (borra+reescribe)
```

Fallo de escena tras N reintentos → log + skip; la agregación opera con lo
disponible (FR-016). Manuscrito sin capa M1 → error explícito (`NotExtractedError`,
FR-015).

---

## Invariantes de integridad (verificables en tests)

- **INV-M3-1 (sustento)**: toda `Attribute` tiene ≥ 1 `AttributeEvidence` del
  mismo (personaje, `key`, `value_norm`); toda evidencia referencia 1
  `Character` y 1 `Scene` existentes.
- **INV-M3-2 (determinismo)**: dos extracciones del mismo manuscrito (cache
  caliente) producen el mismo conjunto de `evidence_id` y los mismos nodos
  `Attribute`.
- **INV-M3-3 (capas previas intactas)**: M3 no modifica ninguna propiedad de
  nodos M0/M1/M2.
- **INV-M3-4 (universo cerrado)**: ninguna evidencia ni atributo referencia un
  `character_id` fuera del cast del manuscrito (SC-003).
- **INV-M3-5 (no colapso)**: todo (personaje, `key`) con ≥ 2 `value_norm`
  distintos conserva un nodo `Attribute` por valor — cero colapsos (SC-004).

---

## Notas de evolución (fuera de M3)

- **Detección de continuidad**: consumidor posterior (`analysis/`) que lee
  `Attribute` + `AttributeEvidence` ya poblados; aplica semántica de igualdad
  (`static`) o transición (`stateful`), genera alertas. No es parte de esta
  spec (FR-017).
- **Vocabulario controlado por `key`**: hoy `value_norm` es normalización
  libre del LLM; si la primera medición muestra fallos de casamiento
  ("azul"/"azulado"/"blue"), se promueve a vocabulario controlado por `key`
  (Open Question de `spec.md`).
- **Ampliar el catálogo**: atributos mutables (posesiones, títulos, ubicación)
  quedaron fuera para no alimentar de ruido al futuro detector; es un cambio
  de catálogo (`AttrKey`), no de modelo.
