"""Tests unitarios de parsers (T012, US1)."""

from __future__ import annotations

import pytest
from ebooklib import epub

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


def test_epub_parser_tags_guide_paratext_with_source_role(tmp_path):
    book = epub.EpubBook()
    book.set_identifier("id-test")
    book.set_title("Libro de prueba")
    book.set_language("es")

    cover = epub.EpubHtml(title="Cover", file_name="cover.xhtml", lang="es")
    cover.content = "<html><body><h1>Libro de prueba</h1><p>J. K. Rowling</p></body></html>"
    chap = epub.EpubHtml(title="Cap 1", file_name="chap1.xhtml", lang="es")
    chap.content = "<html><body><h1>Capítulo 1</h1><p>Elena abrió la puerta.</p></body></html>"

    # Create NCX (table of contents)
    c1 = epub.EpubNcx()

    book.add_item(cover)
    book.add_item(chap)
    book.add_item(c1)
    book.spine = [cover, chap]
    book.toc = (chap,)
    book.guide = [{"type": "cover", "href": "cover.xhtml", "title": "Cover"}]

    path = tmp_path / "with-guide.epub"
    epub.write_epub(str(path), book)

    doc = EpubParser().parse(path)
    cover_blocks = [b for b in doc.blocks if b.text in ("Libro de prueba", "J. K. Rowling")]
    chap_blocks = [b for b in doc.blocks if b.text in ("Capítulo 1", "Elena abrió la puerta.")]

    assert cover_blocks and all(b.source_role == "cover" for b in cover_blocks)
    assert chap_blocks and all(b.source_role is None for b in chap_blocks)
