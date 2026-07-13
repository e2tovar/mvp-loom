"""Protocolo de parser y modelo de bloque normalizado (research.md D2-D4).

Cada parser convierte un archivo de un formato concreto en una secuencia ordenada de
`Block` (heading / paragraph / separator). La detección de capítulos y escenas opera
sobre esos bloques con independencia del formato de origen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from backend.ingest.models import SourceFormat

BlockKind = Literal["heading", "paragraph", "separator"]

# Encabezado de capítulo: la línea es esencialmente "CHAPTER <roman|num>" (es/en),
# con puntuación o corchetes finales tolerados (p. ej. la leyenda "Chapter I.]").
CHAPTER_HEADING_RE = re.compile(
    r"^\s*(?:CHAPTER|CHAP|CAP[IÍ]TULO)\s+(?:[IVXLCDM]+|\d+)\b[.\]\)\s]*$",
    re.IGNORECASE,
)
# Unidades estructurales no estándar conservadas en orden (FR-012).
SPECIAL_HEADING_RE = re.compile(
    r"^\s*(PROLOGUE|PRÓLOGO|PROLOGO|EPILOGUE|EPÍLOGO|EPILOGO|INTERLUDE|INTERLUDIO)\b[.\s:]*$",
    re.IGNORECASE,
)

# Símbolos que pueden componer un separador de escena tipográfico (Nivel 1).
_SEPARATOR_CHARS = set("*·~—#§•-–—_ \t")


def is_separator_line(text: str) -> bool:
    """True si la línea está compuesta SOLO por símbolos separadores (FR-004a).

    Una línea en blanco (sin símbolos) NO es separador.
    """
    stripped = text.strip()
    if not stripped:
        return False
    if not all(ch in _SEPARATOR_CHARS for ch in stripped):
        return False
    # Debe contener al menos un símbolo no-espacio.
    return any(not ch.isspace() for ch in stripped)


@dataclass
class Block:
    """Unidad estructural cruda emitida por un parser."""

    kind: BlockKind
    text: str
    level: int | None = None
    style: str | None = None


@dataclass
class ParsedDocument:
    """Resultado de parsear un manuscrito: bloques en orden de lectura."""

    source_format: SourceFormat
    blocks: list[Block]
    title: str | None = None


class Parser(Protocol):
    """Contrato de un parser por formato."""

    def parse(self, path: Path) -> ParsedDocument: ...
