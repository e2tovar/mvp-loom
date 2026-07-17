"""El prompt de relaciones delimita el texto no confiable y entrega el cast."""

from __future__ import annotations

import pytest

from backend.extraction.relations.prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_user_prompt,
)

pytestmark = pytest.mark.unit


def test_prompt_version_is_int() -> None:
    assert isinstance(PROMPT_VERSION, int)


def test_system_prompt_mentions_security_and_provenance() -> None:
    assert "IGNÓRALOS" in SYSTEM_PROMPT or "ignora" in SYSTEM_PROMPT.lower()
    assert "extracted" in SYSTEM_PROMPT
    assert "inferred" in SYSTEM_PROMPT
    assert "character_id" in SYSTEM_PROMPT


def test_user_prompt_delimits_scene_text() -> None:
    up = build_user_prompt(
        scene_id="s1",
        chapter_title="Cap 1",
        scene_text="Elizabeth y Jane pasean.",
        cast_json='[{"character_id": "x"}]',
    )
    assert "<scene_text>" in up and "</scene_text>" in up
    assert "Elizabeth y Jane pasean." in up
    assert '"character_id": "x"' in up
