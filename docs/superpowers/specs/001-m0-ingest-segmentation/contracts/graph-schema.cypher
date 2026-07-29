// Graph Schema Contract — M0 Capa cruda (Neo4j 5.x)
// Feature: 001-m0-ingest-segmentation
//
// Constraints e índices del subconjunto del esquema necesario para M0.
// Las consultas con nombre viven en backend/graph/ (Principio: "Cypher revisable").
// Se aplican de forma idempotente al arrancar (IF NOT EXISTS).

// ── Constraints de unicidad (identidad estable y derivada del contenido) ──────

CREATE CONSTRAINT manuscript_id_unique IF NOT EXISTS
FOR (m:Manuscript) REQUIRE m.manuscript_id IS UNIQUE;

CREATE CONSTRAINT chapter_id_unique IF NOT EXISTS
FOR (c:Chapter) REQUIRE c.chapter_id IS UNIQUE;

CREATE CONSTRAINT scene_id_unique IF NOT EXISTS
FOR (s:Scene) REQUIRE s.scene_id IS UNIQUE;

CREATE CONSTRAINT nonnarrative_id_unique IF NOT EXISTS
FOR (n:NonNarrativeBlock) REQUIRE n.block_id IS UNIQUE;

// ── Índices de apoyo a la consulta de estructura ─────────────────────────────

CREATE INDEX chapter_by_manuscript IF NOT EXISTS
FOR (c:Chapter) ON (c.manuscript_id);

CREATE INDEX scene_by_chapter IF NOT EXISTS
FOR (s:Scene) ON (s.chapter_id);

CREATE INDEX scene_global_order IF NOT EXISTS
FOR (s:Scene) ON (s.order_narrative_global);

// ── Modelo de nodos (propiedades, ver data-model.md) ─────────────────────────
//
// (:Manuscript { manuscript_id, title, source_format, word_count,
//                chapter_count, ingested_at })
// (:Chapter    { chapter_id, manuscript_id, order_narrative, title, kind,
//                word_count, start_offset, end_offset })
// (:Scene      { scene_id, chapter_id, manuscript_id, order_in_chapter,
//                order_narrative_global, text, char_count, start_offset,
//                end_offset, boundary_reason, snippet })
// (:NonNarrativeBlock { block_id, manuscript_id, kind, text, detected_by, position })

// ── Relaciones ───────────────────────────────────────────────────────────────
//
// (Manuscript)-[:HAS_CHAPTER]->(Chapter)
// (Chapter)-[:HAS_SCENE]->(Scene)
// (Chapter)-[:NEXT_CHAPTER]->(Chapter)
// (Scene)-[:NEXT_SCENE]->(Scene)
// (Manuscript)-[:HAS_NON_NARRATIVE]->(NonNarrativeBlock)

// ── Escritura idempotente (patrón; los parámetros vienen del pipeline) ────────
// Ejemplo de upsert de un capítulo (MERGE por id estable → no duplica al re-ingerir):
//
//   MERGE (m:Manuscript { manuscript_id: $manuscript_id })
//     SET m += $manuscript_props
//   MERGE (c:Chapter { chapter_id: $chapter_id })
//     SET c += $chapter_props
//   MERGE (m)-[:HAS_CHAPTER]->(c);
//
// La re-ingestión del mismo contenido reproduce ids idénticos (SC-005), por lo que
// MERGE converge al mismo grafo sin crear nodos ni relaciones duplicados (FR-009).
