
from backend.extraction.attributes.schemas import (
    SceneAttributeEvidence,
    SceneAttributes,
)


def test_attributes_cache_roundtrip(tmp_path):
    from backend.extraction.attributes.schemas import (
        AttributeSceneContext,
        CastEntry,
        SceneAttributeEvidence,
        SceneAttributes,
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


def test_validate_drops_out_of_cast_and_dedupes_by_key():
    from backend.extraction.attributes.pipeline import _validate_evidences
    out = SceneAttributes(evidences=[
        SceneAttributeEvidence(character_id="ana", key="eye_color",
            value_norm="blue", value_quote="ojos azules", confidence=0.6),
        SceneAttributeEvidence(character_id="ana", key="eye_color",
            value_norm="green", value_quote="ojos verdes", confidence=0.9),
        SceneAttributeEvidence(character_id="intruso", key="hair",
            value_norm="black", value_quote="pelo negro", confidence=0.9),
    ])
    kept = _validate_evidences(out, {"ana"}, "s0")
    # intruso fuera del cast → descartado; ana/eye_color dedup a mayor confianza
    assert len(kept) == 1
    assert kept[0]["character_id"] == "ana"
    assert kept[0]["value_norm"] == "green"
