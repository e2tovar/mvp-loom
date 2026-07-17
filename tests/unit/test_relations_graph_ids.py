"""IDs deterministas y par canónico de M2 (INV-M2-2)."""

from __future__ import annotations

import pytest

from backend.graph.relations import canonical_pair, evidence_id

pytestmark = pytest.mark.unit


def test_canonical_pair_is_order_independent() -> None:
    assert canonical_pair("m:ch:b", "m:ch:a") == ("m:ch:a", "m:ch:b")
    assert canonical_pair("m:ch:a", "m:ch:b") == ("m:ch:a", "m:ch:b")


def test_evidence_id_is_deterministic_and_order_independent() -> None:
    e1 = evidence_id("s1", "m:ch:a", "m:ch:b")
    e2 = evidence_id("s1", "m:ch:b", "m:ch:a")
    assert e1 == e2
    assert e1.startswith("s1:re:")


def test_evidence_id_varies_by_scene_and_pair() -> None:
    base = evidence_id("s1", "m:ch:a", "m:ch:b")
    assert evidence_id("s2", "m:ch:a", "m:ch:b") != base
    assert evidence_id("s1", "m:ch:a", "m:ch:c") != base
