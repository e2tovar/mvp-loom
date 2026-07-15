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


def test_validate_system_output_raises_when_char_list_empty():
    with pytest.raises(RuntimeError, match="Sin extracción o capa cruda ausente"):
        runner._validate_system_output([], {"m:s:1": "c1/s0"}, "mid-x")


def test_validate_system_output_raises_when_scene_coords_empty_but_chars_present():
    """Caso real: conftest.py borra Manuscript/Chapter/Scene pero deja Character/Mention."""
    with pytest.raises(RuntimeError, match="Sin extracción o capa cruda ausente"):
        runner._validate_system_output([{"character_id": "m:ch:1"}], {}, "mid-x")


def test_validate_system_output_ok_when_both_present():
    runner._validate_system_output(
        [{"character_id": "m:ch:1"}], {"m:s:1": "c1/s0"}, "mid-x"
    )  # no debe lanzar


def test_run_eval_exits_when_system_output_missing(monkeypatch):
    """Si el grafo no tiene datos utilizables, run_eval debe sys.exit(1), no dar 0.0."""
    monkeypatch.setattr(runner, "_load_gold", lambda work: GOLD_ANNOTATED)

    def _raise(mid):
        raise RuntimeError(f"Sin extracción o capa cruda ausente para manuscript_id={mid!r}")

    monkeypatch.setattr(runner, "_load_system_output", _raise)

    with pytest.raises(SystemExit) as exc_info:
        runner.run_eval("obra-test")
    assert exc_info.value.code == 1


def test_animals_excluded_from_detection(monkeypatch):
    """entity_kind='animal' no debe contarse como falso positivo de detección.

    El gold nunca anota animales (mascotas como Hedwig): si se cuelan en la
    comparación, penalizan la precisión de forma injusta. El filtro real vive
    dentro de `_load_system_output`, así que este test parchea las
    dependencias que esa función consume (`get_characters_list` et al.) en vez
    de reemplazar `_load_system_output` entera — de lo contrario el test no
    ejercitaría el filtro de producción y pasaría sin implementarlo.
    """
    from contextlib import contextmanager

    import backend.graph.characters as char_graph_module
    import backend.graph.client as client_module
    import backend.graph.merge_candidates as merge_module

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
            }
        ],
    }
    pred_with_animal = [
        {"character_id": "m:ch:1", "canonical_name": "Elena", "aliases": [], "entity_kind": "person"},
        {"character_id": "m:ch:2", "canonical_name": "Hedwig", "aliases": [], "entity_kind": "animal"},
    ]

    @contextmanager
    def fake_session():
        yield object()

    monkeypatch.setattr(runner, "_load_gold", lambda work: gold)
    monkeypatch.setattr(client_module, "session", fake_session)
    monkeypatch.setattr(
        char_graph_module, "get_characters_list", lambda sess, mid: pred_with_animal
    )
    monkeypatch.setattr(
        char_graph_module, "get_scene_coordinates", lambda sess, mid: {"m:s:1": "c1/s0"}
    )
    monkeypatch.setattr(
        char_graph_module, "get_character_detail", lambda sess, mid, cid: {"mentions": []}
    )
    monkeypatch.setattr(
        merge_module, "get_merge_candidates", lambda sess, mid, status="all": []
    )

    result = runner.run_eval("obra-test")
    # Sin el animal: 1 pred vs 1 gold → detección perfecta.
    assert result["detection"]["f1"] == pytest.approx(1.0)


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
