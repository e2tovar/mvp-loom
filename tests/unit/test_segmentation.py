"""Tests unitarios de segmentación de capítulos y escenas (T013, US1)."""

from __future__ import annotations

import pytest

from backend.ingest.parsers.base import Block
from backend.ingest.segmentation.chapters import segment_chapters
from backend.ingest.segmentation.scenes import segment_scenes

pytestmark = pytest.mark.unit


def _p(text: str) -> Block:
    return Block(kind="paragraph", text=text)


def _h(text: str) -> Block:
    return Block(kind="heading", text=text, level=1)


def _sep() -> Block:
    return Block(kind="separator", text="* * *")


# ── Nivel 0 ───────────────────────────────────────────────────────────────────


def test_chapter_start_is_single_scene_without_separators():
    scenes = segment_scenes([_p("uno"), _p("dos")])
    assert len(scenes) == 1
    assert scenes[0].boundary_reason == "chapter_start"
    assert scenes[0].text == "uno\n\ndos"


def test_no_headings_means_single_chapter():
    chapters, frontmatter = segment_chapters([_p("solo texto"), _p("más texto")])
    assert len(chapters) == 1
    assert frontmatter == []
    assert chapters[0].title is None


# ── Nivel 1 ───────────────────────────────────────────────────────────────────


def test_separator_splits_into_scenes():
    scenes = segment_scenes([_p("escena 1"), _sep(), _p("escena 2"), _sep(), _p("escena 3")])
    assert len(scenes) == 3
    assert scenes[0].boundary_reason == "chapter_start"
    assert scenes[1].boundary_reason == "separator"
    assert scenes[2].boundary_reason == "separator"


def test_blank_paragraphs_are_not_separators():
    # Párrafos vacíos no deben crear cortes (FR-004a).
    scenes = segment_scenes([_p("a"), _p("   "), _p("b")])
    assert len(scenes) == 1
    assert scenes[0].text == "a\n\nb"


# ── Capítulos ──────────────────────────────────────────────────────────────────


def test_segment_chapters_groups_by_heading_and_frontmatter():
    blocks = [
        _p("frontmatter copyright"),
        _h("CAPÍTULO 1"),
        _p("contenido 1"),
        _h("CAPÍTULO 2"),
        _p("contenido 2"),
        _sep(),
        _p("contenido 2b"),
    ]
    chapters, frontmatter = segment_chapters(blocks)
    assert len(chapters) == 2
    assert len(frontmatter) == 1
    assert chapters[0].title == "CAPÍTULO 1"
    assert chapters[1].kind == "chapter"
    # El capítulo 2 conserva su separador para la segmentación de escenas.
    assert sum(1 for b in chapters[1].blocks if b.kind == "separator") == 1


def test_special_headings_preserve_kind():
    chapters, _ = segment_chapters([_h("PRÓLOGO"), _p("x"), _h("EPÍLOGO"), _p("y")])
    kinds = [c.kind for c in chapters]
    assert kinds == ["prologue", "epilogue"]
