# Test de integración end-to-end del pipeline de atributos (M3, spec 004).
#
# Cubre el flujo completo con un LLM fake determinista (sin gastar cuota) contra
# Neo4j real: no-colapso (SC-004), procedencia (INV-M3: first_evidence_id →
# escena de menor orden narrativo), idempotencia, y los caminos de error de
# FR-015 (sin capa M1) y FR-016 (una escena falla, el resto continúa).
import pytest

from backend.core.errors import ExtractionError, NotExtractedError

pytestmark = pytest.mark.integration


class _FakeLLM:
    """Devuelve atributos deterministas según el scene_id presente en el prompt."""

    def complete_structured(self, system, user, schema):
        from backend.extraction.attributes.schemas import (
            SceneAttributes, SceneAttributeEvidence,
        )
        if "s0" in user:
            return SceneAttributes(evidences=[SceneAttributeEvidence(
                character_id="test-e2e:ch:ana", key="eye_color", value_norm="green",
                value_quote="ojos verdes", confidence=0.9)])
        if "s1" in user:
            return SceneAttributes(evidences=[SceneAttributeEvidence(
                character_id="test-e2e:ch:ana", key="eye_color", value_norm="blue",
                value_quote="ojos azules", confidence=0.8)])
        return SceneAttributes(evidences=[])


def _seed(sess):
    sess.run("""
        MERGE (m:Manuscript {manuscript_id:'test-e2e'})
        MERGE (ch:Chapter {chapter_id:'test-e2e:c0'}) SET ch.title='Uno'
        MERGE (m)-[:HAS_CHAPTER]->(ch)
        MERGE (s0:Scene {scene_id:'test-e2e:s0'})
            SET s0.text='Ana de ojos verdes.', s0.order_narrative_global=0
        MERGE (s1:Scene {scene_id:'test-e2e:s1'})
            SET s1.text='Ana de ojos azules.', s1.order_narrative_global=1
        MERGE (ch)-[:HAS_SCENE]->(s0)
        MERGE (ch)-[:HAS_SCENE]->(s1)
        MERGE (c:Character {character_id:'test-e2e:ch:ana'})
            SET c.manuscript_id='test-e2e', c.canonical_name='Ana', c.aliases=[],
                c.entity_kind='person'
        MERGE (c)-[:APPEARS_IN]->(s0)
        MERGE (c)-[:APPEARS_IN]->(s1)
    """).consume()  # fuerza el flush del seed antes de que el pipeline lea en otra sesión


def test_e2e_no_collapse_and_provenance(neo4j_session):
    from backend.graph import schema, attributes as attr_graph
    from backend.extraction.attributes.pipeline import run_attributes_pipeline
    schema.apply_schema(neo4j_session)
    _seed(neo4j_session)

    result = run_attributes_pipeline("test-e2e", llm_client=_FakeLLM(), cache=None)
    assert result.evidences_written == 2
    assert result.attributes_written == 2         # SC-004: dos valores, no uno

    listed = attr_graph.get_attributes_list(neo4j_session, "test-e2e")
    eye = sorted(a["value_norm"] for a in listed if a["key"] == "eye_color")
    assert eye == ["blue", "green"]

    # INV-M3: primera evidencia = escena de orden 0 (verde)
    green = next(a for a in listed if a["value_norm"] == "green")
    assert green["first_evidence_id"].startswith("test-e2e:s0:ae:")

    # INV-M3 determinismo: segunda corrida (idempotente) → mismo grafo
    run_attributes_pipeline("test-e2e", llm_client=_FakeLLM(), cache=None)
    listed2 = attr_graph.get_attributes_list(neo4j_session, "test-e2e")
    assert len(listed2) == 2


def _seed_no_m1(sess):
    """Manuscrito con capa M0 (Chapter+Scene) pero SIN Character (sin M1)."""
    sess.run("""
        MERGE (m:Manuscript {manuscript_id:'test-e2e-nom1'})
        MERGE (ch:Chapter {chapter_id:'test-e2e-nom1:c0'}) SET ch.title='Uno'
        MERGE (m)-[:HAS_CHAPTER]->(ch)
        MERGE (s0:Scene {scene_id:'test-e2e-nom1:s0'})
            SET s0.text='Escena sin personajes extraídos.', s0.order_narrative_global=0
        MERGE (ch)-[:HAS_SCENE]->(s0)
    """).consume()  # forzar el commit antes de que el pipeline lea desde otra sesión


def test_pipeline_raises_without_m1(neo4j_session):
    """FR-015: sin capa M1 (personajes) el pipeline debe fallar explícito, no en silencio."""
    from backend.graph import schema
    from backend.extraction.attributes.pipeline import run_attributes_pipeline
    schema.apply_schema(neo4j_session)
    _seed_no_m1(neo4j_session)

    with pytest.raises(NotExtractedError):
        run_attributes_pipeline("test-e2e-nom1", llm_client=_FakeLLM(), cache=None)


class _FakeLLMFailsOnS0:
    """s0 revienta con ExtractionError (tras "reintentos" simulados); s1 responde ok."""

    def complete_structured(self, system, user, schema):
        from backend.extraction.attributes.schemas import (
            SceneAttributes, SceneAttributeEvidence,
        )
        if "s0" in user:
            raise ExtractionError("fallo simulado del LLM en s0")
        if "s1" in user:
            return SceneAttributes(evidences=[SceneAttributeEvidence(
                character_id="test-e2e-fail:ch:ana", key="eye_color",
                value_norm="green", value_quote="ojos verdes", confidence=0.9)])
        return SceneAttributes(evidences=[])


def _seed_fail(sess):
    """Manuscrito con dos escenas y un personaje que aparece en ambas."""
    sess.run("""
        MERGE (m:Manuscript {manuscript_id:'test-e2e-fail'})
        MERGE (ch:Chapter {chapter_id:'test-e2e-fail:c0'}) SET ch.title='Uno'
        MERGE (m)-[:HAS_CHAPTER]->(ch)
        MERGE (s0:Scene {scene_id:'test-e2e-fail:s0'})
            SET s0.text='Escena que falla.', s0.order_narrative_global=0
        MERGE (s1:Scene {scene_id:'test-e2e-fail:s1'})
            SET s1.text='Ana de ojos verdes.', s1.order_narrative_global=1
        MERGE (ch)-[:HAS_SCENE]->(s0)
        MERGE (ch)-[:HAS_SCENE]->(s1)
        MERGE (c:Character {character_id:'test-e2e-fail:ch:ana'})
            SET c.manuscript_id='test-e2e-fail', c.canonical_name='Ana', c.aliases=[],
                c.entity_kind='person'
        MERGE (c)-[:APPEARS_IN]->(s0)
        MERGE (c)-[:APPEARS_IN]->(s1)
    """).consume()  # forzar el commit antes de que el pipeline lea desde otra sesión


def test_scene_failure_skips_and_continues(neo4j_session):
    """FR-016: una escena que falla se descarta pero no aborta el resto del trabajo."""
    from backend.graph import schema, attributes as attr_graph
    from backend.extraction.attributes.pipeline import run_attributes_pipeline
    schema.apply_schema(neo4j_session)
    _seed_fail(neo4j_session)

    result = run_attributes_pipeline(
        "test-e2e-fail", llm_client=_FakeLLMFailsOnS0(), cache=None
    )
    assert result.scenes_failed == 1
    assert result.scenes_processed == 1

    listed = attr_graph.get_attributes_list(neo4j_session, "test-e2e-fail")
    assert any(a["value_norm"] == "green" and a["key"] == "eye_color" for a in listed)
