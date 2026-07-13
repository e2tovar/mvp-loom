# Contrato API + CLI — M1 Personajes

**Feature**: `002-char-extraction-eval` · **Fecha**: 2026-06-10

La extracción (proceso largo) se opera por **CLI**; la API expone solo operaciones
rápidas: inspección de personajes y gestión de la cola de fusiones (research R7).

---

## CLI

### `python -m backend.extraction.run <manuscript_id> [--force]`

Extrae los personajes de un manuscrito ya ingerido (capa cruda de M0 presente).

- Procesa las escenas en orden narrativo; imprime progreso (`escena i/N`, cache
  hit/miss) y un resumen final (personajes, menciones, candidatos a revisión, coste).
- Reanudable: re-lanzar tras un fallo continúa desde la cache (research R6).
- `--force`: ignora la cache (re-extracción completa; las decisiones humanas de
  fusión se respetan igualmente).
- Exit code 0 en éxito; ≠ 0 con mensaje claro si el manuscrito no existe o Neo4j/LLM
  no están disponibles.

### `python -m eval.characters.runner [--work <obra>] [--compare]`

Ejecuta el harness contra el golden dataset (sin llamadas LLM: compara grafo vs gold).

- Escribe `eval/results/characters-<obra>-<fecha>-<sha>.json` (ver data-model:
  EvalResult).
- `--compare`: muestra el delta contra el último resultado registrado.
- Exit code ≠ 0 si alguna métrica queda bajo umbral (gate, SC-007).

---

## REST

### `GET /manuscripts/{manuscript_id}/characters`

Lista inspeccionable de personajes (FR-006, SC-008).

Query params: `role` (filtro), `include_mentioned_only` (default `true`),
`order_by` ∈ {`appearances`, `first_appearance`, `name`} (default `appearances`).

**200**:

```json
{
  "manuscript_id": "…",
  "character_count": 27,
  "pending_merge_candidates": 2,
  "characters": [
    {
      "character_id": "…:ch:elizabeth-bennet",
      "canonical_name": "Elizabeth Bennet",
      "aliases": ["Lizzy", "Eliza", "Miss Bennet"],
      "role": "protagonist",
      "is_mentioned_only": false,
      "appearance_count": 54,
      "mention_count": 612,
      "first_appearance": { "scene_id": "…:c0:s0", "chapter_order": 0, "quote": "…" }
    }
  ]
}
```

**404** `{"error": "not_found", ...}` si el manuscrito no existe.
**409** `{"error": "not_extracted", ...}` si existe pero no se ha ejecutado la extracción.

### `GET /manuscripts/{manuscript_id}/characters/{character_id}`

Detalle con apariciones y menciones (procedencia completa, FR-004).

**200**: entidad + `appearances[]` (escena, kind, mention_count) + `mentions[]`
(surface, kind, scene_id, offsets, quote). **404** si no existe.

### `GET /manuscripts/{manuscript_id}/merge-candidates`

Cola de revisión (US3). Query param `status` ∈ {`pending`, `accepted`, `rejected`,
`all`} (default `pending`).

**200**:

```json
{
  "candidates": [
    {
      "candidate_id": "…:mc:eliza+miss-e",
      "characters": [
        { "character_id": "…", "canonical_name": "Eliza", "aliases": [] },
        { "character_id": "…", "canonical_name": "Miss E.", "aliases": [] }
      ],
      "confidence": 0.72,
      "rationale": "…",
      "evidence": [ { "scene_id": "…", "surface": "Eliza", "quote": "…" } ],
      "status": "pending"
    }
  ]
}
```

### `POST /merge-candidates/{candidate_id}/resolve`

Decisión humana sobre una fusión dudosa (FR-005).

Body: `{ "decision": "accept" | "reject" }`

- `accept`: aplica el merge en el grafo (menciones, apariciones y alias de B → A;
  B se elimina; `merged_from` registrado). **200** con el `Character` resultante.
- `reject`: las entidades quedan separadas permanentemente; el par no se vuelve a
  proponer. **200** con `{"status": "rejected"}`.
- **404** si el candidato no existe; **409** `{"error": "already_resolved"}` si ya
  fue decidido (las decisiones son finales en M1).

---

## Errores

Mismo formato que M0: `{"error": "<code>", "detail": "<mensaje>"}` con códigos
`not_found` (404), `not_extracted` (409), `already_resolved` (409),
`invalid_decision` (400).
