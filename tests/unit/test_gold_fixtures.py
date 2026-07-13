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
