# Cierre de M1: B³ real en el eval harness + T038 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cablear la resolución B³ real en el eval harness (clusters de menciones reales, gold anotado a nivel de mención, pares de MergeCandidate reales) y ejecutar el quickstart E2E contra obras reales (T038), cerrando M1 sin métricas stub.

**Architecture:** El espacio compartido de IDs entre gold y pred es la clave `"c{cap}/s{escena}::{surface_normalizada}"`. Funciona porque el pipeline solo escribe la primera ocurrencia de cada surface por escena (`pipeline.py:_find_offset` usa `text.find`) y `mention_id` es determinista por (scene, surface, offset) — así (coordenada, surface) identifica unívocamente una mención predicha. El gold anota menciones solo en las fixtures crafted (pequeñas); cuando el gold no tiene menciones (pride-and-prejudice), B³ se reporta como `null` y el gate no lo considera — nunca un 0.0 falso ni un pass silencioso.

**Tech Stack:** Python 3.12 + uv, pytest, Neo4j (driver `neo4j`), sin llamadas LLM salvo en la Task 7 (extracción real vía LiteLLM).

## Global Constraints

- Cypher SOLO en `backend/graph/` (constitución); LiteLLM SOLO en `backend/llm/`.
- Umbrales sin cambios (`eval/characters/thresholds.py`): `DETECTION_F1 = 0.90`, `RESOLUTION_B3_F1 = 0.85`, `SILENT_BAD_MERGES = 0`.
- Ids deterministas e idempotencia (INV-M1-1); decisiones humanas finales (INV-M1-4).
- Docstrings/comentarios en español; commits conventional en inglés; NUNCA `git push`.
- Correr tests con `uv run pytest …`; lint con `uv run ruff check backend eval tests`.
- El resultado del eval nunca sobre-afirma: métrica no medida = `null` + warning, jamás un valor inventado (regla quality-boundaries).

## Contexto para el implementador (leer antes de empezar)

- `docs/known-issues.md` — describe la deuda exacta que este plan salda.
- `eval/characters/runner.py` — el runner actual descarta `pred_clusters` (línea 83) y construye clusters ficticios disjuntos (líneas 98-102) → B³ = 0.0 siempre; `count_silent_bad_merges` recibe `[]` (línea 104).
- `eval/characters/metrics.py` — `bcubed_f1` ya es correcto; no se toca. `count_silent_bad_merges` cambia de firma.
- `backend/graph/characters.py` — `get_character_detail` ya devuelve `mentions` con `mention_id, surface, kind, scene_id, start_offset…`.
- `backend/graph/merge_candidates.py:get_merge_candidates(sess, mid, status)` — devuelve candidatos con `characters: [char_a, char_b]` (dicts con `canonical_name` y `aliases`).
- Grafo: `Chapter.order_narrative` (0-based, prólogo = 0) y `Scene.order_in_chapter` — de ahí salen las coordenadas `c{n}/s{m}` que usa el gold.
- **Hallazgo del research:** el fixture `crafted-two-chapters.epub` NO contiene los nombres Elena/Marco en su texto (`eval/fixtures/build_fixtures.py:26-42`), pero su gold los declara. Nunca se notó porque el gate siempre hacía SKIP. La Task 5 regenera el epub con texto coherente.

---

### Task 1: `count_silent_bad_merges` con pares reales de MergeCandidate

**Files:**
- Modify: `eval/characters/metrics.py:148-179`
- Test: `tests/unit/test_character_metrics.py`

**Interfaces:**
- Produces: `count_silent_bad_merges(gold_entities: list[dict], pred_entities: list[dict], candidate_pairs: list[tuple[dict, dict]]) -> int` — los pares son dicts de entidad (`canonical_name` + `aliases`), y el matching usa solapamiento de aliases (`_entities_match`), no igualdad exacta de nombre. La Task 4 le pasa los pares reales del grafo.

- [ ] **Step 1: Write the failing test**

Añadir al final de la sección "Silent bad merges" de `tests/unit/test_character_metrics.py`:

```python
def test_bad_merge_with_registered_candidate_not_counted():
    """Una fusión con MergeCandidate registrado NO es silenciosa, aunque los
    nombres del candidato no coincidan exactamente con los del gold."""
    gold = [_entity("Ana"), _entity("María")]
    pred = [_entity("Ana", aliases=["María"])]
    # El candidato registra el par vía alias, no vía canonical exacto
    pairs = [(_entity("Ana"), _entity("Mari", aliases=["María"]))]
    assert count_silent_bad_merges(gold, pred, pairs) == 0


def test_bad_merge_with_unrelated_candidate_still_counted():
    gold = [_entity("Ana"), _entity("María")]
    pred = [_entity("Ana", aliases=["María"])]
    pairs = [(_entity("Pedro"), _entity("Juan"))]
    assert count_silent_bad_merges(gold, pred, pairs) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_character_metrics.py -q`
Expected: FAIL — los dos tests nuevos rompen (la implementación actual espera tuplas de strings y hace `a.casefold()` sobre un dict → `AttributeError`).

- [ ] **Step 3: Change the implementation**

En `eval/characters/metrics.py`, reemplazar la firma y el bloque `pair_known` de `count_silent_bad_merges`:

