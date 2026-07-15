"""Detección de contenido no-narrativo (FR-007, SC-007, research.md D7).

Opera sobre los bloques que quedan antes del primer capítulo (frontmatter). Marca
licencias/boilerplate de Gutenberg, índices y portadas; nunca los borra: los conserva
como `NonNarrativeBlock` para trazabilidad.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.ingest.models import NonNarrativeKind
from backend.ingest.parsers.base import Block


@dataclass
class NonNarrativeDraft:
    kind: NonNarrativeKind
    text: str
    detected_by: str
    position: str = "before"


def _detect(text: str) -> tuple[NonNarrativeKind, str]:
    low = text.lower()
    if "project gutenberg" in low or "produced by" in low:
        return "license", "gutenberg_marker"
    if "copyright" in low or "all rights reserved" in low:
        return "license", "copyright_keyword"
    if (
        "list of illustrations" in low
        or "table of contents" in low
        or "heading to chapter" in low
        or "tailpiece" in low
        or low.strip() in {"contents", "índice", "indice"}
    ):
        return "toc", "toc_heuristic"
    return "frontmatter", "frontmatter_position"


_ROLE_TO_KIND: dict[str, NonNarrativeKind] = {
    "cover": "cover",
    "title-page": "cover",
    "titlepage": "cover",
    "copyright-page": "license",
    "copyright": "license",
    "toc": "toc",
    "loi": "toc",
    "lot": "toc",
    "dedication": "frontmatter",
    "acknowledgements": "frontmatter",
    "notes": "backmatter",
    "colophon": "backmatter",
    "index": "backmatter",
    "bibliography": "backmatter",
    "glossary": "backmatter",
}


def _kind_from_role(role: str | None) -> NonNarrativeKind | None:
    if not role:
        return None
    return _ROLE_TO_KIND.get(role.lower())


def classify(frontmatter_blocks: list[Block]) -> list[NonNarrativeDraft]:
    """Clasifica el frontmatter y fusiona bloques contiguos del mismo tipo."""
    drafts: list[NonNarrativeDraft] = []
    for block in frontmatter_blocks:
        if block.kind == "separator":
            continue
        role_kind = _kind_from_role(block.source_role)
        if role_kind is not None:
            kind, detected_by = role_kind, "source_role"
        else:
            kind, detected_by = _detect(block.text)
        if drafts and drafts[-1].kind == kind and drafts[-1].detected_by == detected_by:
            drafts[-1].text += "\n\n" + block.text
        else:
            drafts.append(NonNarrativeDraft(kind=kind, text=block.text, detected_by=detected_by))
    return drafts
