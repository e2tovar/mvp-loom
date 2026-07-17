"""Los golds de relaciones son estructuralmente válidos y consistentes con el
gold de personajes de su obra (FR-010)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).resolve().parent.parent.parent / "eval" / "fixtures"
WORKS = [
    "crafted-three-chapters.txt",
    "crafted-two-chapters.epub",
    "pride-and-prejudice.txt",
]
REL_TYPES = {"family", "romantic", "friendship", "antagonism", "professional", "social", "other"}


@pytest.mark.parametrize("work", WORKS)
def test_relations_gold_is_valid(work: str) -> None:
    rel_path = FIXTURES / f"{work}.relations.gold.json"
    chars_path = FIXTURES / f"{work}.characters.gold.json"
    assert rel_path.exists(), f"falta {rel_path}"

    gold = json.loads(rel_path.read_text(encoding="utf-8"))
    chars = json.loads(chars_path.read_text(encoding="utf-8"))
    known_ids = {c["gold_id"] for c in chars["characters"]}

    seen_pairs: set[tuple[str, str]] = set()
    for rel in gold["relations"]:
        assert rel["a"] in known_ids, f"{rel['a']} no está en el characters gold"
        assert rel["b"] in known_ids, f"{rel['b']} no está en el characters gold"
        assert rel["a"] < rel["b"], f"par sin orden alfabético: {rel['a']},{rel['b']}"
        assert rel["rel_type"] in REL_TYPES
        assert rel["provenance"] in {"extracted", "inferred"}
        pair = (rel["a"], rel["b"])
        assert pair not in seen_pairs, f"par duplicado: {pair}"
        seen_pairs.add(pair)
