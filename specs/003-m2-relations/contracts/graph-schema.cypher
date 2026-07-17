// specs/003-m2-relations/contracts/graph-schema.cypher
// Graph Schema Contract — M2 Relaciones (Neo4j 5.x)
// Feature: 003-m2-relations
//
// DELTA sobre M0+M1. M2 no modifica nodos previos; solo añade. Idempotente.

// ── Constraints ───────────────────────────────────────────────────────────────

CREATE CONSTRAINT relation_evidence_id_unique IF NOT EXISTS
FOR (re:RelationEvidence) REQUIRE re.evidence_id IS UNIQUE;

// ── Índices ───────────────────────────────────────────────────────────────────

CREATE INDEX relation_evidence_by_manuscript IF NOT EXISTS
FOR (re:RelationEvidence) ON (re.manuscript_id);

CREATE INDEX relation_evidence_by_scene IF NOT EXISTS
FOR (re:RelationEvidence) ON (re.scene_id);

// ── Modelo (propiedades — ver data-model.md) ──────────────────────────────────
//
// (:RelationEvidence { evidence_id, manuscript_id, scene_id,
//                      character_a_id, character_b_id,
//                      rel_type, descriptor, role_a, role_b,
//                      provenance, confidence, quote })
//
// ── Relaciones ────────────────────────────────────────────────────────────────
//
// (a:Character)-[:RELATES_TO { rel_type, descriptor, role_a, role_b,
//                              provenance, confidence, evidence_count,
//                              first_evidence_id }]->(b:Character)
//   · una por par, dirección canónica = orden lexicográfico de character_id
//   · derivada de las evidencias: se borra y reescribe en cada agregación
// (re:RelationEvidence)-[:ABOUT]->(:Character)      // exactamente 2
// (re:RelationEvidence)-[:IN_SCENE]->(:Scene)
// (Manuscript)-[:HAS_RELATION_EVIDENCE]->(re)
