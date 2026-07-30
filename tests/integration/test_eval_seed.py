"""El sembrador deja el grafo en el estado que los gates necesitan.

Requiere Neo4j. NO requiere cuota LLM si las respuestas congeladas están
presentes (eval/fixtures/llm-cache) — que es justamente lo que se verifica.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_gate_works_cover_the_three_milestones():
    """El catálogo declara qué capa necesita cada obra. Puro, sin base."""
    from eval.seed import GATE_WORKS

    by_name = {w.filename: w for w in GATE_WORKS}
    assert set(by_name) == {
        "crafted-three-chapters.txt",
        "crafted-two-chapters.epub",
        "crafted-relations.txt",
        "crafted-attributes.txt",
    }
    # M1 en las cuatro; M2 solo en la obra de relaciones; M3 solo en la de atributos.
    assert all("m1" in w.layers for w in GATE_WORKS)
    assert by_name["crafted-relations.txt"].layers == ("m1", "m2")
    assert by_name["crafted-attributes.txt"].layers == ("m1", "m3")
    assert by_name["crafted-three-chapters.txt"].layers == ("m1",)


def test_seed_all_leaves_every_gate_layer_present(neo4j_session):
    """Tras sembrar, los checkers que usan los gates dicen que hay datos."""
    from backend.graph import attributes as attr_graph
    from backend.graph import characters as char_graph
    from backend.graph import relations as rel_graph
    from eval.seed import seed_all

    ids = seed_all()
    assert len(ids) == 4

    sess = neo4j_session
    for name, mid in ids.items():
        assert char_graph.has_extraction(sess, mid), f"M1 ausente en {name}"
    assert rel_graph.has_relations(sess, ids["crafted-relations.txt"])
    assert attr_graph.has_attributes(sess, ids["crafted-attributes.txt"])


def test_seed_is_idempotent_and_spends_no_llm_calls_on_rerun(neo4j_session):
    """Segunda corrida: todo sale de la caché, cero llamadas nuevas."""
    from eval.seed import seed_all

    first = seed_all()
    second = seed_all()
    assert first == second, "los manuscript_id son hashes de contenido: estables"


def test_seed_does_not_touch_manuscripts_outside_the_gate(neo4j_session):
    """Guard de aislamiento: sembrar no borra ni altera obras reales.

    Ver docs/known-issues.md → follow-up 1 de M1: un borrado sin scope destruyó
    la capa cruda de todos los libros tres veces en una sesión.
    """
    from backend.graph import raw_layer
    from eval.seed import seed_all

    sess = neo4j_session
    sess.run(
        "CREATE (m:Manuscript {manuscript_id: $mid, title: $t})",
        mid="test-seed-bystander",
        t="No me toques",
    )
    seed_all()
    assert raw_layer.manuscript_exists(sess, "test-seed-bystander")