```python
def count_silent_bad_merges(
    gold_entities: list[dict],
    pred_entities: list[dict],
    candidate_pairs: list[tuple[dict, dict]],
) -> int:
    """Pares del gold distintos que aparecen fusionados en pred sin candidate.

    Un "silent bad merge" es: dos gold_ids que el sistema colapsó en una sola
    entidad predicha pero sin MergeCandidate registrado para ese par.

    Args:
        candidate_pairs: Pares (char_a, char_b) de MergeCandidate del grafo
            (cualquier status); cada elemento es un dict de entidad con
            `canonical_name` y `aliases`. El matching usa solapamiento de
            aliases, igual que la detección.
    """
    bad = 0
    for i, ga in enumerate(gold_entities):
        for gb in gold_entities[i + 1 :]:
            if _entities_match(ga, gb):
                # Son entidades distintas en gold pero podrían coincidir en pred
                continue
            # Buscar si pred fusionó ga y gb en la misma entidad
            pred_a = next((p for p in pred_entities if _entities_match(ga, p)), None)
            pred_b = next((p for p in pred_entities if _entities_match(gb, p)), None)
            if pred_a is None or pred_b is None:
                continue
            if pred_a["canonical_name"] == pred_b["canonical_name"]:
                # Están fusionadas — ¿existe un candidate para el par?
                pair_known = any(
                    (_entities_match(ga, ca) and _entities_match(gb, cb))
                    or (_entities_match(ga, cb) and _entities_match(gb, ca))
                    for ca, cb in candidate_pairs
                )
                if not pair_known:
                    bad += 1
    return bad
```

Los dos tests existentes (`test_no_silent_bad_merges_when_separate`, `test_silent_bad_merge_detected`) pasan `[]` y siguen siendo válidos sin cambios.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_character_metrics.py -q`
Expected: PASS (14 tests).

- [ ] **Step 5: Commit**

```bash
git add eval/characters/metrics.py tests/unit/test_character_metrics.py
git commit -m "feat(eval): silent_bad_merges matches real MergeCandidate pairs by alias overlap"
```

---

### Task 2: Módulo de alineación de menciones gold↔pred

**Files:**
- Create: `eval/characters/alignment.py`
- Test: `tests/unit/test_mention_alignment.py`

**Interfaces:**
- Produces:
  - `mention_key(scene_coord: str, surface: str) -> str` — clave `"c1/s0::elena"`.
  - `gold_mention_clusters(gold: dict) -> list[list[str]] | None` — `None` si NINGÚN personaje del gold tiene `mentions`; `ValueError` si solo algunos la tienen.
  - `pred_mention_clusters(characters_mentions: list[list[dict]], scene_coords: dict[str, str]) -> list[list[str]]` — recibe, por personaje, sus menciones del grafo (dicts con `scene_id`, `surface`, `kind`) y el mapa `scene_id → "c{n}/s{m}"`. Excluye `kind == "pronoun_resolved"`.
- Consumed by: Task 4 (runner).

- [ ] **Step 1: Write the failing tests**

Crear `tests/unit/test_mention_alignment.py`:

```python
"""Tests de la alineación de menciones gold↔pred para B³ (cierre de known-issues M1)."""

from __future__ import annotations

import pytest

from eval.characters.alignment import (
    gold_mention_clusters,
    mention_key,
    pred_mention_clusters,
)
from eval.characters.metrics import bcubed_f1


def _gold_char(gold_id: str, mentions: list[dict] | None) -> dict:
    char = {
        "gold_id": gold_id,
        "canonical_name": gold_id.title(),
        "aliases": [],
        "role": "secondary",
        "is_mentioned_only": False,
        "appearances": [],
    }
    if mentions is not None:
        char["mentions"] = mentions
    return char


def test_mention_key_normalizes_surface():
    assert mention_key("c1/s0", "  Elena ") == "c1/s0::elena"
    assert mention_key("c1/s0", "ELENA") == "c1/s0::elena"


def test_gold_clusters_none_when_not_annotated():
    gold = {"characters": [_gold_char("elena", None)]}
    assert gold_mention_clusters(gold) is None


def test_gold_clusters_inconsistent_annotation_raises():
    gold = {
        "characters": [
            _gold_char("elena", [{"scene": "c1/s0", "surface": "Elena"}]),
            _gold_char("marco", None),
        ]
    }
    with pytest.raises(ValueError, match="marco"):
        gold_mention_clusters(gold)


def test_gold_and_pred_share_key_space_perfect_b3():
    gold = {
        "characters": [
            _gold_char(
                "elena",
                [
                    {"scene": "c1/s0", "surface": "Elena"},
                    {"scene": "c2/s1", "surface": "Elena"},
                ],
            ),
            _gold_char("marco", [{"scene": "c2/s0", "surface": "Marco"}]),
        ]
    }
    scene_coords = {"sc-a": "c1/s0", "sc-b": "c2/s0", "sc-c": "c2/s1"}
    pred = [
        [
            {"scene_id": "sc-a", "surface": "Elena", "kind": "name"},
            {"scene_id": "sc-c", "surface": "Elena", "kind": "name"},
        ],
        [{"scene_id": "sc-b", "surface": "Marco", "kind": "name"}],
    ]
    scores = bcubed_f1(gold_mention_clusters(gold), pred_mention_clusters(pred, scene_coords))
    assert scores.f1 == pytest.approx(1.0)


