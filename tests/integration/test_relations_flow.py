"""Integración M2: pipeline con LLM falso + Neo4j real.

Verifica: INV-M2-1 (sustento), INV-M2-2 (determinismo), INV-M2-3 (capas
intactas), INV-M2-4 (universo cerrado), INV-M2-5 (umbral) y el happy path
del endpoint (FR-014).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from backend.extraction.relations.pipeline import run_relations_pipeline
from backend.extraction.relations.schemas import SceneRelationEvidence, SceneRelations
from backend.extraction.schemas import CharacterCandidateOut, MentionOut, SceneExtraction
from backend.graph import relations as rel_graph
from backend.graph.client import session as db_session
from backend.graph.raw_layer import write_raw_layer
from backend.ingest.models import Chapter, Manuscript, Scene

pytestmark = pytest.mark.integration

MANUSCRIPT_ID = "test-m2-flow"
SCENE_TEXT = "Elena abrazó a su hermano Miguel. Elena y Miguel recordaron a su madre."


def build_manuscript() -> Manuscript:
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
        boundary_reason="separator",
        snippet=SCENE_TEXT[:80],
    )
    chapter = Chapter(
        chapter_id=f"{MANUSCRIPT_ID}:c0",
        manuscript_id=MANUSCRIPT_ID,
        order_narrative=0,
        title="Capítulo 1",
        start_offset=0,
        end_offset=len(SCENE_TEXT),
        word_count=len(SCENE_TEXT.split()),
        scenes=[scene],
    )
    return Manuscript(
        manuscript_id=MANUSCRIPT_ID,
        title="M2 flow",
        source_format="txt",
        word_count=len(SCENE_TEXT.split()),
        chapter_count=1,
        ingested_at=datetime.now(UTC),
        chapters=[chapter],
    )


def _fake_m1() -> SceneExtraction:
    return SceneExtraction(
        mentions=[
            MentionOut(surface="Elena", kind="name", links_to=None,
                       quote="Elena abrazó a su hermano Miguel."),
            MentionOut(surface="Miguel", kind="name", links_to=None,
                       quote="Elena abrazó a su hermano Miguel."),
        ],
        new_characters=[
            CharacterCandidateOut(canonical_name="Elena", aliases=[],
                                  role="protagonist", is_present_in_scene=True),
            CharacterCandidateOut(canonical_name="Miguel", aliases=[],
                                  role="secondary", is_present_in_scene=True),
        ],
        present_entities=["Elena", "Miguel"],
    )


def _fake_m2(cid_a: str, cid_b: str) -> SceneRelations:
    return SceneRelations(
        evidences=[
            SceneRelationEvidence(
                character_a_id=cid_a,
                character_b_id=cid_b,
                rel_type="family",
                descriptor="hermanos",
                role_a=None,
                role_b=None,
                provenance="extracted",
                confidence=0.95,
                quote="Elena abrazó a su hermano Miguel.",
            )
        ]
    )


def _setup_m1(sess) -> dict[str, str]:
    """Ingesta + extracción M1 con LLM falso. Devuelve canonical_name → character_id."""
    from backend.extraction.pipeline import run_pipeline

    write_raw_layer(sess, build_manuscript())
    llm = MagicMock()
    llm.complete_structured.return_value = _fake_m1()
    run_pipeline(MANUSCRIPT_ID, llm_client=llm)
    from backend.graph import characters as char_graph

    chars = char_graph.get_characters_list(sess, MANUSCRIPT_ID)
    return {c["canonical_name"]: c["character_id"] for c in chars}


def test_full_flow_and_invariants(neo4j_session, api_client) -> None:
    ids = _setup_m1(neo4j_session)
    cid_a, cid_b = ids["Elena"], ids["Miguel"]

    llm = MagicMock()
    llm.complete_structured.return_value = _fake_m2(cid_a, cid_b)
    result = run_relations_pipeline(MANUSCRIPT_ID, llm_client=llm)

    assert result.evidences_written == 1
    assert result.relations_written == 1

    # INV-M2-1: la arista está sustentada por una evidencia con Scene y 2 Character
    rows = neo4j_session.run(
        """
        MATCH (a:Character)-[r:RELATES_TO]->(b:Character)
        WHERE a.manuscript_id = $mid
        MATCH (re:RelationEvidence {evidence_id: r.first_evidence_id})
        MATCH (re)-[:IN_SCENE]->(s:Scene)
        MATCH (re)-[:ABOUT]->(c:Character)
        RETURN r.rel_type AS rel_type, r.provenance AS prov,
               s.scene_id AS sid, count(c) AS about_count, re.quote AS quote
        """,
        mid=MANUSCRIPT_ID,
    ).single()
    assert rows["rel_type"] == "family"
    assert rows["prov"] == "extracted"
    assert rows["about_count"] == 2
    assert rows["quote"] in SCENE_TEXT  # SC-003: cita rastreable

    # INV-M2-2: re-ejecutar converge (mismos ids, misma única arista)
    result2 = run_relations_pipeline(MANUSCRIPT_ID, llm_client=llm)
    count = neo4j_session.run(
        "MATCH (:Character {manuscript_id: $mid})-[r:RELATES_TO]->() RETURN count(r) AS n",
        mid=MANUSCRIPT_ID,
    ).single()["n"]
    assert count == 1
    assert result2.relations_written == 1

    # INV-M2-3: capa M1 intacta (mention_count no cambió)
    m1_count = neo4j_session.run(
        "MATCH (c:Character {manuscript_id: $mid}) RETURN sum(c.mention_count) AS n",
        mid=MANUSCRIPT_ID,
    ).single()["n"]
    assert m1_count == 2

    # FR-014: endpoint happy path
    resp = api_client.get(f"/manuscripts/{MANUSCRIPT_ID}/relations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["relation_count"] == 1
    assert body["relations"][0]["rel_type"] == "family"


def test_below_threshold_writes_evidence_but_no_edge(neo4j_session) -> None:
    ids = _setup_m1(neo4j_session)
    weak = _fake_m2(ids["Elena"], ids["Miguel"])
    weak.evidences[0].provenance = "inferred"
    weak.evidences[0].confidence = 0.3

    llm = MagicMock()
    llm.complete_structured.return_value = weak
    result = run_relations_pipeline(MANUSCRIPT_ID, llm_client=llm)

    assert result.evidences_written == 1
    assert result.relations_written == 0  # INV-M2-5
    n_edges = neo4j_session.run(
        "MATCH (:Character {manuscript_id: $mid})-[r:RELATES_TO]->() RETURN count(r) AS n",
        mid=MANUSCRIPT_ID,
    ).single()["n"]
    assert n_edges == 0
    n_ev = neo4j_session.run(
        "MATCH (re:RelationEvidence {manuscript_id: $mid}) RETURN count(re) AS n",
        mid=MANUSCRIPT_ID,
    ).single()["n"]
    assert n_ev == 1  # la evidencia persiste (FR-005)


def test_out_of_cast_never_reaches_graph(neo4j_session) -> None:
    ids = _setup_m1(neo4j_session)
    bad = _fake_m2(ids["Elena"], "m:ch:fantasma")
    llm = MagicMock()
    llm.complete_structured.return_value = bad
    run_relations_pipeline(MANUSCRIPT_ID, llm_client=llm)
    n = neo4j_session.run(
        "MATCH (re:RelationEvidence {manuscript_id: $mid}) RETURN count(re) AS n",
        mid=MANUSCRIPT_ID,
    ).single()["n"]
    assert n == 0  # INV-M2-4 / SC-004
