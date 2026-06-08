"""Detección de capítulos (FR-002, FR-012, research.md D5 Nivel 0).

Agrupa los bloques en capítulos a partir de los bloques `heading`. El contenido previo
al primer encabezado se devuelve aparte como frontmatter (no-narrativo).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.ingest.models import ChapterKind
from backend.ingest.parsers.base import SPECIAL_HEADING_RE, Block

_TRIM_TRAILING = re.compile(r"[.\]\)\s]+$")


@dataclass
class ChapterDraft:
    title: str | None
    kind: ChapterKind
    blocks: list[Block] = field(default_factory=list)


def _kind_from_heading(text: str) -> ChapterKind:
    if SPECIAL_HEADING_RE.match(text):
        low = text.lower()
        if low.startswith(("pról", "prol", "prologue")) or "prol" in low:
            return "prologue"
        if "epíl" in low or "epil" in low:
            return "epilogue"
        if "interl" in low:
            return "interlude"
        return "other"
    return "chapter"


def _clean_title(text: str) -> str:
    return _TRIM_TRAILING.sub("", text.strip()).strip() or text.strip()


def segment_chapters(blocks: list[Block]) -> tuple[list[ChapterDraft], list[Block]]:
    """Devuelve (capítulos, frontmatter_blocks).

    Si no hay encabezados, todo el contenido narrativo es un único capítulo.
    """
    heading_indices = [i for i, b in enumerate(blocks) if b.kind == "heading"]

    if not heading_indices:
        body = [b for b in blocks if b.kind != "heading"]
        if not body:
            return [], []
        return [ChapterDraft(title=None, kind="chapter", blocks=body)], []

    first = heading_indices[0]
    frontmatter = [b for b in blocks[:first] if b.kind != "heading"]

    chapters: list[ChapterDraft] = []
    for pos, idx in enumerate(heading_indices):
        heading = blocks[idx]
        end = heading_indices[pos + 1] if pos + 1 < len(heading_indices) else len(blocks)
        body = [b for b in blocks[idx + 1 : end] if b.kind != "heading"]
        chapters.append(
            ChapterDraft(
                title=_clean_title(heading.text),
                kind=_kind_from_heading(heading.text),
                blocks=body,
            )
        )
    return chapters, frontmatter
