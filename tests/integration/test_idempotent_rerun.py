"""Test de integración US4: re-ejecución idempotente con cache (T035).

Verifica INV-M1-1: la segunda ejecución no llama al LLM y produce el mismo grafo.
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
from backend.graph.raw_layer import write_raw_layer
from backend.ingest.models import Chapter, Manuscript, Scene

MANUSCRIPT_ID = "test-idempotent-rerun"
SCENE_TEXT = "Ana entró al salón."


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
        boundary_reason="separator",
        snippet=SCENE_TEXT,
    )
    chapter = Chapter(
        chapter_id=f"{MANUSCRIPT_ID}:c0",
        manuscript_id=MANUSCRIPT_ID,
        order_narrative=0,
        title=None,
        kind="chapter",
        word_count=4,
        start_offset=0,
        end_offset=len(SCENE_TEXT),
        scenes=[scene],
    )
    return Manuscript(
        manuscript_id=MANUSCRIPT_ID,
        title="Rerun Test",
        source_format="txt",
        word_count=4,
        chapter_count=1,
        scene_count=1,
        ingested_at=datetime.now(UTC),
        chapters=[chapter],
        non_narrative=[],
    )


def _fake_extraction() -> SceneExtraction:
    return SceneExtraction(
        mentions=[MentionOut(surface="Ana", kind="name", links_to=None, quote=SCENE_TEXT)],
        new_characters=[
            CharacterCandidateOut(
                canonical_name="Ana", aliases=[], role="protagonist", is_present_in_scene=True
            )
        ],
    )


@pytest.fixture(autouse=True)
def clean(neo4j_session):
    neo4j_session.run(f"MATCH (n) WHERE n.manuscript_id = '{MANUSCRIPT_ID}' DETACH DELETE n")
    yield
    neo4j_session.run(f"MATCH (n) WHERE n.manuscript_id = '{MANUSCRIPT_ID}' DETACH DELETE n")


@pytest.fixture
def manuscript_in_graph(neo4j_session):
    write_raw_layer(neo4j_session, _build_ms())


@pytest.mark.integration
def test_second_run_zero_llm_calls(tmp_path, neo4j_session, manuscript_in_graph):
    """Segunda ejecución con cache caliente: 0 llamadas al LLM, grafo idéntico."""
    from backend.extraction.pipeline import run_pipeline
    from backend.extraction.prompts import PROMPT_VERSION
    from backend.extraction.schemas import SCHEMA_VERSION
    from backend.llm.cache import ExtractionCache

    cache = ExtractionCache(
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        model="test-model",
        cache_dir=tmp_path / "cache",
    )

    llm1 = MagicMock()
    llm1.complete_structured.return_value = _fake_extraction()
    run_pipeline(MANUSCRIPT_ID, llm_client=llm1, cache=cache)

    with db_session() as sess:
        chars_first = char_graph.get_characters_list(sess, MANUSCRIPT_ID)

    llm2 = MagicMock()
    llm2.complete_structured.return_value = _fake_extraction()
    run_pipeline(MANUSCRIPT_ID, llm_client=llm2, cache=cache)

    assert llm2.complete_structured.call_count == 0, (
        f"Segunda ejecución hizo {llm2.complete_structured.call_count} llamadas al LLM (esperado 0)"
    )

    with db_session() as sess:
        chars_second = char_graph.get_characters_list(sess, MANUSCRIPT_ID)

    ids_first = {c["character_id"] for c in chars_first}
    ids_second = {c["character_id"] for c in chars_second}
    assert ids_first == ids_second, "Los character_ids cambiaron entre ejecuciones (INV-M1-1)"


@pytest.mark.integration
def test_force_reruns_llm(tmp_path, neo4j_session, manuscript_in_graph):
    """--force re-llama al LLM aunque la cache esté caliente."""
    from backend.extraction.pipeline import run_pipeline
    from backend.extraction.prompts import PROMPT_VERSION
    from backend.extraction.schemas import SCHEMA_VERSION
    from backend.llm.cache import ExtractionCache

    cache = ExtractionCache(
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        model="test-model",
        cache_dir=tmp_path / "cache",
    )

    llm1 = MagicMock()
    llm1.complete_structured.return_value = _fake_extraction()
    run_pipeline(MANUSCRIPT_ID, llm_client=llm1, cache=cache)

    llm2 = MagicMock()
    llm2.complete_structured.return_value = _fake_extraction()
    run_pipeline(MANUSCRIPT_ID, llm_client=llm2, cache=cache, force=True)

    assert llm2.complete_structured.call_count >= 1, "--force debe re-llamar al LLM"
