"""Partición de paratexto inequívoco antes de la segmentación de capítulos."""

from __future__ import annotations

from backend.ingest.parsers.base import Block
from backend.ingest.segmentation.paratext import partition_paratext


def _blk(kind: str, text: str, role: str | None = None) -> Block:
    return Block(kind=kind, text=text, source_role=role)


def test_paratext_role_goes_to_paratext_even_with_heading():
    blocks = [
        _blk("heading", "Título del libro", role="cover"),
        _blk("paragraph", "J. K. Rowling", role="cover"),
        _blk("heading", "Capítulo 1"),
        _blk("paragraph", "Elena abrió la puerta."),
    ]
    narrative, paratext = partition_paratext(blocks)
    assert [b.text for b in paratext] == ["Título del libro", "J. K. Rowling"]
    assert [b.text for b in narrative] == ["Capítulo 1", "Elena abrió la puerta."]


def test_prologue_role_stays_narrative():
    """Prólogo/prefacio son ambiguos: no se apartan estructuralmente."""
    blocks = [
        _blk("heading", "Prólogo", role="preface"),
        _blk("paragraph", "Aquella noche todo cambió."),
    ]
    narrative, paratext = partition_paratext(blocks)
    assert paratext == []
    assert len(narrative) == 2


def test_no_role_all_narrative():
    blocks = [_blk("heading", "Capítulo 1"), _blk("paragraph", "Texto.")]
    narrative, paratext = partition_paratext(blocks)
    assert paratext == []
    assert len(narrative) == 2
