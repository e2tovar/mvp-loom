"""Parser EPUB: recorre el spine en orden de lectura y extrae texto del XHTML.

research.md D2. Usa ebooklib para el contenedor y BeautifulSoup para el contenido.
"""

from __future__ import annotations

from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from backend.core.errors import InvalidFileError
from backend.ingest.parsers.base import Block, ParsedDocument, is_separator_line

_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_BLOCK_TAGS = [*_HEADING_TAGS.keys(), "p", "hr"]


def _title(book: epub.EpubBook) -> str | None:
    meta = book.get_metadata("DC", "title")
    if meta and meta[0] and meta[0][0]:
        return str(meta[0][0]).strip()
    return None


class EpubParser:
    def parse(self, path: Path) -> ParsedDocument:
        try:
            book = epub.read_epub(str(path))
        except Exception as exc:  # noqa: BLE001
            raise InvalidFileError(f"No se pudo leer el EPUB: {exc}") from exc

        blocks: list[Block] = []
        guide_roles = {
            str(g.get("href", "")).split("#")[0]: str(g.get("type", "")).strip()
            for g in getattr(book, "guide", []) or []
            if g.get("href")
        }
        for idref, _linear in book.spine:
            item = book.get_item_with_id(idref)
            if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue
            role = guide_roles.get(item.get_name()) or None
            soup = BeautifulSoup(item.get_content(), "lxml")
            for el in soup.find_all(_BLOCK_TAGS):
                if el.name == "hr":
                    blocks.append(Block(kind="separator", text="***", source_role=role))
                    continue
                text = el.get_text(" ", strip=True)
                if not text:
                    continue
                if el.name in _HEADING_TAGS:
                    blocks.append(
                        Block(kind="heading", text=text, level=_HEADING_TAGS[el.name], source_role=role)
                    )
                elif is_separator_line(text):
                    blocks.append(Block(kind="separator", text=text, source_role=role))
                else:
                    blocks.append(Block(kind="paragraph", text=text, source_role=role))

        if not blocks:
            raise InvalidFileError("El EPUB no contiene texto extraíble.")
        return ParsedDocument(source_format="epub", blocks=blocks, title=_title(book))
