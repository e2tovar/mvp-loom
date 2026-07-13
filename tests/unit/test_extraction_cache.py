"""Tests unitarios de la cache de extracción (T034)."""

from __future__ import annotations

import pytest

from backend.extraction.schemas import (
    CharacterCandidateOut,
    MentionOut,
    SceneContext,
    SceneExtraction,
)
from backend.llm.cache import ExtractionCache


def _ctx(text: str = "Hello world.", scene_id: str = "ms:c0:s0") -> SceneContext:
    return SceneContext(
        scene_id=scene_id,
        chapter_title=None,
        scene_text=text,
        known_entities=[],
    )


def _extraction() -> SceneExtraction:
    return SceneExtraction(
        mentions=[
            MentionOut(surface="Ana", kind="name", links_to=None, quote="Ana walked in.")
        ],
        new_characters=[
            CharacterCandidateOut(
                canonical_name="Ana", aliases=[], role="protagonist", is_present_in_scene=True
            )
        ],
    )


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / "cache"


@pytest.fixture
def cache(cache_dir):
    return ExtractionCache(
        prompt_version=1, schema_version=1, model="test-model", cache_dir=cache_dir
    )


# ── Clave estable ─────────────────────────────────────────────────────────────


def test_key_stable_for_same_input(cache):
    ctx = _ctx()
    k1 = cache._key(ctx)
    k2 = cache._key(ctx)
    assert k1 == k2


def test_different_texts_different_keys(cache):
    assert cache._key(_ctx("Hello.")) != cache._key(_ctx("World."))


# ── Invalidación ──────────────────────────────────────────────────────────────


def test_invalidation_on_prompt_version(cache_dir):
    ctx = _ctx()
    c1 = ExtractionCache(prompt_version=1, schema_version=1, model="m", cache_dir=cache_dir)
    c2 = ExtractionCache(prompt_version=2, schema_version=1, model="m", cache_dir=cache_dir)
    assert c1._key(ctx) != c2._key(ctx)


def test_invalidation_on_schema_version(cache_dir):
    ctx = _ctx()
    c1 = ExtractionCache(prompt_version=1, schema_version=1, model="m", cache_dir=cache_dir)
    c2 = ExtractionCache(prompt_version=1, schema_version=2, model="m", cache_dir=cache_dir)
    assert c1._key(ctx) != c2._key(ctx)


def test_invalidation_on_model(cache_dir):
    ctx = _ctx()
    c1 = ExtractionCache(prompt_version=1, schema_version=1, model="model-a", cache_dir=cache_dir)
    c2 = ExtractionCache(prompt_version=1, schema_version=1, model="model-b", cache_dir=cache_dir)
    assert c1._key(ctx) != c2._key(ctx)


# ── Round-trip ────────────────────────────────────────────────────────────────


def test_round_trip(cache):
    ctx = _ctx()
    ext = _extraction()
    assert cache.get(ctx) is None
    cache.set(ctx, ext)
    result = cache.get(ctx)
    assert result is not None
    assert result.mentions[0].surface == "Ana"
    assert result.new_characters[0].canonical_name == "Ana"


def test_miss_returns_none(cache):
    assert cache.get(_ctx("Not in cache.")) is None


def test_invalid_cache_file_returns_none(cache, cache_dir):
    """Un archivo de cache corrupto devuelve None sin explotar."""
    ctx = _ctx()
    path = cache._path(cache._key(ctx))
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text("{ invalid json }", encoding="utf-8")
    assert cache.get(ctx) is None
