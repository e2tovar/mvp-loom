import pytest
from pydantic import ValidationError

from backend.extraction.attributes.schemas import (
    SceneAttributeEvidence,
    SceneAttributes,
    key_class,
)


def test_key_class_static_vs_stateful():
    assert key_class("eye_color") == "static"
    assert key_class("status") == "stateful"


def test_evidence_accepts_valid_key():
    ev = SceneAttributeEvidence(
        character_id="m:ch:ana", key="eye_color",
        value_norm="green", value_quote="sus ojos verdes", confidence=0.9,
    )
    assert ev.value_norm == "green"


def test_evidence_rejects_key_outside_catalog():
    with pytest.raises(ValidationError):
        SceneAttributeEvidence(
            character_id="m:ch:ana", key="mood",  # no en catálogo
            value_norm="happy", value_quote="feliz", confidence=0.5,
        )


def test_evidence_rejects_empty_value_norm():
    with pytest.raises(ValidationError):
        SceneAttributeEvidence(
            character_id="m:ch:ana", key="hair",
            value_norm="  ", value_quote="pelo", confidence=0.5,
        )


def test_scene_attributes_defaults_empty():
    out = SceneAttributes(evidences=[])
    assert out.evidences == [] and out.notes is None
