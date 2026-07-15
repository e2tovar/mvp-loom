"""Tests de integración US1: pipeline con LLM falso + Neo4j real (T019).

Verifican: grafo correcto, INV-M1-2 (procedencia), INV-M1-3 (sin huérfanos),
INV-M1-5 (capa cruda intacta), endpoints GET devuelven el contrato.
"""

from __future__ import annotations

from datetime import UTC
from unittest.mock import MagicMock

import pytest

from backend.extraction.schemas import (
    CharacterCandidateOut,
    MentionOut,
    SceneExtraction,
)
from backend.graph import characters as char_graph
from backend.graph.client import session as db_session
from backend.graph.raw_layer import manuscript_exists, write_raw_layer
from backend.ingest.models import Chapter, Manuscript, Scene

# ── Fixtures ──────────────────────────────────────────────────────────────────

SCENE_TEXT = "Elizabeth walked into the room. Mr. Darcy stood by the window."
MANUSCRIPT_ID = "test-manuscript-char-flow"


def _fake_extraction() -> SceneExtraction:
    return SceneExtraction(
        mentions=[
            MentionOut(
                surface="Elizabeth",
                kind="name",
                links_to=None,
                quote="Elizabeth walked into the room.",
            ),
            MentionOut(
                surface="Mr. Darcy",
                kind="name",
                links_to=None,
                quote="Mr. Darcy stood by the window.",
            ),
        ],
        new_characters=[
            CharacterCandidateOut(
                canonical_name="Elizabeth",
                aliases=["Lizzy"],
                role="protagonist",
                is_present_in_scene=True,
            ),
            CharacterCandidateOut(
                canonical_name="Mr. Darcy",
                aliases=["Darcy"],
                role="secondary",
                is_present_in_scene=True,
            ),
        ],
    )


def _build_manuscript() -> Manuscript:
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
        title="Chapter One",
        kind="chapter",
        word_count=12,
        start_offset=0,
        end_offset=len(SCENE_TEXT),
        scenes=[scene],
    )
    from datetime import datetime

    return Manuscript(
        manuscript_id=MANUSCRIPT_ID,
        title="Test Book",
        source_format="txt",
        word_count=12,
        chapter_count=1,
        scene_count=1,
        ingested_at=datetime.now(UTC),
        chapters=[chapter],
        non_narrative=[],
    )


@pytest.fixture(autouse=True)
def clean_m1_nodes(neo4j_session):
    """Limpia nodos de M1 del manuscrito de prueba antes/después de cada test.

    Scoped por manuscript_id (como en test_idempotent_rerun / test_merge_review_flow):
    un DELETE sin scope borraría la extracción de obras reales en la BD de desarrollo.
    """
    _wipe = (
        "MATCH (n) WHERE n.manuscript_id = $mid "
        "AND (n:Character OR n:Mention OR n:MergeCandidate) DETACH DELETE n"
    )
    neo4j_session.run(_wipe, mid=MANUSCRIPT_ID)
    yield
    neo4j_session.run(_wipe, mid=MANUSCRIPT_ID)


@pytest.fixture
def manuscript_in_graph(neo4j_session):
    """Escribe la capa cruda M0 del manuscrito de prueba."""
    ms = _build_manuscript()
    write_raw_layer(neo4j_session, ms)
    return ms


@pytest.fixture
def fake_llm():
    client = MagicMock()
    client.complete_structured.return_value = _fake_extraction()
    return client


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_pipeline_writes_characters_and_mentions(neo4j_session, manuscript_in_graph, fake_llm):
    """El pipeline crea Character y Mention correctos en el grafo."""
    from backend.extraction.pipeline import run_pipeline

    result = run_pipeline(MANUSCRIPT_ID, llm_client=fake_llm)

    assert result.total_characters >= 1
    assert result.total_mentions >= 1

    with db_session() as sess:
        chars = char_graph.get_characters_list(sess, MANUSCRIPT_ID)
    assert len(chars) >= 1
    names = [c["canonical_name"] for c in chars]
    assert any("Elizabeth" in n for n in names)


