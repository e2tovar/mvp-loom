"""Metadata de tracing por pipeline (ADR-0003): unidad pura, sin BD ni Langfuse."""

from __future__ import annotations

from backend.extraction.attributes.pipeline import _trace_metadata as attributes_trace_metadata
from backend.extraction.pipeline import _trace_metadata as characters_trace_metadata
from backend.extraction.relations.pipeline import _trace_metadata as relations_trace_metadata
from backend.llm.cache import AttributesCache, ExtractionCache, RelationsCache


def test_characters_trace_metadata(tmp_path):
    cache = ExtractionCache(3, 2, "openai/kimi-k2.5", cache_dir=tmp_path)
    meta = characters_trace_metadata("ms-1", llm_client=None, cache=cache, force=False)
    assert meta == {
        "manuscript_id": "ms-1",
        "model": "openai/kimi-k2.5",
        "prompt_version": 3,
        "schema_version": 2,
    }


def test_relations_trace_metadata(tmp_path):
    cache = RelationsCache(1, 1, "test-model", cache_dir=tmp_path)
    meta = relations_trace_metadata("ms-2", llm_client=None, cache=cache, force=True)
    assert meta == {
        "manuscript_id": "ms-2",
        "model": "test-model",
        "prompt_version": 1,
        "schema_version": 1,
    }


def test_attributes_trace_metadata(tmp_path):
    cache = AttributesCache(2, 1, "test-model", cache_dir=tmp_path)
    meta = attributes_trace_metadata("ms-3", llm_client=None, cache=cache, force=False)
    assert meta == {
        "manuscript_id": "ms-3",
        "model": "test-model",
        "prompt_version": 2,
        "schema_version": 1,
    }


def test_trace_metadata_tolerates_missing_cache():
    meta = characters_trace_metadata("ms-4", llm_client=None, cache=None, force=False)
    assert meta == {
        "manuscript_id": "ms-4",
        "model": None,
        "prompt_version": None,
        "schema_version": None,
    }
