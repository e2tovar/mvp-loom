"""RelationsCache: keyed por contenido + cast + versiones (FR-008)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.extraction.relations.schemas import (
    CastEntry,
    RelationSceneContext,
    SceneRelations,
)
from backend.llm.cache import RelationsCache

pytestmark = pytest.mark.unit


def _ctx(text: str = "Elena y Miguel discuten.", cast_ids: tuple[str, ...] = ("a", "b")):
    return RelationSceneContext(
        scene_id="s1",
        chapter_title=None,
        scene_text=text,
        cast=[
            CastEntry(character_id=c, canonical_name=c.upper(), aliases=[])
            for c in cast_ids
        ],
    )


def test_roundtrip(tmp_path: Path) -> None:
    cache = RelationsCache(1, 1, "test-model", cache_dir=tmp_path)
    out = SceneRelations(evidences=[])
    assert cache.get(_ctx()) is None
    cache.set(_ctx(), out)
    got = cache.get(_ctx())
    assert got is not None and got.evidences == []


def test_cast_change_invalidates(tmp_path: Path) -> None:
    cache = RelationsCache(1, 1, "test-model", cache_dir=tmp_path)
    cache.set(_ctx(cast_ids=("a", "b")), SceneRelations(evidences=[]))
    assert cache.get(_ctx(cast_ids=("a", "b", "c"))) is None


def test_cast_order_does_not_matter(tmp_path: Path) -> None:
    cache = RelationsCache(1, 1, "test-model", cache_dir=tmp_path)
    cache.set(_ctx(cast_ids=("b", "a")), SceneRelations(evidences=[]))
    assert cache.get(_ctx(cast_ids=("a", "b"))) is not None


def test_version_change_invalidates(tmp_path: Path) -> None:
    RelationsCache(1, 1, "test-model", cache_dir=tmp_path).set(
        _ctx(), SceneRelations(evidences=[])
    )
    assert RelationsCache(2, 1, "test-model", cache_dir=tmp_path).get(_ctx()) is None
