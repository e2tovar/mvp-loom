"""Aplicación idempotente del esquema del grafo (contracts/graph-schema.cypher).

Las constraints/índices se crean con IF NOT EXISTS, de modo que aplicar el esquema en
cada arranque sea seguro y repetible.
"""

from __future__ import annotations

from neo4j import Session

#: Constraints e índices de M0 + delta de M1 (idempotentes con IF NOT EXISTS).
SCHEMA_STATEMENTS: tuple[str, ...] = (
    "CREATE CONSTRAINT manuscript_id_unique IF NOT EXISTS "
    "FOR (m:Manuscript) REQUIRE m.manuscript_id IS UNIQUE",
    "CREATE CONSTRAINT chapter_id_unique IF NOT EXISTS "
    "FOR (c:Chapter) REQUIRE c.chapter_id IS UNIQUE",
    "CREATE CONSTRAINT scene_id_unique IF NOT EXISTS "
    "FOR (s:Scene) REQUIRE s.scene_id IS UNIQUE",
    "CREATE CONSTRAINT nonnarrative_id_unique IF NOT EXISTS "
    "FOR (n:NonNarrativeBlock) REQUIRE n.block_id IS UNIQUE",
    "CREATE INDEX chapter_by_manuscript IF NOT EXISTS "
    "FOR (c:Chapter) ON (c.manuscript_id)",
    "CREATE INDEX scene_by_chapter IF NOT EXISTS "
    "FOR (s:Scene) ON (s.chapter_id)",
    "CREATE INDEX scene_global_order IF NOT EXISTS "
    "FOR (s:Scene) ON (s.order_narrative_global)",
    # ── M1: personajes, menciones y candidatos de fusión ─────────────────────
    "CREATE CONSTRAINT character_id_unique IF NOT EXISTS "
    "FOR (c:Character) REQUIRE c.character_id IS UNIQUE",
    "CREATE CONSTRAINT mention_id_unique IF NOT EXISTS "
    "FOR (m:Mention) REQUIRE m.mention_id IS UNIQUE",
    "CREATE CONSTRAINT merge_candidate_id_unique IF NOT EXISTS "
    "FOR (mc:MergeCandidate) REQUIRE mc.candidate_id IS UNIQUE",
    "CREATE INDEX character_by_manuscript IF NOT EXISTS "
    "FOR (c:Character) ON (c.manuscript_id)",
    "CREATE INDEX mention_by_scene IF NOT EXISTS "
    "FOR (m:Mention) ON (m.scene_id)",
    "CREATE INDEX merge_candidate_by_status IF NOT EXISTS "
    "FOR (mc:MergeCandidate) ON (mc.status)",
    # ── M2: evidencias de relación ────────────────────────────────────────────
    "CREATE CONSTRAINT relation_evidence_id_unique IF NOT EXISTS "
    "FOR (re:RelationEvidence) REQUIRE re.evidence_id IS UNIQUE",
    "CREATE INDEX relation_evidence_by_manuscript IF NOT EXISTS "
    "FOR (re:RelationEvidence) ON (re.manuscript_id)",
    "CREATE INDEX relation_evidence_by_scene IF NOT EXISTS "
    "FOR (re:RelationEvidence) ON (re.scene_id)",
    # ── M3: atributos de personaje ────────────────────────────────────────────
    "CREATE CONSTRAINT attribute_id_unique IF NOT EXISTS "
    "FOR (a:Attribute) REQUIRE a.attribute_id IS UNIQUE",
    "CREATE CONSTRAINT attribute_evidence_id_unique IF NOT EXISTS "
    "FOR (ae:AttributeEvidence) REQUIRE ae.evidence_id IS UNIQUE",
    "CREATE INDEX attribute_by_manuscript IF NOT EXISTS "
    "FOR (a:Attribute) ON (a.manuscript_id)",
    "CREATE INDEX attribute_evidence_by_manuscript IF NOT EXISTS "
    "FOR (ae:AttributeEvidence) ON (ae.manuscript_id)",
    "CREATE INDEX attribute_evidence_by_scene IF NOT EXISTS "
    "FOR (ae:AttributeEvidence) ON (ae.scene_id)",
)


def apply_schema(sess: Session) -> None:
    """Ejecuta todas las sentencias de esquema de forma idempotente."""
    for statement in SCHEMA_STATEMENTS:
        sess.run(statement)
