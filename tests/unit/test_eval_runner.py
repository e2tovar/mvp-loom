"""Tests de run_eval con la carga del grafo simulada (sin Neo4j ni LLM)."""

from __future__ import annotations

import pytest

from eval.characters import runner

GOLD_ANNOTATED = {
    "work": "obra-test",
    "characters": [
        {
            "gold_id": "elena",
            "canonical_name": "Elena",
            "aliases": [],
            "role": "protagonist",
            "is_mentioned_only": False,
            "appearances": ["c1/s0"],
            "mentions": [{"scene": "c1/s0", "surface": "Elena"}],
        },
        {
            "gold_id": "marco",
            "canonical_name": "Marco",
            "aliases": [],
            "role": "secondary",
            "is_mentioned_only": False,
            "appearances": ["c2/s0"],
            "mentions": [{"scene": "c2/s0", "surface": "Marco"}],
        },
    ],
}

GOLD_NOT_ANNOTATED = {
    "work": "obra-test",
    "characters": [
        {
            "gold_id": "elena",
            "canonical_name": "Elena",
            "aliases": [],
            "role": "protagonist",
            "is_mentioned_only": False,
            "appearances": ["c1/s0"],
        },
    ],
}

PRED_ENTITIES = [
    {"character_id": "m:ch:1", "canonical_name": "Elena", "aliases": []},
    {"character_id": "m:ch:2", "canonical_name": "Marco", "aliases": []},
]


def _patch(monkeypatch, gold, clusters, pairs=None):
    monkeypatch.setattr(runner, "_load_gold", lambda work: gold)
    monkeypatch.setattr(
        runner,
        "_load_system_output",
        lambda mid: (PRED_ENTITIES, clusters, pairs or []),
    )


def test_b3_real_perfect(monkeypatch):
    _patch(
        monkeypatch,
        GOLD_ANNOTATED,
        [["c1/s0::elena"], ["c2/s0::marco"]],
    )
    result = runner.run_eval("obra-test")
    assert result["resolution_b3"]["f1"] == pytest.approx(1.0)
    assert result["passed"] is True


def test_b3_real_bad_clustering_fails_gate(monkeypatch):
    # El sistema fusionó las menciones de Elena y Marco en un solo cluster
    _patch(monkeypatch, GOLD_ANNOTATED, [["c1/s0::elena", "c2/s0::marco"]])
    result = runner.run_eval("obra-test")
    assert result["resolution_b3"]["f1"] < 0.85
    assert result["passed"] is False


def test_b3_null_when_gold_not_annotated(monkeypatch):
    _patch(monkeypatch, GOLD_NOT_ANNOTATED, [["c1/s0::elena"]])
    result = runner.run_eval("obra-test")
    assert result["resolution_b3"] is None
    # detection sigue contando: 2 pred vs 1 gold → precision 0.5 → F1 < 0.90
    assert result["passed"] is False


def test_b3_null_does_not_block_when_detection_ok(monkeypatch):
    gold = {
        "work": "obra-test",
        "characters": [
            {
                "gold_id": "elena",
                "canonical_name": "Elena",
                "aliases": [],
                "role": "protagonist",
                "is_mentioned_only": False,
                "appearances": ["c1/s0"],
            },
            {
                "gold_id": "marco",
                "canonical_name": "Marco",
                "aliases": [],
                "role": "secondary",
                "is_mentioned_only": False,
                "appearances": ["c2/s0"],
            },
        ],
    }
    _patch(monkeypatch, gold, [["c1/s0::elena"]])
    result = runner.run_eval("obra-test")
    assert result["resolution_b3"] is None
    assert result["passed"] is True
