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


def _seed_min_graph(sess):
    sess.run("""
        MERGE (m:Manuscript {manuscript_id:'test-attr'})
        MERGE (s0:Scene {scene_id:'test-attr:s0'}) SET s0.order_narrative_global=0
        MERGE (s5:Scene {scene_id:'test-attr:s5'}) SET s5.order_narrative_global=5
        MERGE (c:Character {character_id:'test-attr:ch:ana'})
            SET c.manuscript_id='test-attr', c.canonical_name='Ana', c.aliases=[]
    """)


def test_upsert_evidence_and_replace_attributes_roundtrip(neo4j_session):
    from backend.graph import attributes as attr_graph
    _seed_min_graph(neo4j_session)
    e0 = attr_graph.upsert_attribute_evidence(neo4j_session, "test-attr", "test-attr:s0",
        {"character_id":"test-attr:ch:ana","key":"eye_color","value_norm":"blue",
         "value_quote":"ojos azules","confidence":0.9})
    attr_graph.upsert_attribute_evidence(neo4j_session, "test-attr", "test-attr:s5",
        {"character_id":"test-attr:ch:ana","key":"eye_color","value_norm":"green",
         "value_quote":"ojos verdes","confidence":0.8})

    evs = attr_graph.get_attribute_evidences(neo4j_session, "test-attr")
    assert len(evs) == 2
    assert all("narrative_order" in e for e in evs)

    from backend.extraction.attributes.aggregation import aggregate_character_attributes
    nodes = aggregate_character_attributes(evs)
    attr_graph.replace_attributes(neo4j_session, "test-attr", nodes)

    listed = attr_graph.get_attributes_list(neo4j_session, "test-attr")
    eye = sorted(a["value_norm"] for a in listed if a["key"] == "eye_color")
    assert eye == ["blue", "green"]          # SC-004: no colapso
    assert attr_graph.has_attributes(neo4j_session, "test-attr") is True
    assert isinstance(e0, str)


def test_replace_attributes_is_idempotent(neo4j_session):
    from backend.graph import attributes as attr_graph
    _seed_min_graph(neo4j_session)
    attr_graph.upsert_attribute_evidence(neo4j_session, "test-attr", "test-attr:s0",
        {"character_id":"test-attr:ch:ana","key":"hair","value_norm":"blonde",
         "value_quote":"pelo rubio","confidence":0.7})
    from backend.extraction.attributes.aggregation import aggregate_character_attributes
    evs = attr_graph.get_attribute_evidences(neo4j_session, "test-attr")
    nodes = aggregate_character_attributes(evs)
    attr_graph.replace_attributes(neo4j_session, "test-attr", nodes)
    attr_graph.replace_attributes(neo4j_session, "test-attr", nodes)  # 2ª vez
    listed = attr_graph.get_attributes_list(neo4j_session, "test-attr")
    assert len([a for a in listed if a["key"] == "hair"]) == 1


def test_replace_attributes_removes_stale_nodes(neo4j_session):
    """Un valor que deja de afirmarse en una re-agregación no deja nodo fantasma."""
    from backend.graph import attributes as attr_graph
    _seed_min_graph(neo4j_session)
    attr_graph.upsert_attribute_evidence(neo4j_session, "test-attr", "test-attr:s0",
        {"character_id":"test-attr:ch:ana","key":"eye_color","value_norm":"blue",
         "value_quote":"ojos azules","confidence":0.9})
    from backend.extraction.attributes.aggregation import aggregate_character_attributes
    evs = attr_graph.get_attribute_evidences(neo4j_session, "test-attr")
    nodes = aggregate_character_attributes(evs)
    attr_graph.replace_attributes(neo4j_session, "test-attr", nodes)

    listed = attr_graph.get_attributes_list(neo4j_session, "test-attr")
    assert len(listed) == 1

    attr_graph.replace_attributes(neo4j_session, "test-attr", [])  # re-agregación vacía

    listed_after = attr_graph.get_attributes_list(neo4j_session, "test-attr")
    assert listed_after == []
