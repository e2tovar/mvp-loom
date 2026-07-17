# Data Model — M2: Relaciones entre personajes

**Feature**: `003-m2-relations` · **Fecha**: 2026-07-17

Mismo triple contrato que M1, que debe mantenerse coherente:

1. **Contrato Pydantic de extracción** (`backend/extraction/relations/schemas.py`) —
   lo que el LLM devuelve por escena, validado.
2. **Agregación de dominio** (`backend/extraction/relations/`) — evidencias → relación
   agregada, reglas deterministas sin LLM.
3. **Esquema de grafo Neo4j** (`backend/graph/relations.py`) — persistencia.

Se construye **sobre** las capas M0 (`Manuscript`/`Chapter`/`Scene`) y M1
(`Character`/`Mention`/`APPEARS_IN`): ningún nodo previo se modifica; M2 solo añade.
M2 **lee** de M1: el cast por escena sale de `APPEARS_IN` (presentes y mencionados),
filtrando `entity_kind = "person"` — los animales no participan en relaciones en M2.

---

## Entidades

### RelationEvidence (nodo)

El hecho crudo: señal de relación entre un par de personajes en una escena. Es a la
relación lo que `Mention` es a `Character`.

| Campo | Tipo | Reglas / Notas |
|-------|------|----------------|
| `evidence_id` | `str` | `{scene_id}:re:{slug_a}+{slug_b}` — slugs de `character_id` en orden lexicográfico. Determinista (máx. 1 evidencia por par por escena). |
| `character_a_id` | `str` | Personaje A (orden lexicográfico). Debe existir en la capa M1. |
| `character_b_id` | `str` | Personaje B. `a ≠ b`. |
| `rel_type` | `Literal["family","romantic","friendship","antagonism","professional","social","other"]` | Catálogo cerrado. |
| `descriptor` | `str` | Libre corto (≤ ~10 palabras): "tío y tutor". |
| `role_a` / `role_b` | `str \| None` | Roles cuando la relación es asimétrica ("padre"/"hija"). |
| `provenance` | `Literal["extracted","inferred"]` | Enunciada en la prosa vs deducida de la interacción. |
| `confidence` | `float` | `[0,1]`. |
| `quote` | `str` | Frase literal de la escena que sustenta la evidencia (procedencia). |
| `scene_id` | `str` | Escena de origen (FK a capa cruda). |

**Reglas**:
- Ambos personajes deben pertenecer al **cast entregado al LLM** para esa escena
  (presentes o mencionados vía `APPEARS_IN`, más los enunciados a distancia validados
  contra el cast del manuscrito). Referencia fuera del cast → rechazo en validación.
- Máximo una evidencia por par por escena: el LLM consolida las señales de la escena.
- El contrato Pydantic (`SceneRelationEvidence`) valida todo lo anterior antes de
  aceptar la salida del modelo.

### RELATES_TO (arista agregada)

La relación consolidada del par. Una sola arista por par, dirección de almacenamiento
canónica (orden lexicográfico de `character_id`), semánticamente simétrica.

| Propiedad | Tipo | Reglas / Notas |
|-----------|------|----------------|
| `rel_type` | enum (ver arriba) | Tipo dominante según reglas de agregación. |
| `descriptor` | `str` | El de la evidencia de mayor confianza del tipo ganador. |
| `role_a` / `role_b` | `str \| None` | Primeros no nulos del tipo ganador; conflicto → vacíos (no adivinar). |
| `provenance` | enum | `extracted` si ≥ 1 evidencia extracted del tipo ganador; si no `inferred`. |
| `confidence` | `float` | Máxima entre las evidencias del tipo ganador. |
| `evidence_count` | `int` | Nº de evidencias del par (todas, no solo el tipo ganador). `≥ 1`. |
| `first_evidence_id` | `str` | Procedencia de la arista: primera evidencia en orden narrativo. |

**Reglas de agregación** (deterministas, recomputables desde las evidencias):

1. `rel_type`: mayor peso de evidencias, con `extracted` × 2 sobre `inferred`;
   empate → tipo de la evidencia extracted más tardía en orden narrativo.
2. `descriptor`: el de mayor confianza dentro del tipo ganador.
3. Roles: primeros no nulos del tipo ganador; conflicto → `None`.
4. `confidence`: máximo del tipo ganador.
5. **Umbral de escritura** (configurable, inicial 0,5): confianza agregada por debajo
   → la arista NO se aserta; las evidencias persisten.

