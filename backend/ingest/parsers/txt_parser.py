"""Parser de texto plano, con stripping del boilerplate de Project Gutenberg.

research.md D3. Detecta encabezados de capítulo y separadores de escena por línea;
agrupa el resto en párrafos.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.core.errors import InvalidFileError
from backend.ingest.parsers.base import (
    CHAPTER_HEADING_RE,
    SPECIAL_HEADING_RE,
    Block,
    ParsedDocument,
    is_separator_line,
)

_GUTENBERG_START = re.compile(
    r"\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", re.IGNORECASE
)
_GUTENBERG_END = re.compile(
    r"\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG.*?\*\*\*", re.IGNORECASE
)
_PARA_SPLIT = re.compile(r"\n\s*\n")


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise InvalidFileError("No se pudo decodificar el archivo de texto.")


def strip_gutenberg(text: str) -> str:
    """Conserva solo la zona narrativa entre los marcadores START/END de Gutenberg."""
    start = _GUTENBERG_START.search(text)
    if start:
        text = text[start.end():]
    end = _GUTENBERG_END.search(text)
    if end:
        text = text[: end.start()]
    return text


class TxtParser:
    def parse(self, path: Path) -> ParsedDocument:
        data = path.read_bytes()
        if not data.strip():
            raise InvalidFileError("El archivo de texto está vacío.")
        text = _decode(data).replace("\r\n", "\n").replace("\r", "\n")
        text = strip_gutenberg(text)

        blocks: list[Block] = []
        for segment in _PARA_SPLIT.split(text):
            stripped = segment.strip()
            if not stripped:
                continue
            single_line = "\n" not in stripped
            if single_line and is_separator_line(stripped):
                blocks.append(Block(kind="separator", text=stripped))
            elif single_line and CHAPTER_HEADING_RE.match(stripped):
                blocks.append(Block(kind="heading", text=stripped, level=1))
            elif single_line and SPECIAL_HEADING_RE.match(stripped):
                blocks.append(Block(kind="heading", text=stripped, level=1))
            else:
                # Párrafo: colapsa los saltos de línea internos (wrapping) a espacios.
                paragraph = " ".join(line.strip() for line in stripped.split("\n"))
                blocks.append(Block(kind="paragraph", text=paragraph))

        return ParsedDocument(source_format="txt", blocks=blocks, title=None)
