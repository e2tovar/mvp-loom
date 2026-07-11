"""Tests unitarios de métricas del eval harness (T025)."""

from __future__ import annotations

import pytest

from eval.characters.metrics import bcubed_f1, count_silent_bad_merges, detection_f1


def _entity(name: str, aliases=None) -> dict:
    return {"canonical_name": name, "aliases": aliases or []}


# ── Detection F1 ──────────────────────────────────────────────────────────────


def test_detection_perfect():
    gold = [_entity("Elizabeth"), _entity("Darcy")]
    pred = [_entity("Elizabeth"), _entity("Darcy")]
    scores = detection_f1(gold, pred)
    assert scores.precision == pytest.approx(1.0)
    assert scores.recall == pytest.approx(1.0)
    assert scores.f1 == pytest.approx(1.0)


def test_detection_empty_pred():
    gold = [_entity("Elizabeth")]
    pred = []
    scores = detection_f1(gold, pred)
    assert scores.f1 == pytest.approx(0.0)


def test_detection_empty_gold_and_pred():
    scores = detection_f1([], [])
    assert scores.f1 == pytest.approx(1.0)


def test_detection_alias_matching():
    """El emparejamiento usa solapamiento de aliases."""
    gold = [_entity("Elizabeth Bennet", aliases=["Lizzy", "Miss Bennet"])]
    pred = [_entity("Lizzy", aliases=["Elizabeth"])]
    scores = detection_f1(gold, pred)
    assert scores.f1 == pytest.approx(1.0)


def test_detection_over_prediction_lowers_precision():
    gold = [_entity("Elizabeth")]
    pred = [_entity("Elizabeth"), _entity("Ghost")]
    scores = detection_f1(gold, pred)
    assert scores.precision == pytest.approx(0.5)
    assert scores.recall == pytest.approx(1.0)


def test_detection_under_prediction_lowers_recall():
    gold = [_entity("Elizabeth"), _entity("Darcy")]
    pred = [_entity("Elizabeth")]
    scores = detection_f1(gold, pred)
    assert scores.precision == pytest.approx(1.0)
    assert scores.recall == pytest.approx(0.5)


# ── B-cubed ───────────────────────────────────────────────────────────────────


def test_bcubed_perfect():
    gold = [["m1", "m2"], ["m3"]]
    pred = [["m1", "m2"], ["m3"]]
    scores = bcubed_f1(gold, pred)
    assert scores.f1 == pytest.approx(1.0)


def test_bcubed_empty():
    scores = bcubed_f1([], [])
    assert scores.f1 == pytest.approx(1.0)


def test_bcubed_over_merge_penalizes():
    """Fusionar dos clusters gold en uno pred baja la precisión (sobre-fusión)."""
    gold = [["m1", "m2"], ["m3", "m4"]]
    pred = [["m1", "m2", "m3", "m4"]]  # sobre-fusión
    scores = bcubed_f1(gold, pred)
    assert scores.precision < 1.0
    assert scores.recall == pytest.approx(1.0)


def test_bcubed_under_merge_penalizes():
    """Separar un cluster gold en dos pred baja el recall (sub-fusión)."""
    gold = [["m1", "m2", "m3", "m4"]]
    pred = [["m1", "m2"], ["m3", "m4"]]  # sub-fusión
    scores = bcubed_f1(gold, pred)
    assert scores.recall < 1.0
    assert scores.precision == pytest.approx(1.0)


# ── Silent bad merges ─────────────────────────────────────────────────────────


def test_no_silent_bad_merges_when_separate():
    gold = [_entity("Ana"), _entity("María")]
    pred = [_entity("Ana"), _entity("María")]
    sbm = count_silent_bad_merges(gold, pred, [])
    assert sbm == 0


def test_silent_bad_merge_detected():
    """Si pred fusiona dos entidades del gold sin candidato registrado → sbm=1."""
    gold = [_entity("Ana"), _entity("María")]
    # El sistema fusionó ambas en "Ana"
    pred = [_entity("Ana", aliases=["María"])]
    sbm = count_silent_bad_merges(gold, pred, [])
    assert sbm == 1


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