### RelationsGold (eval, fuera del grafo)

`eval/fixtures/<obra>.relations.gold.json` — referencia por obra. Reusa los `gold_id`
de personaje del gold de M1:

```json
{
  "work": "crafted-three-chapters",
  "annotation_criteria": "vínculo a eval/fixtures/README.md",
  "relations": [
    {
      "a": "elena-vasquez",
      "b": "miguel-vasquez",
      "rel_type": "family",
      "descriptor": "hermanos",
      "provenance": "extracted"
    }
  ]
}
```

### EvalResult (eval, fuera del grafo)

`eval/results/relations-<obra>-<fecha>-<sha>.json`:

| Campo | Tipo | Notas |
|-------|------|-------|
| `work`, `run_at`, `git_sha`, `prompt_version`, `model` | `str` | Reproducibilidad. |
| `pair_detection` | `{precision, recall, f1}` × {extracted, inferred, all} | SC-001. |
| `type_accuracy` | `float` × {extracted, inferred, all} | SC-002, sobre pares acertados. |
| `thresholds` | `{pair_f1_extracted, type_accuracy}` | Umbrales vigentes. |
| `passed` | `bool` | Gate solo sobre métricas `extracted` (SC-007). |

---

## Relaciones (Neo4j, delta — solo añade)

```
(a:Character)-[:RELATES_TO {rel_type, descriptor, role_a, role_b,
                            provenance, confidence, evidence_count,
                            first_evidence_id}]->(b:Character)
(ev:RelationEvidence)-[:ABOUT]->(:Character)      // exactamente 2 por evidencia
(ev:RelationEvidence)-[:IN_SCENE]->(:Scene)
(Manuscript)-[:HAS_RELATION_EVIDENCE]->(ev)
```

- Constraint: `RelationEvidence.evidence_id` UNIQUE. Índices por `manuscript_id` y
  `scene_id`.
- Escritura: `MERGE` por id determinista (evidencias) y por par canónico (arista) —
  re-ejecutar converge al mismo grafo.

---

## Data flow

```
Grafo M1 (Character + APPEARS_IN)  ── solo lectura ──┐
                                                      ▼
por escena (orden narrativo):
  texto escena + cast (ids + nombres/alias) ──▶ LLM ──▶ SceneRelationEvidence[]
  · cache por hash(escena + cast + versión prompt)
  · validación: pares dentro del cast, a ≠ b, máx 1 por par
                                                      ▼
agregación determinista por par ──▶ RELATES_TO (si confianza ≥ umbral)
                                                      ▼
backend/graph/relations.py ──▶ MERGE idempotente
```

Fallo de escena tras N reintentos → log + skip; la agregación opera con lo disponible
(FR-017). Manuscrito sin capa M1 → error explícito (FR-016).

---

## Invariantes de integridad (verificables en tests)

- **INV-M2-1 (sustento)**: toda arista `RELATES_TO` tiene ≥ 1 `RelationEvidence` del
  par; toda evidencia referencia 2 `Character` existentes y 1 `Scene` existente.
- **INV-M2-2 (determinismo)**: dos extracciones del mismo manuscrito (cache caliente)
  producen el mismo conjunto de `evidence_id` y las mismas aristas agregadas.
- **INV-M2-3 (capas previas intactas)**: M2 no modifica ninguna propiedad de nodos
  M0/M1.
- **INV-M2-4 (universo cerrado)**: ninguna evidencia ni arista referencia un
  `character_id` fuera del cast del manuscrito (SC-004).
- **INV-M2-5 (umbral)**: ninguna arista asertada tiene `confidence` bajo el umbral de
  escritura vigente.

---

## Notas de evolución (fuera de M2)

- **Arcos de relación** (estados por tramo narrativo): las `RelationEvidence`
  ordenadas por escena son la materia prima; añadir arcos no exige re-extraer.
- **Atributos y continuidad** (`knows/unaware_of`, `open_wounds`): specs posteriores
  del bloque M2 del roadmap.
- **Consolidador por par** (approach C como refuerzo): LLM sobre evidencias acumuladas
  de un par para refinar tipo/descriptor de relaciones inferidas, sin releer texto.
- **Relaciones humano–animal**: excluidas en M2 (cast filtra `entity_kind = "person"`);
  si el producto las pide (vínculo mascota–dueño), es un cambio de filtro, no de modelo.
