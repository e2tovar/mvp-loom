// Graph Schema Contract — M3 Atributos (Neo4j 5.x)
// Feature: 004-m3-attributes
//
// DELTA sobre M0+M1+M2. M3 no modifica nodos previos; solo añade. Idempotente.

// ── Constraints ───────────────────────────────────────────────────────────────
CREATE CONSTRAINT attribute_id_unique IF NOT EXISTS
FOR (a:Attribute) REQUIRE a.attribute_id IS UNIQUE;

CREATE CONSTRAINT attribute_evidence_id_unique IF NOT EXISTS
FOR (ae:AttributeEvidence) REQUIRE ae.evidence_id IS UNIQUE;

// ── Índices ───────────────────────────────────────────────────────────────────
CREATE INDEX attribute_by_manuscript IF NOT EXISTS
FOR (a:Attribute) ON (a.manuscript_id);

CREATE INDEX attribute_evidence_by_manuscript IF NOT EXISTS
FOR (ae:AttributeEvidence) ON (ae.manuscript_id);

CREATE INDEX attribute_evidence_by_scene IF NOT EXISTS
FOR (ae:AttributeEvidence) ON (ae.scene_id);

// ── Modelo (propiedades — ver data-model.md) ──────────────────────────────────
//
// (:AttributeEvidence { evidence_id, manuscript_id, scene_id,
//                       character_id, key, value_norm, value_quote, confidence })
// (:Attribute { attribute_id, manuscript_id, character_id, key, value_norm,
//               attr_class, confidence, evidence_count, first_evidence_id })
//
// ── Relaciones ────────────────────────────────────────────────────────────────
//
// (c:Character)-[:HAS_ATTRIBUTE]->(a:Attribute)
//   · un nodo Attribute por (character_id, key, value_norm) — NO se colapsa
//   · derivado de las evidencias: se borra y reescribe en cada agregación
// (ae:AttributeEvidence)-[:ABOUT]->(:Character)     // exactamente 1
// (ae:AttributeEvidence)-[:IN_SCENE]->(:Scene)
// (Manuscript)-[:HAS_ATTRIBUTE_EVIDENCE]->(ae)
