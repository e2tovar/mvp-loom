"""Tests de contrato de POST /manuscripts — casos de error (T014, US1).

Estos casos no tocan Neo4j (el pipeline rechaza antes de escribir), por lo que corren
siempre, sin base de datos.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

_GUTENBERG_EMPTY = (
    b"*** START OF THE PROJECT GUTENBERG EBOOK 1 ***\n\n"
    b"*** END OF THE PROJECT GUTENBERG EBOOK 1 ***\n"
)


def test_unsupported_format_returns_415(api_client):
    resp = api_client.post(
        "/manuscripts",
        files={"file": ("libro.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert resp.status_code == 415
    assert resp.json()["error"] == "unsupported_format"


def test_empty_file_returns_400(api_client):
    resp = api_client.post(
        "/manuscripts",
        files={"file": ("vacio.txt", b"", "text/plain")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_file"


def test_no_narrative_content_returns_422(api_client):
    resp = api_client.post(
        "/manuscripts",
        files={"file": ("solo-boilerplate.txt", _GUTENBERG_EMPTY, "text/plain")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "no_narrative_content"
