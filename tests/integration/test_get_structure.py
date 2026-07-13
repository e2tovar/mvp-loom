"""Contrato e integración de GET /manuscripts/{id}/structure (T030, US2). Requiere Neo4j."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _ingest(api_client, fixtures_dir) -> str:
    data = (fixtures_dir / "crafted-three-chapters.txt").read_bytes()
    resp = api_client.post(
        "/manuscripts",
        files={"file": ("crafted-three-chapters.txt", data, "text/plain")},
    )
    assert resp.status_code == 201
    return resp.json()["manuscript_id"]


def test_structure_returns_hierarchy_and_snippets(neo4j_session, api_client, fixtures_dir):
    mid = _ingest(api_client, fixtures_dir)
    resp = api_client.get(f"/manuscripts/{mid}/structure")
    assert resp.status_code == 200
    body = resp.json()

    assert body["manuscript_id"] == mid
    assert body["chapter_count"] == 4
    assert body["scene_count"] == 6
    assert len(body["chapters"]) == 4

    first_chapter = body["chapters"][0]
    assert first_chapter["order_narrative"] == 0
    assert first_chapter["scene_count"] >= 1
    assert "snippet" in first_chapter["scenes"][0]

    # El capítulo 2 (orden 2) tiene 3 escenas por sus 2 separadores.
    chapter_two = next(c for c in body["chapters"] if c["order_narrative"] == 2)
    assert chapter_two["scene_count"] == 3

    assert len(body["non_narrative_blocks"]) >= 1


def test_structure_can_omit_snippets(neo4j_session, api_client, fixtures_dir):
    mid = _ingest(api_client, fixtures_dir)
    resp = api_client.get(f"/manuscripts/{mid}/structure", params={"include_snippets": False})
    assert resp.status_code == 200
    assert "snippet" not in resp.json()["chapters"][0]["scenes"][0]


def test_structure_unknown_manuscript_returns_404(neo4j_session, api_client):
    resp = api_client.get("/manuscripts/does-not-exist/structure")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"