@pytest.mark.integration
def test_first_appearance_quote_populated(neo4j_session, manuscript_in_graph, fake_llm):
    """contracts/api.md:60 — first_appearance.quote no debe quedar hardcodeado a None."""
    from backend.extraction.pipeline import run_pipeline

    run_pipeline(MANUSCRIPT_ID, llm_client=fake_llm)

    with db_session() as sess:
        chars = char_graph.get_characters_list(sess, MANUSCRIPT_ID)

    assert chars, "Se esperaban personajes tras la extracción"
    for char in chars:
        quote = char["first_appearance"]["quote"]
        assert quote is not None and len(quote) > 0, (
            f"{char['canonical_name']}: first_appearance.quote sigue en None"
        )


@pytest.mark.integration
def test_inv_m1_2_provenance_verifiable(neo4j_session, manuscript_in_graph, fake_llm):
    """INV-M1-2: cada Mention tiene scene_id, start_offset, end_offset y quote."""
    from backend.extraction.pipeline import run_pipeline

    run_pipeline(MANUSCRIPT_ID, llm_client=fake_llm)

    with db_session() as sess:
        result = sess.run(
            """
            MATCH (mn:Mention {manuscript_id: $mid})
            RETURN mn.scene_id AS sid, mn.start_offset AS s,
                   mn.end_offset AS e, mn.quote AS q
            """,
            mid=MANUSCRIPT_ID,
        )
        for row in result:
            assert row["sid"] is not None
            assert row["s"] is not None and row["e"] is not None
            assert row["q"] is not None and len(row["q"]) > 0


@pytest.mark.integration
def test_inv_m1_3_no_orphan_mentions(neo4j_session, manuscript_in_graph, fake_llm):
    """INV-M1-3: ninguna Mention queda huérfana (sin IN_SCENE ni HAS_MENTION)."""
    from backend.extraction.pipeline import run_pipeline

    run_pipeline(MANUSCRIPT_ID, llm_client=fake_llm)

    with db_session() as sess:
        orphan_scene = sess.run(
            """
            MATCH (mn:Mention {manuscript_id: $mid})
            WHERE NOT (mn)-[:IN_SCENE]->(:Scene)
            RETURN count(mn) AS n
            """,
            mid=MANUSCRIPT_ID,
        ).single()
        orphan_char = sess.run(
            """
            MATCH (mn:Mention {manuscript_id: $mid})
            WHERE NOT (:Character)-[:HAS_MENTION]->(mn)
            RETURN count(mn) AS n
            """,
            mid=MANUSCRIPT_ID,
        ).single()
    assert orphan_scene["n"] == 0, "Menciones sin IN_SCENE encontradas"
    assert orphan_char["n"] == 0, "Menciones sin Character encontradas"


@pytest.mark.integration
def test_inv_m1_5_raw_layer_intact(neo4j_session, manuscript_in_graph, fake_llm):
    """INV-M1-5: la capa cruda (Manuscript/Chapter/Scene) no se modifica."""
    from backend.extraction.pipeline import run_pipeline

    run_pipeline(MANUSCRIPT_ID, llm_client=fake_llm)

    with db_session() as sess:
        assert manuscript_exists(sess, MANUSCRIPT_ID)
        scenes = sess.run(
            "MATCH (s:Scene {manuscript_id: $mid}) RETURN count(s) AS n",
            mid=MANUSCRIPT_ID,
        ).single()
    assert scenes["n"] == 1


@pytest.mark.integration
def test_pipeline_idempotent(neo4j_session, manuscript_in_graph, fake_llm):
    """Ejecutar dos veces produce el mismo grafo (sin duplicados)."""
    from backend.extraction.pipeline import run_pipeline

    run_pipeline(MANUSCRIPT_ID, llm_client=fake_llm)
    run_pipeline(MANUSCRIPT_ID, llm_client=fake_llm)

    with db_session() as sess:
        chars = char_graph.get_characters_list(sess, MANUSCRIPT_ID)
    names = [c["canonical_name"] for c in chars]
    assert len(names) == len(set(names)), "Personajes duplicados tras dos ejecuciones"


