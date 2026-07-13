"""Integración pipeline -> grafo (T015, US1). Requiere Neo4j."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_ingest_writes_raw_layer_to_graph(neo4j_session, api_client, fixtures_dir):
    data = (fixtures_dir / "crafted-three-chapters.txt").read_bytes()
    resp = api_client.post(
        "/manuscripts",
        files={"file": ("crafted-three-chapters.txt", data, "text/plain")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] is True
    assert body["chapter_count"] == 4
    assert body["scene_count"] == 6
    assert body["non_narrative_block_count"] >= 1
    mid = body["manuscript_id"]

    chapters = neo4j_session.run(
        "MATCH (:Manuscript {manuscript_id:$id})-[:HAS_CHAPTER]->(c) RETURN count(c) AS n",
        id=mid,
    ).single()["n"]
    assert chapters == 4

    scenes = neo4j_session.run(
        "MATCH (:Manuscript {manuscript_id:$id})-[:HAS_CHAPTER]->()-[:HAS_SCENE]->(s) "
        "RETURN count(s) AS n",
        id=mid,
    ).single()["n"]
    assert scenes == 6

    next_scene = neo4j_session.run(
        "MATCH (a:Scene {manuscript_id:$id})-[:NEXT_SCENE]->(:Scene) RETURN count(*) AS n",
        id=mid,
    ).single()["n"]
    assert next_scene == 5  # N escenas -> N-1 relaciones de orden

    # El orden narrativo global es una secuencia 0..N-1 sin huecos.
    orders = [
        r["o"]
        for r in neo4j_session.run(
            "MATCH (s:Scene {manuscript_id:$id}) RETURN s.order_narrative_global AS o "
            "ORDER BY o",
            id=mid,
        )
    ]
    assert orders == list(range(6))
