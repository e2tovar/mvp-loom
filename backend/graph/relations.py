"""Escritura/lectura idempotente de RelationEvidence/RELATES_TO en Neo4j (M2).

Contrato: docs/superpowers/specs/003-m2-relations/contracts/graph-schema.cypher. Ids deterministas
(INV-M2-2); Cypher solo vive aquí (constitución). RELATES_TO es una arista
DERIVADA de las evidencias: se reescribe entera en cada agregación, igual que
los contadores en characters.recompute_counters().
"""

from __future__ import annotations

import hashlib
from typing import Any

from neo4j import Session

# ── Ids deterministas ─────────────────────────────────────────────────────────


def canonical_pair(cid_a: str, cid_b: str) -> tuple[str, str]:
    """Par en orden lexicográfico — dirección canónica única (FR-007)."""
    return (cid_a, cid_b) if cid_a <= cid_b else (cid_b, cid_a)


def evidence_id(scene_id: str, cid_a: str, cid_b: str) -> str:
    """Id estable de la evidencia: (escena, par canónico). Máx 1 por par/escena."""
    a, b = canonical_pair(cid_a, cid_b)
    digest = hashlib.sha256(f"{a}::{b}".encode()).hexdigest()[:16]
    return f"{scene_id}:re:{digest}"


# ── Escritura ─────────────────────────────────────────────────────────────────


def upsert_relation_evidence(
    sess: Session,
    manuscript_id: str,
    scene_id: str,
    ev: dict[str, Any],
) -> str:
    """MERGE de RelationEvidence + ABOUT×2 + IN_SCENE + HAS_RELATION_EVIDENCE.

    `ev` llega con el par YA en orden canónico (lo garantiza el pipeline).
    """
    eid = evidence_id(scene_id, ev["character_a_id"], ev["character_b_id"])
    sess.run(
        """
        MERGE (re:RelationEvidence {evidence_id: $eid})
        SET re.manuscript_id  = $mid,
            re.scene_id       = $scene_id,
            re.character_a_id = $cid_a,
            re.character_b_id = $cid_b,
            re.rel_type       = $rel_type,
            re.descriptor     = $descriptor,
            re.role_a         = $role_a,
            re.role_b         = $role_b,
            re.provenance     = $provenance,
            re.confidence     = $confidence,
            re.quote          = $quote
        WITH re
        MATCH (m:Manuscript {manuscript_id: $mid})
        MERGE (m)-[:HAS_RELATION_EVIDENCE]->(re)
        WITH re
        MATCH (s:Scene {scene_id: $scene_id})
        MERGE (re)-[:IN_SCENE]->(s)
        WITH re
        MATCH (a:Character {character_id: $cid_a})
        MERGE (re)-[:ABOUT]->(a)
        WITH re
        MATCH (b:Character {character_id: $cid_b})
        MERGE (re)-[:ABOUT]->(b)
        """,
        eid=eid,
        mid=manuscript_id,
        scene_id=scene_id,
        cid_a=ev["character_a_id"],
        cid_b=ev["character_b_id"],
        rel_type=ev["rel_type"],
        descriptor=ev["descriptor"],
        role_a=ev.get("role_a"),
        role_b=ev.get("role_b"),
        provenance=ev["provenance"],
        confidence=ev["confidence"],
        quote=ev["quote"],
    )
    return eid


def replace_relates_to(
    sess: Session,
    manuscript_id: str,
    relations: list[dict[str, Any]],
) -> None:
    """Reescribe las aristas RELATES_TO del manuscrito (arista derivada).

    Borrar+reescribir garantiza que un par que cayó bajo el umbral en una
    re-agregación no deja arista fantasma (INV-M2-5).
    """
    sess.run(
        """
        MATCH (a:Character {manuscript_id: $mid})-[r:RELATES_TO]->()
        DELETE r
        """,
        mid=manuscript_id,
    )
    for rel in relations:
        cid_a, cid_b = canonical_pair(rel["character_a_id"], rel["character_b_id"])
        role_a, role_b = rel.get("role_a"), rel.get("role_b")
        if cid_a != rel["character_a_id"]:
            role_a, role_b = role_b, role_a
        sess.run(
            """
            MATCH (a:Character {character_id: $cid_a})
            MATCH (b:Character {character_id: $cid_b})
            MERGE (a)-[r:RELATES_TO]->(b)
            SET r.rel_type          = $rel_type,
                r.descriptor        = $descriptor,
                r.role_a            = $role_a,
                r.role_b            = $role_b,
                r.provenance        = $provenance,
                r.confidence        = $confidence,
                r.evidence_count    = $evidence_count,
                r.first_evidence_id = $first_evidence_id
            """,
            cid_a=cid_a,
            cid_b=cid_b,
            rel_type=rel["rel_type"],
            descriptor=rel["descriptor"],
            role_a=role_a,
            role_b=role_b,
            provenance=rel["provenance"],
            confidence=rel["confidence"],
            evidence_count=rel["evidence_count"],
            first_evidence_id=rel["first_evidence_id"],
        )