def test_pred_clusters_exclude_pronouns_and_unknown_scenes():
    scene_coords = {"sc-a": "c1/s0"}
    pred = [
        [
            {"scene_id": "sc-a", "surface": "Elena", "kind": "name"},
            {"scene_id": "sc-a", "surface": "ella", "kind": "pronoun_resolved"},
            {"scene_id": "sc-zz", "surface": "Elena", "kind": "name"},
        ]
    ]
    assert pred_mention_clusters(pred, scene_coords) == [["c1/s0::elena"]]


def test_pred_clusters_dedupe_repeated_key():
    scene_coords = {"sc-a": "c1/s0"}
    pred = [
        [
            {"scene_id": "sc-a", "surface": "Elena", "kind": "name"},
            {"scene_id": "sc-a", "surface": "elena", "kind": "alias"},
        ]
    ]
    assert pred_mention_clusters(pred, scene_coords) == [["c1/s0::elena"]]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_mention_alignment.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'eval.characters.alignment'`.

- [ ] **Step 3: Write the implementation**

Crear `eval/characters/alignment.py`:

```python
"""Alineación de menciones gold↔pred para B-cubed (cierra docs/known-issues.md M1).

El espacio compartido de IDs es la clave `"c{cap}/s{escena}::{surface_normalizada}"`.
Funciona porque el pipeline solo escribe la primera ocurrencia de cada surface por
escena (pipeline._find_offset) y mention_id es determinista: (coordenada de escena,
surface) identifica unívocamente una mención predicha.

Las menciones `pronoun_resolved` se excluyen del espacio B³: el gold solo anota
menciones nombradas (name/alias/title/description) — ver eval/fixtures/README.md.
"""

from __future__ import annotations

_EXCLUDED_KINDS = {"pronoun_resolved"}


def mention_key(scene_coord: str, surface: str) -> str:
    """Clave compartida gold↔pred de una mención."""
    return f"{scene_coord}::{surface.casefold().strip()}"


def gold_mention_clusters(gold: dict) -> list[list[str]] | None:
    """Clusters gold de menciones; None si el gold no está anotado a nivel de mención.

    Raises:
        ValueError: si solo algunos personajes tienen `mentions` (gold inconsistente).
    """
    chars = gold["characters"]
    annotated = [c for c in chars if "mentions" in c]
    if not annotated:
        return None
    if len(annotated) != len(chars):
        missing = [c["gold_id"] for c in chars if "mentions" not in c]
        raise ValueError(f"Gold inconsistente: personajes sin 'mentions': {missing}")

    clusters: list[list[str]] = []
    for c in chars:
        cluster: list[str] = []
        for m in c["mentions"]:
            key = mention_key(m["scene"], m["surface"])
            if key not in cluster:
                cluster.append(key)
        if cluster:
            clusters.append(cluster)
    return clusters


def pred_mention_clusters(
    characters_mentions: list[list[dict]],
    scene_coords: dict[str, str],
) -> list[list[str]]:
    """Clusters pred en el mismo espacio de claves que el gold.

    Args:
        characters_mentions: por personaje, sus menciones del grafo
            (dicts con `scene_id`, `surface`, `kind`).
        scene_coords: mapa scene_id → coordenada "c{n}/s{m}".
    """
    clusters: list[list[str]] = []
    for mentions in characters_mentions:
        cluster: list[str] = []
        for m in mentions:
            if m.get("kind") in _EXCLUDED_KINDS:
                continue
            coord = scene_coords.get(m["scene_id"])
            if coord is None:
                continue
            key = mention_key(coord, m["surface"])
            if key not in cluster:
                cluster.append(key)
        if cluster:
            clusters.append(cluster)
    return clusters
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_mention_alignment.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add eval/characters/alignment.py tests/unit/test_mention_alignment.py
git commit -m "feat(eval): gold/pred mention alignment on shared scene-coord key space"
```

---

### Task 3: `get_scene_coordinates` en la capa de grafo

**Files:**
- Modify: `backend/graph/characters.py` (añadir función en la sección "Lectura", después de `get_character_detail`)

**Interfaces:**
- Produces: `get_scene_coordinates(sess: Session, manuscript_id: str) -> dict[str, str]` — mapa `scene_id → "c{order_narrative}/s{order_in_chapter}"`. Consumida por Task 4. (Cypher vive aquí por constitución; sin test unitario propio — requiere Neo4j; queda cubierta por el E2E de Task 7.)

- [ ] **Step 1: Write the implementation**

Añadir a `backend/graph/characters.py` tras `get_character_detail`:

```python
def get_scene_coordinates(sess: Session, manuscript_id: str) -> dict[str, str]:
    """Mapa scene_id → coordenada 'c{cap}/s{escena}' (mismo formato que el gold del eval)."""
    result = sess.run(
        """
        MATCH (m:Manuscript {manuscript_id: $mid})-[:HAS_CHAPTER]->(c:Chapter)
              -[:HAS_SCENE]->(s:Scene)
        RETURN s.scene_id AS scene_id,
               c.order_narrative AS chapter_order,
               s.order_in_chapter AS scene_order
        """,
        mid=manuscript_id,
    )
    return {
        rec["scene_id"]: f"c{rec['chapter_order']}/s{rec['scene_order']}"
        for rec in result
    }
