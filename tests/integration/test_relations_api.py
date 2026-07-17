"""Contrato del endpoint de inspección de relaciones (FR-014)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_relations_404_for_unknown_manuscript(api_client, neo4j_session) -> None:
    resp = api_client.get("/manuscripts/test-nope/relations")
    assert resp.status_code == 404


def test_relations_409_when_not_extracted(api_client, neo4j_session) -> None:
    from backend.graph.raw_layer import write_raw_layer
    from tests.integration.test_relations_flow import build_manuscript

    write_raw_layer(neo4j_session, build_manuscript())
    resp = api_client.get("/manuscripts/test-m2-flow/relations")
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "not_extracted"