@pytest.mark.integration
def test_api_get_characters_returns_contract(
    neo4j_session, manuscript_in_graph, fake_llm, api_client
):
    """GET /manuscripts/{id}/characters devuelve el contrato esperado."""
    from backend.extraction.pipeline import run_pipeline

    run_pipeline(MANUSCRIPT_ID, llm_client=fake_llm)

    resp = api_client.get(f"/manuscripts/{MANUSCRIPT_ID}/characters")
    assert resp.status_code == 200
    data = resp.json()
    assert "characters" in data
    assert "character_count" in data
    assert "pending_merge_candidates" in data


@pytest.mark.integration
def test_api_not_extracted_returns_409(neo4j_session, manuscript_in_graph, api_client):
    """GET /characters antes de extraer devuelve 409 not_extracted."""
    resp = api_client.get(f"/manuscripts/{MANUSCRIPT_ID}/characters")
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "not_extracted"


@pytest.mark.integration
def test_api_unknown_manuscript_returns_404(api_client):
    """GET /characters con manuscrito inexistente devuelve 404."""
    resp = api_client.get("/manuscripts/nonexistent-id/characters")
    assert resp.status_code == 404


@pytest.mark.integration
def test_character_props_monotonic(neo4j_session):
    """is_mentioned_only nunca vuelve a true; role no se degrada a unknown."""
    from backend.graph import characters as char_graph

    mid = "test-monotonic-props"
    neo4j_session.run(
        "MATCH (n) WHERE n.manuscript_id = $mid "
        "AND (n:Character OR n:Mention OR n:MergeCandidate) DETACH DELETE n",
        mid=mid,
    )
    neo4j_session.run("MERGE (:Manuscript {manuscript_id: $mid})", mid=mid)

    # Aparece presente y con rol
    char_graph.upsert_character(
        neo4j_session, mid, "Elizabeth Bennet", ["Lizzy"],
        role="protagonist", is_mentioned_only=False, first_scene_id="s1",
    )
    # Re-aparece como solo-mencionada y con rol unknown (candidato tardío)
    char_graph.upsert_character(
        neo4j_session, mid, "Elizabeth Bennet", ["Lizzy"],
        role="unknown", is_mentioned_only=True, first_scene_id="s9",
    )

    rec = neo4j_session.run(
        "MATCH (c:Character {manuscript_id: $mid, canonical_name: 'Elizabeth Bennet'}) "
        "RETURN c.is_mentioned_only AS m, c.role AS r, c.first_scene_id AS f",
        mid=mid,
    ).single()
    assert rec["m"] is False          # no se degrada
    assert rec["r"] == "protagonist"  # no se pisa con unknown
    assert rec["f"] == "s1"           # first_scene_id es ON CREATE only

    neo4j_session.run(
        "MATCH (n) WHERE n.manuscript_id = $mid DETACH DELETE n", mid=mid
    )


@pytest.mark.integration
def test_known_character_gains_appearance_and_counters(neo4j_session):
    """Un personaje conocido que reaparece gana APPEARS_IN; contadores derivados, no acumulados."""
    from backend.graph import characters as char_graph

    mid = "test-appears-counters"
    neo4j_session.run(
        "MATCH (n) WHERE n.manuscript_id = $mid DETACH DELETE n", mid=mid
    )
    neo4j_session.run("MERGE (:Manuscript {manuscript_id: $mid})", mid=mid)
    for sid in ["ta:s1", "ta:s2"]:
        neo4j_session.run(
            "MERGE (s:Scene {scene_id: $sid}) SET s.manuscript_id = $mid",
            sid=sid, mid=mid,
        )

    cid = char_graph.upsert_character(
        neo4j_session, mid, "Ana", [], "secondary", False, "ta:s1"
    )
    # Dos menciones en s1, una en s2
    char_graph.upsert_mention(neo4j_session, "ta:s1", mid, cid, "Ana", "name", 0, 3, "Ana entró.")
    char_graph.upsert_mention(neo4j_session, "ta:s1", mid, cid, "Anita", "alias", 10, 15, "…Anita…")
    char_graph.upsert_mention(neo4j_session, "ta:s2", mid, cid, "Ana", "name", 5, 8, "…Ana…")
    char_graph.upsert_appears_in(neo4j_session, cid, "ta:s1", "present")
    char_graph.upsert_appears_in(neo4j_session, cid, "ta:s2", "mentioned")

    # Recompute dos veces: idempotente
    char_graph.recompute_counters(neo4j_session, mid)
    char_graph.recompute_counters(neo4j_session, mid)

    rec = neo4j_session.run(
        "MATCH (c:Character {character_id: $cid}) "
        "RETURN c.mention_count AS mc, c.appearance_count AS ac", cid=cid,
    ).single()
    assert rec["mc"] == 3
    assert rec["ac"] == 2

    rel = neo4j_session.run(
        "MATCH (c:Character {character_id: $cid})-[r:APPEARS_IN]->(s:Scene {scene_id: 'ta:s1'}) "
        "RETURN r.mention_count AS rmc, r.kind AS kind, r.first_mention_id AS fm", cid=cid,
    ).single()
    assert rel["rmc"] == 2          # menciones DEL personaje en ESA escena
    assert rel["kind"] == "present"
    assert rel["fm"]                 # primera mención por offset

    neo4j_session.run(
        "MATCH (n) WHERE n.manuscript_id = $mid DETACH DELETE n", mid=mid
    )
    neo4j_session.run("MATCH (s:Scene) WHERE s.scene_id STARTS WITH 'ta:' DETACH DELETE s")


