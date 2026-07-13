"""Re-ingestión determinista e idempotente (T033, T034, US3). Requiere Neo4j."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_reingesting_same_file_is_idempotent(neo4j_session, api_client, fixtures_dir):
    data = (fixtures_dir / "crafted-two-chapters.epub").read_bytes()
    files = {"file": ("crafted-two-chapters.epub", data, "application/epub+zip")}

    r1 = api_client.post("/manuscripts", files=files)
    assert r1.status_code == 201
    assert r1.json()["created"] is True
    mid = r1.json()["manuscript_id"]
    scenes_after_first = r1.json()["scene_count"]

    r2 = api_client.post("/manuscripts", files=files)
    assert r2.status_code == 200
    assert r2.json()["created"] is False
    assert r2.json()["manuscript_id"] == mid

    # Sin duplicados tras re-ingerir.
    chapters = neo4j_session.run(
        "MATCH (:Manuscript {manuscript_id:$id})-[:HAS_CHAPTER]->(c) RETURN count(c) AS n",
        id=mid,
    ).single()["n"]
    scenes = neo4j_session.run(
        "MATCH (s:Scene {manuscript_id:$id}) RETURN count(s) AS n", id=mid
    ).single()["n"]
    assert chapters == 2
    assert scenes == scenes_after_first


def test_same_content_different_name_same_id(neo4j_session, api_client, fixtures_dir):
    data = (fixtures_dir / "crafted-three-chapters.txt").read_bytes()

    r1 = api_client.post("/manuscripts", files={"file": ("alpha.txt", data, "text/plain")})
    r2 = api_client.post("/manuscripts", files={"file": ("beta.txt", data, "text/plain")})

    assert r1.status_code == 201
    assert r2.status_code == 200  # mismo contenido -> idempotente
    assert r1.json()["manuscript_id"] == r2.json()["manuscript_id"]
