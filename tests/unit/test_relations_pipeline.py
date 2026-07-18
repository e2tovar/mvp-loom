"""Pipeline M2 con LLM falso y capa de grafo mockeada (FR-001/002/016/017)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.core.errors import ExtractionError, NotExtractedError
from backend.extraction.relations.schemas import SceneRelationEvidence, SceneRelations

pytestmark = pytest.mark.unit

MID = "test-m2-pipe"

_SCENES = [
    {"scene_id": "s0", "text": "Elena y Miguel discuten.", "chapter_title": "C1", "order": 0},
    {"scene_id": "s1", "text": "Elena pasea sola.", "chapter_title": "C1", "order": 1},
]

_CASTS = {
    "s0": [
        {"character_id": "a", "canonical_name": "Elena", "aliases": []},
        {"character_id": "b", "canonical_name": "Miguel", "aliases": []},
    ],
    "s1": [{"character_id": "a", "canonical_name": "Elena", "aliases": []}],
}


def _evidence(cid_a="a", cid_b="b", conf=0.9) -> SceneRelationEvidence:
    return SceneRelationEvidence(
        character_a_id=cid_a,
        character_b_id=cid_b,
        rel_type="family",
        descriptor="hermanos",
        provenance="extracted",
        confidence=conf,
        quote="Elena y Miguel discuten.",
    )


def _run(llm_out, has_extraction=True, evidences_by_pair=None):
    from backend.extraction.relations import pipeline as pipe

    llm = MagicMock()
    llm.complete_structured.side_effect = llm_out
    written: list[dict] = []
    replaced: list[list[dict]] = []

    with (
        patch.object(pipe, "_load_scenes", return_value=_SCENES),
        patch.object(pipe.char_graph, "has_extraction", return_value=has_extraction),
        patch.object(pipe.rel_graph, "get_scene_casts", return_value=_CASTS),
        patch.object(
            pipe.rel_graph,
            "upsert_relation_evidence",
            side_effect=lambda sess, mid, sid, ev: written.append(ev) or "eid",
        ),
        patch.object(
            pipe.rel_graph,
            "get_evidences_by_pair",
            return_value=evidences_by_pair or {},
        ),
        patch.object(
            pipe.rel_graph,
            "replace_relates_to",
            side_effect=lambda sess, mid, rels: replaced.append(rels),
        ),
        patch.object(pipe, "db_session", MagicMock()),
    ):
        result = pipe.run_relations_pipeline(MID, llm_client=llm)
    return result, written, replaced, llm


def test_requires_m1_extraction() -> None:
    from backend.extraction.relations import pipeline as pipe

    with (
        patch.object(pipe, "_load_scenes", return_value=_SCENES),
        patch.object(pipe.char_graph, "has_extraction", return_value=False),
        patch.object(pipe, "db_session", MagicMock()),
    ):
        with pytest.raises(NotExtractedError):
            pipe.run_relations_pipeline(MID, llm_client=MagicMock())


def test_requires_m1_extraction_before_llm_client_construction() -> None:
    """FR-016: sin cliente LLM explícito, el check de M1 debe correr ANTES de
    construir el LiteLLMClient por defecto. Si el orden estuviera invertido,
    un entorno sin LOOM_LLM_MODEL configurado levantaría LLMUnavailableError
    en vez de NotExtractedError. `LiteLLMClient` se mockea para probar la
    aserción de forma determinista sin depender de si el .env local trae la
    variable configurada: la construcción no debe ocurrir en absoluto cuando
    M1 no está extraído."""
    from backend.extraction.relations import pipeline as pipe

    with (
        patch.object(pipe, "_load_scenes", return_value=_SCENES),
        patch.object(pipe.char_graph, "has_extraction", return_value=False),
        patch.object(pipe, "db_session", MagicMock()),
        patch("backend.llm.litellm_client.LiteLLMClient") as mock_client_cls,
    ):
        with pytest.raises(NotExtractedError):
            pipe.run_relations_pipeline(MID)

    mock_client_cls.assert_not_called()


def test_scene_with_small_cast_skips_llm() -> None:
    result, written, _, llm = _run([SceneRelations(evidences=[_evidence()])])
    # solo s0 tiene cast >= 2 → 1 llamada LLM, s1 skipped
    assert llm.complete_structured.call_count == 1
    assert result.scenes_skipped == 1
    assert len(written) == 1


def test_out_of_cast_evidence_dropped() -> None:
    bad = _evidence(cid_a="a", cid_b="zzz")
    result, written, _, _ = _run([SceneRelations(evidences=[bad])])
    assert written == []


def test_duplicate_pair_keeps_highest_confidence() -> None:
    out = SceneRelations(evidences=[_evidence(conf=0.6), _evidence(conf=0.95)])
    _, written, _, _ = _run([out])
    assert len(written) == 1
    assert written[0]["confidence"] == 0.95


def test_scene_failure_does_not_abort(caplog) -> None:
    result, written, _, _ = _run([ExtractionError("boom")])
    assert result.scenes_failed == 1
    assert written == []


def test_aggregation_runs_over_graph_evidences() -> None:
    stored = {
        ("a", "b"): [
            {
                "evidence_id": "s0:re:x",
                "character_a_id": "a",
                "character_b_id": "b",
                "rel_type": "family",
                "descriptor": "hermanos",
                "role_a": None,
                "role_b": None,
                "provenance": "extracted",
                "confidence": 0.9,
                "narrative_order": 0,
            }
        ]
    }
    _, _, replaced, _ = _run(
        [SceneRelations(evidences=[_evidence()])], evidences_by_pair=stored
    )
    assert len(replaced) == 1
    assert replaced[0][0]["rel_type"] == "family"


def test_pair_normalized_to_canonical_order_with_role_swap() -> None:
    inverted = SceneRelationEvidence(
        character_a_id="b",
        character_b_id="a",
        rel_type="family",
        descriptor="padre e hija",
        role_a="padre",
        role_b="hija",
        provenance="extracted",
        confidence=0.9,
        quote="Elena y Miguel discuten.",
    )
    _, written, _, _ = _run([SceneRelations(evidences=[inverted])])
    assert written[0]["character_a_id"] == "a"
    assert written[0]["role_a"] == "hija"  # el rol viaja con el personaje