@pytest.mark.integration
def test_appears_in_kind_upgrades_to_present(neo4j_session):
    """kind solo mejora: mentioned → present, nunca al revés."""
    from backend.graph import characters as char_graph

    mid = "test-kind-upgrade"
    neo4j_session.run("MATCH (n) WHERE n.manuscript_id = $mid DETACH DELETE n", mid=mid)
    neo4j_session.run("MERGE (:Manuscript {manuscript_id: $mid})", mid=mid)
    neo4j_session.run("MERGE (s:Scene {scene_id: 'tk:s1'}) SET s.manuscript_id = $mid", mid=mid)

    cid = char_graph.upsert_character(neo4j_session, mid, "Bo", [], "minor", False, "tk:s1")
    char_graph.upsert_appears_in(neo4j_session, cid, "tk:s1", "mentioned")
    char_graph.upsert_appears_in(neo4j_session, cid, "tk:s1", "present")
    char_graph.upsert_appears_in(neo4j_session, cid, "tk:s1", "mentioned")

    rec = neo4j_session.run(
        "MATCH (:Character {character_id: $cid})-[r:APPEARS_IN]->() RETURN r.kind AS k",
        cid=cid,
    ).single()
    assert rec["k"] == "present"

    neo4j_session.run("MATCH (n) WHERE n.manuscript_id = $mid DETACH DELETE n", mid=mid)
    neo4j_session.run("MATCH (s:Scene {scene_id: 'tk:s1'}) DETACH DELETE s")


@pytest.mark.integration
def test_wipe_extraction_removes_only_m1_layer(neo4j_session):
    """wipe_extraction borra Character/Mention/MergeCandidate sin tocar la capa cruda."""
    from backend.extraction.wipe import wipe_extraction
    from backend.graph import characters as char_graph

    mid = "test-wipe-m1"
    neo4j_session.run("MATCH (n) WHERE n.manuscript_id = $mid DETACH DELETE n", mid=mid)
    neo4j_session.run("MERGE (:Manuscript {manuscript_id: $mid})", mid=mid)
    neo4j_session.run("MERGE (s:Scene {scene_id: 'tw:s1'}) SET s.manuscript_id = $mid", mid=mid)

    cid = char_graph.upsert_character(neo4j_session, mid, "Ana", [], "minor", False, "tw:s1")
    char_graph.upsert_mention(neo4j_session, "tw:s1", mid, cid, "Ana", "name", 0, 3, "Ana.")

    counts = wipe_extraction(neo4j_session, mid)
    assert counts["Character"] == 1
    assert counts["Mention"] == 1

    remaining = neo4j_session.run(
        "MATCH (n) WHERE n.manuscript_id = $mid RETURN labels(n)[0] AS l", mid=mid
    ).value()
    assert set(remaining) == {"Manuscript", "Scene"}  # capa cruda intacta

    neo4j_session.run("MATCH (n) WHERE n.manuscript_id = $mid DETACH DELETE n", mid=mid)


