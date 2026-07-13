"""Rendimiento de ingestión (SC-006) — T038.

Mide el parseo + segmentación de una novela real. SC-006 exige < 5 min para 150k
palabras; sin LLM y sin DB el parseo debe ser de segundos. Usamos un margen amplio.
"""

from __future__ import annotations

import time

import pytest

from backend.ingest.pipeline import parse_manuscript

pytestmark = pytest.mark.eval

MAX_SECONDS = 60.0  # margen muy amplio sobre el objetivo real de segundos


def test_full_novel_parses_within_budget(fixtures_dir):
    source = fixtures_dir / "pride-and-prejudice.txt"
    start = time.perf_counter()
    m = parse_manuscript(source, "txt")
    elapsed = time.perf_counter() - start
    assert m.chapter_count == 61
    assert elapsed < MAX_SECONDS, f"parseo tardó {elapsed:.1f}s (> {MAX_SECONDS}s)"
