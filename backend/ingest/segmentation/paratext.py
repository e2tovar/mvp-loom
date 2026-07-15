"""Partición de paratexto inequívoco (portada, índice, créditos…) antes de segmentar.

Solo actúa sobre bloques cuyo formato de origen declaró un rol no narrativo explícito
(hoy: epub vía `guide`). Prólogo/prefacio/introducción son ambiguos y NO se apartan
aquí: pueden ser narrativa y los decide el LLM de extracción por su contenido.
"""

from __future__ import annotations

from backend.ingest.parsers.base import Block

# Roles del `guide` de EPUB inequívocamente no narrativos. Se excluye deliberadamente
# "text", "foreword", "preface", "epigraph": los tres últimos pueden ser narrativa.
_PARATEXT_ROLES = frozenset(
    {
        "cover", "title-page", "titlepage", "copyright-page", "copyright",
        "toc", "loi", "lot", "index", "bibliography", "glossary",
        "dedication", "acknowledgements", "colophon", "notes",
    }
)


def partition_paratext(blocks: list[Block]) -> tuple[list[Block], list[Block]]:
    """Separa (narrativa, paratexto) según el `source_role` declarado por el formato."""
    narrative: list[Block] = []
    paratext: list[Block] = []
    for block in blocks:
        role = (block.source_role or "").lower()
        if role in _PARATEXT_ROLES:
            paratext.append(block)
        else:
            narrative.append(block)
    return narrative, paratext