@pytest.mark.integration
def test_is_mentioned_only_derived_from_present_appearance(neo4j_session):
    """recompute_counters marca is_mentioned_only=false si hay APPEARS_IN present,
    true si todas las apariciones son 'mentioned'."""
    from backend.graph import characters as char_graph

    mid = "test-mo-derived"
    neo4j_session.run("MATCH (n) WHERE n.manuscript_id = $mid DETACH DELETE n", mid=mid)
    neo4j_session.run("MERGE (:Manuscript {manuscript_id: $mid})", mid=mid)
    for sid in ["md:s1", "md:s2"]:
        neo4j_session.run(
            "MERGE (s:Scene {scene_id: $sid}) SET s.manuscript_id = $mid", sid=sid, mid=mid
        )

    # Personaje presente en s2 pero cuyo nodo se creó con is_mentioned_only=True
    # (primera extracción fue una mención en s1).
    cid_p = char_graph.upsert_character(
        neo4j_session, mid, "Elizabeth", [], "protagonist", True, "md:s1"
    )
    char_graph.upsert_appears_in(neo4j_session, cid_p, "md:s1", "mentioned")
    char_graph.upsert_appears_in(neo4j_session, cid_p, "md:s2", "present")

    # Personaje que solo se menciona, nunca presente.
    cid_m = char_graph.upsert_character(
        neo4j_session, mid, "Old Uncle", [], "minor", True, "md:s1"
    )
    char_graph.upsert_appears_in(neo4j_session, cid_m, "md:s1", "mentioned")

    char_graph.recompute_counters(neo4j_session, mid)
    char_graph.recompute_counters(neo4j_session, mid)  # idempotente

    p = neo4j_session.run(
        "MATCH (c:Character {character_id: $cid}) RETURN c.is_mentioned_only AS m", cid=cid_p
    ).single()
    m = neo4j_session.run(
        "MATCH (c:Character {character_id: $cid}) RETURN c.is_mentioned_only AS m", cid=cid_m
    ).single()
    assert p["m"] is False   # tiene aparición present -> NO solo-mencionado
    assert m["m"] is True    # solo mentioned -> solo-mencionado

    neo4j_session.run("MATCH (n) WHERE n.manuscript_id = $mid DETACH DELETE n", mid=mid)
    neo4j_session.run("MATCH (s:Scene) WHERE s.scene_id STARTS WITH 'md:' DETACH DELETE s")


@pytest.mark.integration
def test_pipeline_persists_animal_entity_kind(neo4j_session, manuscript_in_graph):
    """El pipeline propaga entity_kind del candidato ('animal') al Character persistido."""
    from backend.extraction.pipeline import run_pipeline

    fake = MagicMock()
    fake.complete_structured.return_value = SceneExtraction(
        mentions=[
            MentionOut(
                surface="Hedwig",
                kind="name",
                links_to=None,
                quote="Hedwig voló por la ventana.",
            )
        ],
        new_characters=[
            CharacterCandidateOut(
                canonical_name="Hedwig",
                is_present_in_scene=True,
                entity_kind="animal",
            )
        ],
    )

    run_pipeline(MANUSCRIPT_ID, llm_client=fake)

    with db_session() as sess:
        char_list = char_graph.get_characters_list(sess, MANUSCRIPT_ID)
        chars = {c["canonical_name"]: c for c in char_list}
    assert chars["Hedwig"]["entity_kind"] == "animal"


@pytest.mark.integration
def test_entity_kind_persisted_and_defaulted(neo4j_session, manuscript_in_graph):
    """entity_kind se persiste en Character y se devuelve (default 'person' para nodos antiguos)."""
    cid_person = char_graph.upsert_character(
        neo4j_session, MANUSCRIPT_ID, "Elena", [], "protagonist", False, "sc-1"
    )
    cid_animal = char_graph.upsert_character(
        neo4j_session, MANUSCRIPT_ID, "Hedwig", [], "minor", False, "sc-1", entity_kind="animal"
    )
    char_list = char_graph.get_characters_list(neo4j_session, MANUSCRIPT_ID)
    chars = {c["character_id"]: c for c in char_list}

    assert chars[cid_person]["entity_kind"] == "person"
    assert chars[cid_animal]["entity_kind"] == "animal"
