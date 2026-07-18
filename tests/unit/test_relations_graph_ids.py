"""IDs deterministas y par canónico de M2 (INV-M2-2)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.graph.relations import canonical_pair, evidence_id, replace_relates_to

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


def test_replace_relates_to_enforces_canonical_order_and_swaps_roles() -> None:
    """FR-007 / INV-M2-5: un par no canónico no debe crear una arista invertida."""
    mock_sess = MagicMock()
    rel = {
        "character_a_id": "m:ch:b",
        "character_b_id": "m:ch:a",
        "rel_type": "ally",
        "descriptor": "friends",
        "role_a": "mentor",
        "role_b": "student",
        "provenance": "auto",
        "confidence": 0.9,
        "evidence_count": 2,
        "first_evidence_id": "s1:re:deadbeef",
    }

    replace_relates_to(mock_sess, "m", [rel])

    assert mock_sess.run.call_count == 2
    merge_call = mock_sess.run.call_args_list[1]
    kwargs = merge_call.kwargs

    assert kwargs["cid_a"] == "m:ch:a"
    assert kwargs["cid_b"] == "m:ch:b"
    # role_a was attached to character_b_id ("m:ch:a") originally as role_b;
    # since cid_a is now "m:ch:a", role_a must carry "student" (role_b's original value)
    assert kwargs["role_a"] == "student"
    assert kwargs["role_b"] == "mentor"


def test_replace_relates_to_passes_through_already_canonical_pair() -> None:
    mock_sess = MagicMock()
    rel = {
        "character_a_id": "m:ch:a",
        "character_b_id": "m:ch:b",
        "rel_type": "ally",
        "descriptor": "friends",
        "role_a": "mentor",
        "role_b": "student",
        "provenance": "auto",
        "confidence": 0.9,
        "evidence_count": 2,
        "first_evidence_id": "s1:re:deadbeef",
    }

    replace_relates_to(mock_sess, "m", [rel])

    merge_call = mock_sess.run.call_args_list[1]
    kwargs = merge_call.kwargs

    assert kwargs["cid_a"] == "m:ch:a"
    assert kwargs["cid_b"] == "m:ch:b"
    assert kwargs["role_a"] == "mentor"
    assert kwargs["role_b"] == "student"
