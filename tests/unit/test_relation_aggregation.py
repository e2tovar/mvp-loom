"""Reglas deterministas de agregación por par (spec FR-004, FR-005)."""

from __future__ import annotations

import pytest

from backend.extraction.relations.aggregation import WRITE_THRESHOLD, aggregate_pair

pytestmark = pytest.mark.unit


def _ev(
    rel_type: str = "family",
    provenance: str = "extracted",
    confidence: float = 0.9,
    order: int = 0,
    descriptor: str = "hermanos",
    role_a: str | None = None,
    role_b: str | None = None,
    eid: str | None = None,
) -> dict:
    return {
        "evidence_id": eid or f"s{order}:re:x",
        "character_a_id": "m:ch:a",
        "character_b_id": "m:ch:b",
        "rel_type": rel_type,
        "descriptor": descriptor,
        "role_a": role_a,
        "role_b": role_b,
        "provenance": provenance,
        "confidence": confidence,
        "narrative_order": order,
    }


def test_extracted_outweighs_inferred() -> None:
    # 1 extracted family (peso 2) vs 3 inferred antagonism (peso 3) → antagonism gana
    evs = [
        _ev(rel_type="family", provenance="extracted", order=0),
        _ev(rel_type="antagonism", provenance="inferred", order=1),
        _ev(rel_type="antagonism", provenance="inferred", order=2),
        _ev(rel_type="antagonism", provenance="inferred", order=3),
    ]
    agg = aggregate_pair(evs)
    assert agg is not None and agg["rel_type"] == "antagonism"
    # pero 1 extracted (2) vs 1 inferred (1) → extracted gana
    evs2 = [
        _ev(rel_type="family", provenance="extracted", order=0),
        _ev(rel_type="antagonism", provenance="inferred", order=1),
    ]
    agg2 = aggregate_pair(evs2)
    assert agg2 is not None and agg2["rel_type"] == "family"


def test_tie_breaks_by_latest_extracted() -> None:
    # antagonism extracted (orden 0) vs romantic extracted (orden 9): empate 2-2 → romantic
    evs = [
        _ev(rel_type="antagonism", provenance="extracted", order=0),
        _ev(rel_type="romantic", provenance="extracted", order=9),
    ]
    agg = aggregate_pair(evs)
    assert agg is not None and agg["rel_type"] == "romantic"


def test_descriptor_and_confidence_from_winning_type() -> None:
    evs = [
        _ev(confidence=0.6, descriptor="parientes", order=0),
        _ev(confidence=0.95, descriptor="hermanos", order=1),
    ]
    agg = aggregate_pair(evs)
    assert agg is not None
    assert agg["descriptor"] == "hermanos"
    assert agg["confidence"] == 0.95


def test_conflicting_roles_become_none() -> None:
    evs = [
        _ev(role_a="padre", role_b="hija", order=0),
        _ev(role_a="tío", role_b="sobrina", order=1),
    ]
    agg = aggregate_pair(evs)
    assert agg is not None
    assert agg["role_a"] is None and agg["role_b"] is None


def test_roles_kept_when_consistent() -> None:
    evs = [
        _ev(role_a=None, role_b=None, order=0),
        _ev(role_a="padre", role_b="hija", order=1),
    ]
    agg = aggregate_pair(evs)
    assert agg is not None
    assert agg["role_a"] == "padre" and agg["role_b"] == "hija"


def test_below_threshold_returns_none() -> None:
    evs = [_ev(provenance="inferred", confidence=WRITE_THRESHOLD - 0.1)]
    assert aggregate_pair(evs) is None


def test_provenance_and_counts() -> None:
    evs = [
        _ev(provenance="inferred", confidence=0.7, order=2, eid="s2:re:x"),
        _ev(provenance="extracted", confidence=0.8, order=5, eid="s5:re:x"),
        _ev(rel_type="social", provenance="inferred", confidence=0.6, order=0, eid="s0:re:x"),
    ]
    agg = aggregate_pair(evs)
    assert agg is not None
    assert agg["provenance"] == "extracted"
    assert agg["evidence_count"] == 3
    assert agg["first_evidence_id"] == "s0:re:x"


def test_empty_evidences_returns_none() -> None:
    assert aggregate_pair([]) is None
