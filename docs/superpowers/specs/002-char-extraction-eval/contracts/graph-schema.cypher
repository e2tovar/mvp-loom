// Graph Schema Contract — M1 Personajes (Neo4j 5.x)
// Feature: 002-char-extraction-eval
//
// DELTA sobre el esquema de M0 (001-m0-ingest-segmentation/contracts/graph-schema.cypher).
// M1 no modifica nodos de la capa cruda; solo añade. Se aplica idempotente (IF NOT EXISTS).

// ── Constraints de unicidad ───────────────────────────────────────────────────

CREATE CONSTRAINT character_id_unique IF NOT EXISTS
FOR (c:Character) REQUIRE c.character_id IS UNIQUE;

CREATE CONSTRAINT mention_id_unique IF NOT EXISTS
FOR (m:Mention) REQUIRE m.mention_id IS UNIQUE;

CREATE CONSTRAINT merge_candidate_id_unique IF NOT EXISTS
FOR (mc:MergeCandidate) REQUIRE mc.candidate_id IS UNIQUE;

// ── Índices de apoyo ──────────────────────────────────────────────────────────

CREATE INDEX character_by_manuscript IF NOT EXISTS
FOR (c:Character) ON (c.manuscript_id);

CREATE INDEX mention_by_scene IF NOT EXISTS
FOR (m:Mention) ON (m.scene_id);

CREATE INDEX merge_candidate_by_status IF NOT EXISTS
FOR (mc:MergeCandidate) ON (mc.status);

// ── Modelo de nodos (propiedades, ver data-model.md) ─────────────────────────
//
// (:Character      { character_id, manuscript_id, canonical_name, aliases,
//                    role, is_mentioned_only, first_scene_id,
//                    appearance_count, mention_count })
// (:Mention        { mention_id, scene_id, manuscript_id, surface, kind,
//                    start_offset, end_offset, quote })
// (:MergeCandidate { candidate_id, manuscript_id, character_a_id, character_b_id,
//                    confidence, rationale, evidence_json, status, resolved_at })

// ── Relaciones ───────────────────────────────────────────────────────────────
//
// (Manuscript)-[:HAS_CHARACTER]->(Character)
// (Character)-[:APPEARS_IN { kind, mention_count, first_mention_id }]->(Scene)
// (Character)-[:HAS_MENTION]->(Mention)
// (Mention)-[:IN_SCENE]->(Scene)
// (MergeCandidate)-[:PROPOSES_MERGE]->(Character)   // exactamente 2 por candidate
// (Manuscript)-[:HAS_MERGE_CANDIDATE]->(MergeCandidate)

// ── Escritura idempotente (patrón) ───────────────────────────────────────────
// Upsert de personaje + mención; ids deterministas → MERGE converge (FR-012):
//
//   MERGE (ch:Character { character_id: $character_id })
//     SET ch += $character_props
//   WITH ch
//   MATCH (m:Manuscript { manuscript_id: $manuscript_id })
//   MERGE (m)-[:HAS_CHARACTER]->(ch);
//
//   MERGE (mn:Mention { mention_id: $mention_id })
//     SET mn += $mention_props
//   WITH mn
//   MATCH (ch:Character { character_id: $character_id })
//   MERGE (ch)-[:HAS_MENTION]->(mn)
//   WITH mn
//   MATCH (s:Scene { scene_id: $scene_id })
//   MERGE (mn)-[:IN_SCENE]->(s);
//
// ── Aplicación de un merge aceptado (humano) ─────────────────────────────────
// Mover menciones/apariciones de B a A, unificar aliases, eliminar B, marcar decisión:
//
//   MATCH (mc:MergeCandidate { candidate_id: $candidate_id, status: "pending" })
//   MATCH (a:Character { character_id: mc.character_a_id })
//   MATCH (b:Character { character_id: mc.character_b_id })
//   ... (mover [:HAS_MENTION] y [:APPEARS_IN], fusionar aliases,
//        SET mc.status = "accepted", mc.resolved_at = datetime(),
//        registrar b.character_id en a.merged_from para idempotencia,
//        DETACH DELETE b)
//
// Las decisiones (accepted/rejected) persisten: el pipeline consulta MergeCandidate
// resueltos antes de proponer o aplicar fusiones (INV-M1-4).
