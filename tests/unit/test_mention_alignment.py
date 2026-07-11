"""Tests de la alineación de menciones gold↔pred para B³ (cierre de known-issues M1)."""

from __future__ import annotations

import pytest

from eval.characters.alignment import (
    gold_mention_clusters,
    mention_key,
    pred_mention_clusters,
)
from eval.characters.metrics import bcubed_f1


def _gold_char(gold_id: str, mentions: list[dict] | None) -> dict:
    char = {
        "gold_id": gold_id,
        "canonical_name": gold_id.title(),
        "aliases": [],
        "role": "secondary",
        "is_mentioned_only": False,
        "appearances": [],
    }
    if mentions is not None:
        char["mentions"] = mentions
    return char


def test_mention_key_normalizes_surface():
    assert mention_key("c1/s0", "  Elena ") == "c1/s0::elena"
    assert mention_key("c1/s0", "ELENA") == "c1/s0::elena"


def test_gold_clusters_none_when_not_annotated():
    gold = {"characters": [_gold_char("elena", None)]}
    assert gold_mention_clusters(gold) is None


def test_gold_clusters_inconsistent_annotation_raises():
    gold = {
        "characters": [
            _gold_char("elena", [{"scene": "c1/s0", "surface": "Elena"}]),
            _gold_char("marco", None),
        ]
    }
    with pytest.raises(ValueError, match="marco"):
        gold_mention_clusters(gold)


def test_gold_and_pred_share_key_space_perfect_b3():
    gold = {
        "characters": [
            _gold_char(
                "elena",
                [
                    {"scene": "c1/s0", "surface": "Elena"},
                    {"scene": "c2/s1", "surface": "Elena"},
                ],
            ),
            _gold_char("marco", [{"scene": "c2/s0", "surface": "Marco"}]),
        ]
    }
    scene_coords = {"sc-a": "c1/s0", "sc-b": "c2/s0", "sc-c": "c2/s1"}
    pred = [
        [
            {"scene_id": "sc-a", "surface": "Elena", "kind": "name"},
            {"scene_id": "sc-c", "surface": "Elena", "kind": "name"},
        ],
        [{"scene_id": "sc-b", "surface": "Marco", "kind": "name"}],
    ]
    scores = bcubed_f1(gold_mention_clusters(gold), pred_mention_clusters(pred, scene_coords))
    assert scores.f1 == pytest.approx(1.0)


def test_pred_clusters_exclude_pronouns_and_unknown_scenes():
    scene_coords = {"sc-a": "c1/s0"}
    pred = [
        [
            {"scene_id": "sc-a", "surface": "Elena", "kind": "name"},
            {"scene_id": "sc-a", "surface": "ella", "kind": "pronoun_resolved"},
            {"scene_id": "sc-zz", "surface": "Elena", "kind": "name"},
        ]
    ]
    assert pred_mention_clusters(pred, scene_coords) == [["c1/s0::elena"]]


def test_pred_clusters_dedupe_repeated_key():
    scene_coords = {"sc-a": "c1/s0"}
    pred = [
        [
            {"scene_id": "sc-a", "surface": "Elena", "kind": "name"},
            {"scene_id": "sc-a", "surface": "elena", "kind": "alias"},
        ]
    ]
    assert pred_mention_clusters(pred, scene_coords) == [["c1/s0::elena"]]
