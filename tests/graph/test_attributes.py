"""Integración: esquema del grafo para M3 (Attribute + AttributeEvidence)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_schema_applies_idempotently(neo4j_session):
    from backend.graph import schema

    schema.apply_schema(neo4j_session)
    schema.apply_schema(neo4j_session)  # segunda vez: sin error
    names = {r["name"] for r in neo4j_session.run("SHOW CONSTRAINTS YIELD name")}
    assert "attribute_id_unique" in names
    assert "attribute_evidence_id_unique" in names
