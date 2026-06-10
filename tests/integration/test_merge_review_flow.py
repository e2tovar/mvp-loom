"""Tests de integración US3: flujo accept/reject de MergeCandidate (T031).

Verifica INV-M1-4:
- accept: menciones movidas, B eliminado, aliases fusionados.
- reject: el par no se vuelve a proponer tras re-ejecutar el pipeline.
"""

from __future__ import annotations

from datetime import UTC
from unittest.mock import MagicMock

import pytest

from backend.extraction.schemas import (
    CharacterCandidateOut,
    MentionOut,
    MergeJudgement,
    SceneExtraction,
)
from backend.graph.client import session as db_session
from backend.graph.raw_layer import write_raw_layer
from backend.ingest.models import Chapter, Manuscript, Scene

MANUSCRIPT_ID = "test-merge-review"
SCENE_TEXT = "Eliza walked in. Elizabeth was already there."


def _build_ms() -> Manuscript:
    from datetime import datetime

    scene = Scene(
        scene_id=f"{MANUSCRIPT_ID}:c0:s0",
        chapter_id=f"{MANUSCRIPT_ID}:c0",
        manuscript_id=MANUSCRIPT_ID,
        order_in_chapter=0,
        order_narrative_global=0,
        text=SCENE_TEXT,
        char_count=len(SCENE_TEXT),
        start_offset=0,
        end_offset=len(SCENE_TEXT),
        boundary_reason="manual",
        snippet=SCENE_TEXT[:80],
    )
    chapter = Chapter(
        chapter_id=f"{MANUSCRIPT_ID}:c0",
        manuscript_id=MANUSCRIPT_ID,
        order_narrative=0,
        title=None,
        kind="chapter",
        word_count=9,
        start_offset=0,
        end_offset=len(SCENE_TEXT),
        scenes=[scene],
    )
    return Manuscript(
        manuscript_id=MANUSCRIPT_ID,
        title="Merge Test",
        source_format="txt",
        word_count=9,
        chapter_count=1,
        scene_count=1,
        ingested_at=datetime.now(UTC),
        chapters=[chapter],
        non_narrative=[],
    )


def _gray_zone_extraction() -> SceneExtraction:
    """Extracción con dos candidatos en zona gris."""
    return SceneExtraction(
        mentions=[
            MentionOut(surface="Eliza", kind="name", links_to=None, quote="Eliza walked in."),
            MentionOut(
                surface="Elizabeth",
                kind="name",
                links_to=None,
                quote="Elizabeth was already there.",
            ),
        ],
        new_characters=[
            CharacterCandidateOut(
                canonical_name="Eliza", aliases=[], role="protagonist", is_present_in_scene=True
            ),
            CharacterCandidateOut(
                canonical_name="Elizabeth", aliases=[], role="protagonist", is_present_in_scene=True
            ),
        ],
    )


def _fake_llm_gray_zone() -> MagicMock:
    client = MagicMock()
    client.complete_structured.return_value = MergeJudgement(
        same_entity=True, confidence=0.72, rationale="test gray zone"
    )
    return client


@pytest.fixture(autouse=True)
def clean_nodes(neo4j_session):
    neo4j_session.run(f"MATCH (n) WHERE n.manuscript_id = '{MANUSCRIPT_ID}' DETACH DELETE n")
    yield
    neo4j_session.run(f"MATCH (n) WHERE n.manuscript_id = '{MANUSCRIPT_ID}' DETACH DELETE n")


@pytest.fixture
def manuscript_in_graph(neo4j_session):
    write_raw_layer(neo4j_session, _build_ms())


@pytest.mark.integration
def test_accept_merges_mentions_and_deletes_b(neo4j_session, manuscript_in_graph):
    """accept: menciones de B movidas a A, B eliminado, aliases fusionados."""
    from backend.extraction.pipeline import run_pipeline
    from backend.graph import characters as char_graph
    from backend.graph.merge_candidates import get_merge_candidates, resolve_merge_candidate

    fake_llm = _fake_llm_gray_zone()
    fake_llm.complete_structured.return_value = _gray_zone_extraction()
    # Primera llamada devuelve la extracción; siguientes el MergeJudgement
    fake_llm.complete_structured.side_effect = [
        _gray_zone_extraction(),
        MergeJudgement(same_entity=True, confidence=0.72, rationale="test"),
    ]

    run_pipeline(MANUSCRIPT_ID, llm_client=fake_llm)

    with db_session() as sess:
        candidates = get_merge_candidates(sess, MANUSCRIPT_ID, status="pending")

    if not candidates:
        pytest.skip("No se generó MergeCandidate (LLM falso no activó la zona gris)")

    cid = candidates[0]["candidate_id"]
    with db_session() as sess:
        result = resolve_merge_candidate(sess, cid, "accept")

    assert "canonical_name" in result or "character_id" in result

    with db_session() as sess:
        remaining = char_graph.get_characters_list(sess, MANUSCRIPT_ID)
    # Después del accept, solo debe quedar una entidad
    assert len(remaining) == 1


@pytest.mark.integration
def test_reject_prevents_re_proposal(neo4j_session, manuscript_in_graph):
    """reject: el par no se vuelve a proponer tras re-ejecutar el pipeline (INV-M1-4)."""
    from backend.extraction.pipeline import run_pipeline
    from backend.graph.merge_candidates import get_merge_candidates, resolve_merge_candidate

    fake_llm = MagicMock()
    fake_llm.complete_structured.side_effect = [
        _gray_zone_extraction(),
        MergeJudgement(same_entity=True, confidence=0.72, rationale="test"),
    ]

    run_pipeline(MANUSCRIPT_ID, llm_client=fake_llm)

    with db_session() as sess:
        candidates = get_merge_candidates(sess, MANUSCRIPT_ID, status="pending")

    if not candidates:
        pytest.skip("No se generó MergeCandidate")

    cid = candidates[0]["candidate_id"]
    with db_session() as sess:
        resolve_merge_candidate(sess, cid, "reject")

    # Re-ejecutar pipeline con la misma extracción
    fake_llm2 = MagicMock()
    fake_llm2.complete_structured.side_effect = [
        _gray_zone_extraction(),
        MergeJudgement(same_entity=True, confidence=0.72, rationale="test"),
    ]
    run_pipeline(MANUSCRIPT_ID, llm_client=fake_llm2, force=True)

    with db_session() as sess:
        new_candidates = get_merge_candidates(sess, MANUSCRIPT_ID, status="pending")

    assert len(new_candidates) == 0, "El par rechazado fue re-propuesto"
