"""Contratos Pydantic de M2: validación estricta de la salida del LLM."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.extraction.relations.schemas import (
    SCHEMA_VERSION,
    SceneRelationEvidence,
    SceneRelations,
)

pytestmark = pytest.mark.unit


def _ev(**overrides) -> dict:
    base = {
        "character_a_id": "m1:ch:aaa",
        "character_b_id": "m1:ch:bbb",
        "rel_type": "family",
        "descriptor": "hermanos",
        "role_a": None,
        "role_b": None,
        "provenance": "extracted",
        "confidence": 0.9,
        "quote": "su hermana Jane",
    }
    base.update(overrides)
    return base


def test_valid_evidence_parses() -> None:
    ev = SceneRelationEvidence.model_validate(_ev())
    assert ev.rel_type == "family"


def test_self_pair_rejected() -> None:
    with pytest.raises(ValidationError):
        SceneRelationEvidence.model_validate(_ev(character_b_id="m1:ch:aaa"))


def test_confidence_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        SceneRelationEvidence.model_validate(_ev(confidence=1.5))


def test_unknown_rel_type_rejected() -> None:
    with pytest.raises(ValidationError):
        SceneRelationEvidence.model_validate(_ev(rel_type="enemies"))


def test_scene_relations_empty_is_valid() -> None:
    out = SceneRelations.model_validate({"evidences": []})
    assert out.evidences == []


def test_schema_version_present() -> None:
    assert isinstance(SCHEMA_VERSION, int)