```

- [ ] **Step 2: Verify no regressions**

Run: `uv run pytest tests/unit -q && uv run ruff check backend`
Expected: PASS / sin violaciones.

- [ ] **Step 3: Commit**

```bash
git add backend/graph/characters.py
git commit -m "feat(graph): scene_id to narrative coordinate map for the eval harness"
```

---

### Task 4: Cablear el runner — B³ real, pares reales, B³ nullable

**Files:**
- Modify: `eval/characters/runner.py`
- Modify: `tests/eval/test_characters_gate.py`
- Test: `tests/unit/test_eval_runner.py` (nuevo)

**Interfaces:**
- Consumes: `alignment.gold_mention_clusters/pred_mention_clusters` (Task 2), `metrics.count_silent_bad_merges` nueva firma (Task 1), `char_graph.get_scene_coordinates` (Task 3), `merge_candidates.get_merge_candidates` (existente).
- Produces: `run_eval(work, manuscript_id=None) -> dict` donde `result["resolution_b3"]` es `dict | None` (`None` = gold sin menciones, con warning por stderr; `passed` no considera B³ en ese caso). `_load_system_output(mid) -> tuple[list[dict], list[list[str]], list[tuple[dict, dict]]]` (entidades, clusters pred alineados, pares de candidatos).

- [ ] **Step 1: Write the failing tests**

Crear `tests/unit/test_eval_runner.py`:

```python
"""Tests de run_eval con la carga del grafo simulada (sin Neo4j ni LLM)."""

from __future__ import annotations

import pytest

from eval.characters import runner

GOLD_ANNOTATED = {
    "work": "obra-test",
    "characters": [
        {
            "gold_id": "elena",
            "canonical_name": "Elena",
            "aliases": [],
            "role": "protagonist",
            "is_mentioned_only": False,
            "appearances": ["c1/s0"],
            "mentions": [{"scene": "c1/s0", "surface": "Elena"}],
        },
        {
            "gold_id": "marco",
            "canonical_name": "Marco",
            "aliases": [],
            "role": "secondary",
            "is_mentioned_only": False,
            "appearances": ["c2/s0"],
            "mentions": [{"scene": "c2/s0", "surface": "Marco"}],
        },
    ],
}

GOLD_NOT_ANNOTATED = {
    "work": "obra-test",
    "characters": [
        {
            "gold_id": "elena",
            "canonical_name": "Elena",
            "aliases": [],
            "role": "protagonist",
            "is_mentioned_only": False,
            "appearances": ["c1/s0"],
        },
    ],
}

PRED_ENTITIES = [
    {"character_id": "m:ch:1", "canonical_name": "Elena", "aliases": []},
    {"character_id": "m:ch:2", "canonical_name": "Marco", "aliases": []},
]


def _patch(monkeypatch, gold, clusters, pairs=None):
    monkeypatch.setattr(runner, "_load_gold", lambda work: gold)
    monkeypatch.setattr(
        runner,
        "_load_system_output",
        lambda mid: (PRED_ENTITIES, clusters, pairs or []),
    )


def test_b3_real_perfect(monkeypatch):
    _patch(
        monkeypatch,
        GOLD_ANNOTATED,
        [["c1/s0::elena"], ["c2/s0::marco"]],
    )
    result = runner.run_eval("obra-test")
    assert result["resolution_b3"]["f1"] == pytest.approx(1.0)
    assert result["passed"] is True


def test_b3_real_bad_clustering_fails_gate(monkeypatch):
    # El sistema fusionó las menciones de Elena y Marco en un solo cluster
    _patch(monkeypatch, GOLD_ANNOTATED, [["c1/s0::elena", "c2/s0::marco"]])
    result = runner.run_eval("obra-test")
    assert result["resolution_b3"]["f1"] < 0.85
    assert result["passed"] is False


def test_b3_null_when_gold_not_annotated(monkeypatch):
    _patch(monkeypatch, GOLD_NOT_ANNOTATED, [["c1/s0::elena"]])
    result = runner.run_eval("obra-test")
    assert result["resolution_b3"] is None
    # detection sigue contando: 2 pred vs 1 gold → precision 0.5 → F1 < 0.90
    assert result["passed"] is False


