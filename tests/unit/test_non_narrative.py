"""Clasificación de bloques no narrativos por rol estructural o heurística de texto."""

from __future__ import annotations

from backend.ingest.non_narrative import classify
from backend.ingest.parsers.base import Block


def test_classify_uses_source_role_over_text():
    drafts = classify([Block(kind="heading", text="Cualquier cosa", source_role="cover")])
    assert len(drafts) == 1
    assert drafts[0].kind == "cover"
    assert drafts[0].detected_by == "source_role"


def test_classify_maps_index_role_to_backmatter():
    drafts = classify([Block(kind="paragraph", text="…", source_role="index")])
    assert drafts[0].kind == "backmatter"


def test_classify_falls_back_to_text_detection():
    drafts = classify([Block(kind="paragraph", text="Copyright 2020 Acme")])
    assert drafts[0].kind == "license"
    assert drafts[0].detected_by == "copyright_keyword"