# ── Lectura ───────────────────────────────────────────────────────────────────


def get_scene_casts(sess: Session, manuscript_id: str) -> dict[str, list[dict[str, Any]]]:
    """scene_id → cast de personas (APPEARS_IN, entity_kind='person')."""
    result = sess.run(
        """
        MATCH (c:Character {manuscript_id: $mid})-[:APPEARS_IN]->(s:Scene)
        WHERE coalesce(c.entity_kind, 'person') = 'person'
        RETURN s.scene_id AS scene_id,
               c.character_id AS character_id,
               c.canonical_name AS canonical_name,
               c.aliases AS aliases
        ORDER BY s.scene_id, c.canonical_name
        """,
        mid=manuscript_id,
    )
    casts: dict[str, list[dict[str, Any]]] = {}
    for rec in result:
        casts.setdefault(rec["scene_id"], []).append(
            {
                "character_id": rec["character_id"],
                "canonical_name": rec["canonical_name"],
                "aliases": rec["aliases"] or [],
            }
        )
    return casts


def get_evidences_by_pair(
    sess: Session, manuscript_id: str
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Evidencias agrupadas por par canónico, con orden narrativo de su escena."""
    result = sess.run(
        """
        MATCH (re:RelationEvidence {manuscript_id: $mid})-[:IN_SCENE]->(s:Scene)
        RETURN re {.evidence_id, .character_a_id, .character_b_id, .rel_type,
                   .descriptor, .role_a, .role_b, .provenance, .confidence,
                   .quote, .scene_id},
               s.order_narrative_global AS narrative_order
        ORDER BY s.order_narrative_global
        """,
        mid=manuscript_id,
    )
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for rec in result:
        ev = dict(rec["re"])
        ev["narrative_order"] = rec["narrative_order"]
        pair = canonical_pair(ev["character_a_id"], ev["character_b_id"])
        by_pair.setdefault(pair, []).append(ev)
    return by_pair


def get_relations_list(
    sess: Session,
    manuscript_id: str,
    provenance: str | None = None,
) -> list[dict[str, Any]]:
    """Relaciones agregadas del manuscrito, con nombres para inspección (FR-014)."""
    filters = "WHERE a.manuscript_id = $mid"
    params: dict[str, Any] = {"mid": manuscript_id}
    if provenance:
        filters += " AND r.provenance = $prov"
        params["prov"] = provenance
    result = sess.run(
        f"""
        MATCH (a:Character)-[r:RELATES_TO]->(b:Character)
        {filters}
        RETURN a.character_id AS character_a_id,
               a.canonical_name AS character_a_name,
               a.aliases AS character_a_aliases,
               b.character_id AS character_b_id,
               b.canonical_name AS character_b_name,
               b.aliases AS character_b_aliases,
               r.rel_type AS rel_type,
               r.descriptor AS descriptor,
               r.role_a AS role_a,
               r.role_b AS role_b,
               r.provenance AS provenance,
               r.confidence AS confidence,
               r.evidence_count AS evidence_count,
               r.first_evidence_id AS first_evidence_id
        ORDER BY r.evidence_count DESC, a.canonical_name
        """,
        **params,
    )
    return [dict(rec) for rec in result]


def has_relations(sess: Session, manuscript_id: str) -> bool:
    result = sess.run(
        """
        MATCH (:Character {manuscript_id: $mid})-[r:RELATES_TO]->()
        RETURN count(r) > 0 AS present
        """,
        mid=manuscript_id,
    )
    row = result.single()
    return bool(row["present"]) if row else False
