"""Identidad por hash de contenido (Principio VI, research.md D6).

El `manuscript_id` deriva del **contenido narrativo normalizado**, no de los bytes
crudos del archivo: dos exports del mismo libro con distinto nombre o empaquetado
producen el mismo id (US3, escenario 2; FR-009).
"""

from __future__ import annotations

import hashlib
import re

_WS_RUN = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n{3,}")


def normalize_narrative(text: str) -> str:
    """Normaliza el texto narrativo para que el hash sea estable e idempotente.

    - Unifica saltos de línea (CRLF/CR -> LF).
    - Colapsa runs de espacios/tabs a un único espacio.
    - Recorta espacios al final de cada línea.
    - Colapsa 3+ saltos de línea consecutivos a 2.
    - Recorta el documento completo.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_WS_RUN.sub(" ", line).rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = _BLANKS.sub("\n\n", text)
    return text.strip()


def content_id(normalized_narrative: str) -> str:
    """Devuelve el SHA-256 hex del contenido narrativo ya normalizado."""
    return hashlib.sha256(normalized_narrative.encode("utf-8")).hexdigest()
