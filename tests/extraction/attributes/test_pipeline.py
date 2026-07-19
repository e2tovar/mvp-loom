import pytest


def test_attributes_cache_roundtrip(tmp_path):
    from backend.extraction.attributes.schemas import (
        AttributeSceneContext, CastEntry, SceneAttributes, SceneAttributeEvidence,
    )
    from backend.llm.cache import AttributesCache

    cache = AttributesCache(prompt_version=1, schema_version=1, model="m",
                            cache_dir=tmp_path)
    ctx = AttributeSceneContext(scene_id="s0", chapter_title=None,
        scene_text="Ana tiene ojos verdes.",
        cast=[CastEntry(character_id="ana", canonical_name="Ana", aliases=[])])
    assert cache.get(ctx) is None
    out = SceneAttributes(evidences=[SceneAttributeEvidence(
        character_id="ana", key="eye_color", value_norm="green",
        value_quote="ojos verdes", confidence=0.9)])
    cache.set(ctx, out)
    again = cache.get(ctx)
    assert again is not None and again.evidences[0].value_norm == "green"