def test_b3_null_does_not_block_when_detection_ok(monkeypatch):
    gold = {
        "work": "obra-test",
        "characters": [
            {
                "gold_id": "elena",
                "canonical_name": "Elena",
                "aliases": [],
                "role": "protagonist",
                "is_mentioned_only": False,
                "appearances": ["c1/s0"],
            },
            {
                "gold_id": "marco",
                "canonical_name": "Marco",
                "aliases": [],
                "role": "secondary",
                "is_mentioned_only": False,
                "appearances": ["c2/s0"],
            },
        ],
    }
    _patch(monkeypatch, gold, [["c1/s0::elena"]])
    result = runner.run_eval("obra-test")
    assert result["resolution_b3"] is None
    assert result["passed"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_eval_runner.py -q`
Expected: FAIL — `_load_system_output` actual devuelve 2 elementos, y `resolution_b3` nunca es `None`.

- [ ] **Step 3: Rewire the runner**

En `eval/characters/runner.py`:

**3a.** Reemplazar `_load_system_output` completo:

```python
def _load_system_output(
    manuscript_id: str,
) -> tuple[list[dict], list[list[str]], list[tuple[dict, dict]]]:
    """Carga del grafo: entidades, clusters de menciones alineados y pares de candidatos."""
    from dotenv import load_dotenv

    load_dotenv()
    from backend.graph import characters as char_graph
    from backend.graph.client import session as db_session
    from backend.graph.merge_candidates import get_merge_candidates
    from eval.characters.alignment import pred_mention_clusters

    with db_session() as sess:
        char_list = char_graph.get_characters_list(sess, manuscript_id)
        scene_coords = char_graph.get_scene_coordinates(sess, manuscript_id)
        per_char_mentions = []
        for c in char_list:
            detail = char_graph.get_character_detail(sess, manuscript_id, c["character_id"])
            if detail:
                per_char_mentions.append(detail.get("mentions", []))
        clusters = pred_mention_clusters(per_char_mentions, scene_coords)
        candidates = get_merge_candidates(sess, manuscript_id, status="all")
        pairs = [(mc["characters"][0], mc["characters"][1]) for mc in candidates]
    return char_list, clusters, pairs
```

**3b.** Eliminar `_build_gold_clusters` (queda muerta — verificar con `grep -rn _build_gold_clusters` que nadie más la usa).

**3c.** En `run_eval`, reemplazar el bloque de métricas (desde `pred_entities, pred_clusters = ...` hasta `sbm = ...`) por:

```python
    mid = manuscript_id or work
    try:
        pred_entities, pred_clusters, candidate_pairs = _load_system_output(mid)
    except Exception as exc:
        print(f"[eval] No se pudo cargar la salida del sistema: {exc}", file=sys.stderr)
        print(
            "[eval] ¿Se ejecutó la extracción? (python -m backend.extraction.run)",
            file=sys.stderr,
        )
        sys.exit(1)

    det = detection_f1(gold_entities, pred_entities)

    # B³ real sobre menciones — solo si el gold está anotado a nivel de mención.
    from eval.characters.alignment import gold_mention_clusters

    gold_clusters = gold_mention_clusters(gold)
    if gold_clusters is None:
        b3 = None
        print(
            f"[eval] Gold de '{work}' sin anotación de menciones — B³ no medido "
            "(ver eval/fixtures/README.md#mentions).",
            file=sys.stderr,
        )
    else:
        b3 = bcubed_f1(gold_clusters, pred_clusters)

    sbm = count_silent_bad_merges(gold_entities, pred_entities, candidate_pairs)

    passed = (
        det.f1 >= DETECTION_F1
        and (b3 is None or b3.f1 >= RESOLUTION_B3_F1)
        and sbm <= SILENT_BAD_MERGES
    )
```

**3d.** En el dict `result`, reemplazar la línea de `resolution_b3`:

```python
        "resolution_b3": (
            None
            if b3 is None
            else {"precision": b3.precision, "recall": b3.recall, "f1": b3.f1}
        ),
```

**3e.** En `_print_result`, reemplazar las líneas que leen `resolution_b3` (`b3_f1 = ...` y el `print` de `B³ Resol.`):

```python
    b3 = result["resolution_b3"]
    b3_thr = result["thresholds"]["resolution_b3_f1"]
    print(f"  Detection  : F1={det_f1:.3f}  (≥{det_thr})")
    if b3 is None:
        print("  B³ Resol.  : no medido — gold sin anotación de menciones")
    else:
        print(f"  B³ Resol.  : F1={b3['f1']:.3f}  (≥{b3_thr})")
```

Y en el bloque `if compare:` proteger el delta de B³:

```python
    if compare:
        dd = result["detection"]["f1"] - compare.get("detection", {}).get("f1", 0)
        prev_b3 = compare.get("resolution_b3") or {}
        if b3 is not None and prev_b3:
            db = b3["f1"] - prev_b3.get("f1", 0)
            print(f"  Δ Detection: {dd:+.3f}   Δ B³: {db:+.3f}  (vs {compare.get('run_at','?')[:10]})")
        else:
            print(f"  Δ Detection: {dd:+.3f}  (vs {compare.get('run_at','?')[:10]})")
```

**3f.** En `tests/eval/test_characters_gate.py`, tras `result = run_eval(...)` y antes del assert de `passed`, añadir el candado anti-regresión (las obras del gate DEBEN tener B³ real) y proteger el formato del mensaje:

```python
    assert result["resolution_b3"] is not None, (
        f"El gold de '{work}' perdió la anotación de menciones: el gate exige B³ real."
    )
```

Y en el f-string del assert final, reemplazar la línea de B³ por:

```python
        f"  B³ F1 = {result['resolution_b3']['f1']:.3f} "
```

(sin cambio funcional — sigue siendo válida porque el assert anterior garantiza no-None).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_eval_runner.py tests/unit/test_character_metrics.py tests/unit/test_mention_alignment.py -q`
Expected: PASS. Luego `uv run pytest tests -q` (el gate hará SKIP sin Neo4j/extracción — correcto).

- [ ] **Step 5: Commit**

```bash
git add eval/characters/runner.py tests/unit/test_eval_runner.py tests/eval/test_characters_gate.py
git commit -m "feat(eval): wire real B-cubed resolution and MergeCandidate pairs into runner

B3 now uses real mention clusters aligned on (scene coordinate, surface)
keys. Golds without mention annotation report resolution_b3=null with a
warning instead of a fake 0.0, and the CI gate hard-requires non-null B3
for its works. Closes the M1 debt in docs/known-issues.md."
```

---

### Task 5: Gold con menciones + fixture epub coherente

**Files:**
- Modify: `eval/fixtures/crafted-three-chapters.txt.characters.gold.json`
- Modify: `eval/fixtures/build_fixtures.py:26-42` (contenido del epub)
- Modify: `eval/fixtures/crafted-two-chapters.epub.characters.gold.json`
- Modify: `eval/fixtures/README.md`
- Regenerate: `eval/fixtures/crafted-two-chapters.epub` (y `.docx` si el builder lo altera)
- Test: `tests/unit/test_gold_fixtures.py` (nuevo)

**Interfaces:**
- Produces: golds de las dos obras del gate (`tests/eval/test_characters_gate.py:EVAL_WORKS`) con `mentions: [{"scene": "c{n}/s{m}", "surface": "<texto>"}]` por personaje. Formato consumido por `gold_mention_clusters` (Task 2).

**Contexto:** el texto del epub actual no contiene Elena/Marco (ver hallazgo en el encabezado). Se reescribe el contenido manteniendo la estructura que exige su `annotation.json` de segmentación: 2 capítulos, 1 separador `<hr/>` en el capítulo 1.

- [ ] **Step 1: Write the failing validation test**

Crear `tests/unit/test_gold_fixtures.py`:

```python
"""Coherencia interna de los golden datasets anotados a nivel de mención (M1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent.parent.parent / "eval" / "fixtures"
# Las obras del gate de CI DEBEN estar anotadas a nivel de mención.
ANNOTATED_WORKS = ["crafted-three-chapters.txt", "crafted-two-chapters.epub"]


@pytest.mark.parametrize("work", ANNOTATED_WORKS)
def test_gold_mentions_consistent_with_appearances(work: str) -> None:
    gold = json.loads(
        (FIXTURES / f"{work}.characters.gold.json").read_text(encoding="utf-8")
    )
    for char in gold["characters"]:
        assert "mentions" in char, f"{char['gold_id']} sin anotación de menciones"
        mention_scenes = {m["scene"] for m in char["mentions"]}
        appearances = set(char["appearances"])
        assert mention_scenes == appearances, (
            f"{char['gold_id']}: escenas de menciones {mention_scenes} "
            f"≠ appearances {appearances}"
        )


def test_txt_gold_surfaces_exist_in_fixture_text() -> None:
    text = (FIXTURES / "crafted-three-chapters.txt").read_text(encoding="utf-8")
    gold = json.loads(
        (FIXTURES / "crafted-three-chapters.txt.characters.gold.json").read_text(
            encoding="utf-8"
        )
    )
    for char in gold["characters"]:
        for m in char["mentions"]:
            assert m["surface"] in text, f"surface '{m['surface']}' no está en el texto"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_gold_fixtures.py -q`
Expected: FAIL — los golds aún no tienen `mentions`.

- [ ] **Step 3: Annotate the txt gold**

Reemplazar el array `characters` de `eval/fixtures/crafted-three-chapters.txt.characters.gold.json` (las menciones salen del texto del fixture: "Elena abrió la puerta" en c1/s0, "Elena bajó sola" en c2/s1, "Marco la esperaba" en c2/s0):

```json
{
  "work": "crafted-three-chapters.txt",
  "annotation_criteria": "eval/fixtures/README.md#characters",
  "characters": [
    {
      "gold_id": "elena",
      "canonical_name": "Elena",
      "aliases": [],
      "role": "protagonist",
      "is_mentioned_only": false,
      "appearances": ["c1/s0", "c2/s1"],
      "mentions": [
        {"scene": "c1/s0", "surface": "Elena"},
        {"scene": "c2/s1", "surface": "Elena"}
      ]
    },
    {
      "gold_id": "marco",
      "canonical_name": "Marco",
      "aliases": [],
      "role": "secondary",
      "is_mentioned_only": false,
      "appearances": ["c2/s0"],
      "mentions": [
        {"scene": "c2/s0", "surface": "Marco"}
      ]
    }
  ]
}
```

- [ ] **Step 4: Rewrite the epub builder content**

En `eval/fixtures/build_fixtures.py`, reemplazar los bloques `c1.content` y `c2.content` (misma estructura: 2 capítulos, 1 `<hr/>` en el cap. 1 — el `annotation.json` de segmentación sigue válido):

```python
    c1.content = (
        "<html><body>"
        "<h1>Capítulo 1</h1>"
        "<p>Elena abrió la puerta con acentós y eñes.</p>"
        "<p>Párrafo dos del primer capítulo.</p>"
        "<hr/>"
        "<p>Elena bajó del tren tras el separador tipográfico.</p>"
        "</body></html>"
    )
```

```python
    c2.content = (
        "<html><body>"
        "<h1>Capítulo 2</h1>"
        "<p>Marco esperaba en la estación del segundo capítulo.</p>"
        "</body></html>"
    )
```

- [ ] **Step 5: Regenerate binaries and update the epub gold**

Run: `uv run python eval/fixtures/build_fixtures.py`
Expected: imprime las rutas de `crafted-two-chapters.epub` y `.docx`.

Reemplazar `eval/fixtures/crafted-two-chapters.epub.characters.gold.json` (el epub tiene capítulos c0 y c1; Elena aparece en las dos escenas del c0):

```json
{
  "work": "crafted-two-chapters.epub",
  "annotation_criteria": "eval/fixtures/README.md#characters",
  "characters": [
    {
      "gold_id": "elena",
      "canonical_name": "Elena",
      "aliases": [],
      "role": "protagonist",
      "is_mentioned_only": false,
      "appearances": ["c0/s0", "c0/s1"],
      "mentions": [
        {"scene": "c0/s0", "surface": "Elena"},
        {"scene": "c0/s1", "surface": "Elena"}
      ]
    },
    {
      "gold_id": "marco",
      "canonical_name": "Marco",
      "aliases": [],
      "role": "secondary",
      "is_mentioned_only": false,
      "appearances": ["c1/s0"],
      "mentions": [
        {"scene": "c1/s0", "surface": "Marco"}
      ]
    }
  ]
}
```

- [ ] **Step 6: Document the annotation criteria**

En `eval/fixtures/README.md`, dentro de la sección "Golden datasets de personajes (M1)", añadir tras los criterios de frontera existentes:

```markdown
### Anotación a nivel de mención (`mentions`) {#mentions}

Las obras del gate de CI llevan además, por personaje, la lista de menciones:
`{"scene": "c{cap}/s{escena}", "surface": "<texto exacto>"}`.

- Se anotan solo menciones **nombradas** (name/alias/title/description); los
  pronombres resueltos (`pronoun_resolved`) quedan fuera del espacio B³.
- Una entrada por par (escena, surface): el pipeline solo persiste la primera
  ocurrencia de cada surface por escena (mention_id determinista), así que la
  clave de alineación `"c{n}/s{m}::{surface}"` es unívoca en ambos lados.
- Golds sin `mentions` (p. ej. pride-and-prejudice) reportan `resolution_b3: null`
  en el eval — la métrica queda "no medida", nunca un valor inventado.
```

Actualizar también la tabla final del README: la fila del epub pasa a "2 (Elena, Marco) — texto regenerado con menciones reales" y añadir nota de que txt+epub llevan anotación de menciones.

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_gold_fixtures.py tests/unit -q`
Expected: PASS. Verificar también que la ingesta del epub regenerado no rompe parsers: `uv run pytest tests/unit/test_parsers.py tests/eval/test_segmentation_accuracy.py -q` → PASS/SKIP.

- [ ] **Step 8: Commit**

```bash
git add eval/fixtures/ tests/unit/test_gold_fixtures.py
git commit -m "feat(eval): mention-level gold for gate works; regenerate epub with real character text

The epub fixture never contained the names its character gold declared
(gate always SKIPped, so it went unnoticed). Rebuilt with Elena/Marco
narrative preserving the 2-chapter/1-separator structure its segmentation
annotation requires."
```

---

### Task 6: Coherencia documental (known-issues + ABOUT)

**Files:**
- Modify: `docs/known-issues.md`
- Modify: `docs/ABOUT.md:127,142`

- [ ] **Step 1: Mark the debt as resolved**

En `docs/known-issues.md`, reemplazar la línea `**Estado:** deuda · detectado 2026-06-15` por:

```markdown
**Estado:** ✅ resuelto 2026-07-11 · detectado 2026-06-15
```

Y añadir al final de esa entrada (antes de la sección "Nota de coherencia", que se elimina):

```markdown
**Resolución (2026-07-11):** `eval/characters/alignment.py` alinea gold↔pred en el
espacio de claves `"c{cap}/s{escena}::{surface}"`; los golds de las obras del gate
llevan `mentions` anotadas; el runner pasa los clusters reales a `bcubed_f1` y los
pares reales de `MergeCandidate` a `count_silent_bad_merges`. Los golds sin anotación
de menciones (pride-and-prejudice) reportan `resolution_b3: null` — no medido, nunca
un valor inventado. El gate exige B³ no-null para sus obras.
```

- [ ] **Step 2: Align ABOUT.md**

En `docs/ABOUT.md:142`, reemplazar:

```markdown
vigentes: detección F1 ≥ 0.90, resolución B³ ≥ 0.85.
```

por:

```markdown
vigentes: detección F1 ≥ 0.90, resolución B³ ≥ 0.85 (B³ se mide sobre las obras con
gold anotado a nivel de mención; sin esa anotación el eval reporta "no medido").
```

En `docs/ABOUT.md:127`, dejar la fila de M1 como `🔚 Cierre en curso` (la Task 7 la devuelve a `✅ Completo` cuando el E2E pase de verdad).

- [ ] **Step 3: Commit**

```bash
git add docs/known-issues.md docs/ABOUT.md
git commit -m "docs: mark B3 resolution debt as resolved, stop over-claiming M1 status"
```

---

### Task 7: T038 — Quickstart E2E contra obras reales + cierre

**Files:**
- Modify: `specs/002-char-extraction-eval/tasks.md:143` (marcar T038)
- Modify: `docs/ABOUT.md:127` (M1 → ✅ Completo, solo si todo pasa)
- Delete: `eval/results/characters-pride-and-prejudice-txt-20260614-4072e29.json` (resultado obsoleto de la métrica stub, sin trackear)
- Create: resultados frescos en `eval/results/` (los que produzca el runner)

**Prerrequisitos (verificar antes de empezar; si falta alguno, PARAR y avisar al usuario):**
- Docker disponible: `docker compose up -d` (Neo4j).
- `.env` con credenciales LLM válidas (`LOOM_LLM_MODEL`, `LOOM_LLM_API_BASE`, `LOOM_LLM_API_KEY`).
- Esta task hace llamadas LLM reales (con cache `.llm_cache/`). Coste esperado: bajo para las fixtures crafted; moderado para pride-and-prejudice (61 capítulos, 1 llamada por escena).

- [ ] **Step 1: Levantar el entorno**

```bash
docker compose up -d
uv run uvicorn backend.api.app:app --port 8000 &
sleep 3 && curl -s http://127.0.0.1:8000/docs > /dev/null && echo API_OK
```

Expected: `API_OK`.

- [ ] **Step 2: Ingerir y extraer las dos obras del gate (cronometrar)**

```bash
for f in crafted-three-chapters.txt crafted-two-chapters.epub; do
  curl -s -F "file=@eval/fixtures/$f" http://127.0.0.1:8000/manuscripts
done
# → anotar cada manuscript_id devuelto
time uv run python -m backend.extraction.run <manuscript_id_txt>
time uv run python -m backend.extraction.run <manuscript_id_epub>
```

Expected: extracción termina sin errores; personajes Elena y Marco en el grafo.

- [ ] **Step 3: Inspección del reparto (SC-008, cronometrar)**

```bash
curl -s "http://127.0.0.1:8000/manuscripts/<id>/characters" | python -m json.tool
```

Verificar contra el libro: personajes presentes, alias consolidados, primera aparición con cita. Anotar el tiempo (< 15 min).

- [ ] **Step 4: Ejecutar el eval de las obras del gate (SC-006, cronometrar)**

```bash
time uv run python -m eval.characters.runner --work crafted-three-chapters.txt --manuscript-id <id_txt>
time uv run python -m eval.characters.runner --work crafted-two-chapters.epub --manuscript-id <id_epub>
uv run pytest tests/eval -q
```

Expected: B³ Resol. con valor REAL (no 0.0, no "no medido") en ambas obras; gate `tests/eval` en PASS (no SKIP) para las dos obras; cada eval < 10 min. Si alguna métrica queda bajo umbral, NO ajustar umbrales ni gold para forzar el pass: investigar la causa (prompt, resolución, segmentación) y reportar al usuario con los números reales.

- [ ] **Step 5: Pride and Prejudice E2E (obra real grande)**

```bash
curl -s -F "file=@eval/fixtures/pride-and-prejudice.txt" http://127.0.0.1:8000/manuscripts
time uv run python -m backend.extraction.run <manuscript_id_pp>
uv run python -m eval.characters.runner --work pride-and-prejudice.txt --manuscript-id <id_pp>
curl -s "http://127.0.0.1:8000/manuscripts/<id_pp>/merge-candidates" | python -m json.tool
```

Expected: detection F1 y silent_bad_merges reales; `B³ Resol.: no medido` (gold sin menciones — correcto); cola de merge-candidates inspeccionable. Anotar fricciones encontradas (T038 pide corregirlas: si aparecen bugs, aplicar systematic-debugging antes de continuar).

- [ ] **Step 6: Limpieza y cierre documental**

```bash
rm eval/results/characters-pride-and-prejudice-txt-20260614-4072e29.json
uv run ruff check backend eval tests
uv run pytest -q
```

Expected: lint limpio, suite completa verde (el gate ahora PASS con Neo4j arriba).

- Marcar `specs/002-char-extraction-eval/tasks.md:143` T038 como `[x]`.
- `docs/ABOUT.md:127`: M1 → `✅ Completo` (solo si Steps 4-5 pasaron).

- [ ] **Step 7: Commit**

```bash
git add eval/results/ specs/002-char-extraction-eval/tasks.md docs/ABOUT.md
git commit -m "feat(m1): T038 complete — E2E quickstart run with real B3 metrics

Fresh eval results for both gate works (real B-cubed) and
pride-and-prejudice (detection + silent merges; B3 unmeasured pending
mention-level gold). SC-006/SC-008 timings verified. Stale stub-metric
result removed."
```

---

## Fuera de scope (explícito)

- Anotar menciones de pride-and-prejudice (miles de menciones en 61 capítulos — inviable a mano; su B³ queda `null` honestamente). Si en el futuro se quiere, anotar un subconjunto de capítulos como obra separada.
- Cambiar umbrales, prompts o la cascada de resolución (solo si la Task 7 revela fallos, y entonces vía systematic-debugging + reporte al usuario).
- El fixture docx no tiene gold de personajes; sigue siendo solo de segmentación.

## Self-review (hecho al escribir el plan)

- Cobertura vs known-issues.md: pred_clusters reales → Task 4; gold con menciones → Task 5; MergeCandidate reales → Tasks 1+4; nota de coherencia ABOUT → Task 6. T038 → Task 7. ✓
- Tipos consistentes: `candidate_pairs: list[tuple[dict, dict]]` (Task 1) = lo que produce `_load_system_output` (Task 4); claves `"c{n}/s{m}::{surface}"` idénticas en alignment, golds y tests. ✓
- El gate exige B³ no-null (Task 4/3f) y el validador de golds (Task 5) impide regresión a golds sin menciones. ✓
