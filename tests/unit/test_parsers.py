"""Tests unitarios de parsers (T012, US1)."""

from __future__ import annotations

import pytest

from backend.core.errors import InvalidFileError
from backend.ingest.parsers.base import is_separator_line
from backend.ingest.parsers.docx_parser import DocxParser
from backend.ingest.parsers.epub_parser import EpubParser
from backend.ingest.parsers.txt_parser import TxtParser, strip_gutenberg

pytestmark = pytest.mark.unit


def test_strip_gutenberg_removes_boilerplate():
    text = (
        "header license\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK 1 ***\n"
        "NARRATIVA\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK 1 ***\n"
        "trailing license"
    )
    out = strip_gutenberg(text)
    assert "NARRATIVA" in out
    assert "license" not in out


@pytest.mark.parametrize(
    "line,expected",
    [
        ("* * *", True),
        ("***", True),
        ("~ ~ ~", True),
        ("·  ·  ·", True),
        ("", False),
        ("   ", False),
        ("Capítulo 1", False),
        ("Una frase normal.", False),
    ],
)
def test_is_separator_line(line, expected):
    assert is_separator_line(line) is expected


def test_txt_parser_detects_headings_and_separators(fixtures_dir):
    doc = TxtParser().parse(fixtures_dir / "crafted-three-chapters.txt")
    headings = [b for b in doc.blocks if b.kind == "heading"]
    separators = [b for b in doc.blocks if b.kind == "separator"]
    assert len(headings) == 4  # prólogo + 3 capítulos
    assert len(separators) == 2  # los dos '* * *' del capítulo 2


def test_txt_parser_preserves_accents(fixtures_dir):
    doc = TxtParser().parse(fixtures_dir / "crafted-three-chapters.txt")
    joined = " ".join(b.text for b in doc.blocks)
    assert "acentós" not in joined  # (no existe en el fixture)
    assert "húmeda" in joined or "Prólogo" in joined or "PRÓLOGO" in joined


def test_txt_parser_rejects_empty(tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_bytes(b"   \n  ")
    with pytest.raises(InvalidFileError):
        TxtParser().parse(empty)


def test_epub_parser_reads_spine_in_order(fixtures_dir):
    doc = EpubParser().parse(fixtures_dir / "crafted-two-chapters.epub")
    headings = [b.text for b in doc.blocks if b.kind == "heading"]
    assert headings == ["Capítulo 1", "Capítulo 2"]
    assert any(b.kind == "separator" for b in doc.blocks)
    assert doc.title == "Crafted Two Chapters"


def test_docx_parser_uses_styles_and_separators(fixtures_dir):
    doc = DocxParser().parse(fixtures_dir / "crafted-two-chapters.docx")
    headings = [b.text for b in doc.blocks if b.kind == "heading"]
    assert headings == ["Capítulo 1", "Capítulo 2"]
    assert any(b.kind == "separator" for b in doc.blocks)
