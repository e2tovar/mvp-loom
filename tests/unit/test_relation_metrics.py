"""Métricas de relaciones: detección de pares + type accuracy por provenance."""

from __future__ import annotations

import pytest

from eval.relations.metrics import align_gold_to_pred, relation_metrics

pytestmark = pytest.mark.unit

GOLD_CHARS = [
    {"gold_id": "elena", "canonical_name": "Elena", "aliases": ["Ele"]},
    {"gold_id": "miguel", "canonical_name": "Miguel", "aliases": []},
    {"gold_id": "sofia", "canonical_name": "Sofía", "aliases": []},
]
PRED_ENTITIES = [
    {"character_id": "m:ch:1", "canonical_name": "Elena", "aliases": []},
    {"character_id": "m:ch:2", "canonical_name": "Miguel", "aliases": []},
]


def _pred_rel(cid_a: str, cid_b: str, rel_type: str = "family", prov: str = "extracted") -> dict:
    a, b = sorted([cid_a, cid_b])
    return {
        "character_a_id": a, "character_b_id": b,
        "rel_type": rel_type, "provenance": prov,
    }


def test_alignment_greedy_with_accent_fold() -> None:
    alignment = align_gold_to_pred(GOLD_CHARS, PRED_ENTITIES)
    assert alignment == {"elena": "m:ch:1", "miguel": "m:ch:2"}


def test_perfect_detection_and_type() -> None:
    gold_rels = [{"a": "elena", "b": "miguel", "rel_type": "family", "provenance": "extracted"}]
    pred_rels = [_pred_rel("m:ch:1", "m:ch:2")]
    m = relation_metrics(gold_rels, pred_rels, {"elena": "m:ch:1", "miguel": "m:ch:2"})
    assert m["pair_detection"]["extracted"]["f1"] == 1.0
    assert m["type_accuracy"]["extracted"] == 1.0


def test_unaligned_gold_counts_as_miss() -> None:
    gold_rels = [{"a": "elena", "b": "sofia", "rel_type": "friendship", "provenance": "extracted"}]
    m = relation_metrics(gold_rels, [], {"elena": "m:ch:1"})
    assert m["pair_detection"]["extracted"]["recall"] == 0.0


def test_wrong_type_detected_but_inaccurate() -> None:
    gold_rels = [{"a": "elena", "b": "miguel", "rel_type": "family", "provenance": "extracted"}]
    pred_rels = [_pred_rel("m:ch:1", "m:ch:2", rel_type="romantic")]
    m = relation_metrics(gold_rels, pred_rels, {"elena": "m:ch:1", "miguel": "m:ch:2"})
    assert m["pair_detection"]["extracted"]["f1"] == 1.0
    assert m["type_accuracy"]["extracted"] == 0.0


def test_inferred_pred_does_not_hit_extracted_precision() -> None:
    gold_rels = [{"a": "elena", "b": "miguel", "rel_type": "family", "provenance": "extracted"}]
    pred_rels = [_pred_rel("m:ch:1", "m:ch:2", prov="inferred")]
    m = relation_metrics(gold_rels, pred_rels, {"elena": "m:ch:1", "miguel": "m:ch:2"})
    # bucket extracted: no hay preds extracted → precision sin denominador (0 preds)
    assert m["pair_detection"]["extracted"]["recall"] == 0.0
    # bucket all: sí detecta
    assert m["pair_detection"]["all"]["recall"] == 1.0


def test_no_matched_pairs_gives_none_accuracy() -> None:
    m = relation_metrics([], [], {})
    assert m["type_accuracy"]["all"] is None
