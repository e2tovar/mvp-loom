"""Escritura/lectura idempotente de AttributeEvidence/Attribute en Neo4j (M3).

Contrato: specs/004-m3-attributes/contracts/graph-schema.cypher. Ids
deterministas; Cypher solo vive aquí (constitución). Los nodos Attribute son
DERIVADOS de las evidencias: se borran y reescriben en cada agregación, igual
que RELATES_TO en relations.replace_relates_to().
"""

from __future__ import annotations

import hashlib
from typing import Any

from neo4j import Session


def attribute_evidence_id(scene_id: str, character_id: str, key: str) -> str:
    """Id estable de la evidencia: (escena, personaje, key). Máx 1 por combinación."""
    digest = hashlib.sha256(f"{character_id}::{key}".encode()).hexdigest()[:16]
    return f"{scene_id}:ae:{digest}"


def attribute_node_id(
    manuscript_id: str, character_id: str, key: str, value_norm: str
) -> str:
    """Id determinista del nodo Attribute: por (personaje, key, valor)."""
    digest = hashlib.sha256(value_norm.encode()).hexdigest()[:16]
    return f"{character_id}:attr:{key}:{digest}"


# ── Escritura ─────────────────────────────────────────────────────────────────


def upsert_attribute_evidence(
    sess: Session, manuscript_id: str, scene_id: str, ev: dict[str, Any]
) -> str:
    """MERGE de AttributeEvidence + ABOUT + IN_SCENE + HAS_ATTRIBUTE_EVIDENCE."""
    eid = attribute_evidence_id(scene_id, ev["character_id"], ev["key"])
    sess.run(
        """
        MATCH (m:Manuscript {manuscript_id: $mid})
        MATCH (s:Scene {scene_id: $scene_id})
        MATCH (c:Character {character_id: $cid})
        MERGE (ae:AttributeEvidence {evidence_id: $eid})
        SET ae.manuscript_id = $mid,
            ae.scene_id      = $scene_id,
            ae.character_id  = $cid,
            ae.key           = $key,
            ae.value_norm    = $value_norm,
            ae.value_quote   = $value_quote,
            ae.confidence    = $confidence
        MERGE (m)-[:HAS_ATTRIBUTE_EVIDENCE]->(ae)
        MERGE (ae)-[:IN_SCENE]->(s)
        MERGE (ae)-[:ABOUT]->(c)
        """,
        eid=eid, mid=manuscript_id, scene_id=scene_id,
        cid=ev["character_id"], key=ev["key"], value_norm=ev["value_norm"],
        value_quote=ev["value_quote"], confidence=ev["confidence"],
    )
    return eid


def replace_attributes(
    sess: Session, manuscript_id: str, nodes: list[dict[str, Any]]
) -> None:
    """Reescribe los nodos Attribute del manuscrito (derivados de evidencias).

    Borrar+reescribir garantiza que un valor que dejó de afirmarse en una
    re-agregación no deja nodo fantasma.
    """
    sess.run(
        """
        MATCH (:Character {manuscript_id: $mid})-[h:HAS_ATTRIBUTE]->(a:Attribute)
        DELETE h, a
        """,
        mid=manuscript_id,
    )
    for n in nodes:
        aid = attribute_node_id(
            manuscript_id, n["character_id"], n["key"], n["value_norm"]
        )
        sess.run(
            """
            MATCH (c:Character {character_id: $cid})
            MERGE (a:Attribute {attribute_id: $aid})
            SET a.manuscript_id     = $mid,
                a.character_id       = $cid,
                a.key                = $key,
                a.value_norm         = $value_norm,
                a.attr_class         = $attr_class,
                a.confidence         = $confidence,
                a.evidence_count     = $evidence_count,
                a.first_evidence_id  = $first_evidence_id
            MERGE (c)-[:HAS_ATTRIBUTE]->(a)
            """,
            aid=aid, mid=manuscript_id, cid=n["character_id"], key=n["key"],
            value_norm=n["value_norm"], attr_class=n["attr_class"],
            confidence=n["confidence"], evidence_count=n["evidence_count"],
            first_evidence_id=n["first_evidence_id"],
        )


# ── Lectura ───────────────────────────────────────────────────────────────────


def get_attribute_evidences(
    sess: Session, manuscript_id: str
) -> list[dict[str, Any]]:
    """Evidencias del manuscrito con el orden narrativo de su escena (para agregar)."""
    result = sess.run(
        """
        MATCH (ae:AttributeEvidence {manuscript_id: $mid})-[:IN_SCENE]->(s:Scene)
        RETURN ae {.evidence_id, .character_id, .key, .value_norm,
                   .value_quote, .confidence, .scene_id},
               s.order_narrative_global AS narrative_order
        ORDER BY s.order_narrative_global
        """,
        mid=manuscript_id,
    )
    out: list[dict[str, Any]] = []
    for rec in result:
        ev = dict(rec["ae"])
        ev["narrative_order"] = rec["narrative_order"]
        out.append(ev)
    return out


def get_attributes_list(
    sess: Session, manuscript_id: str
) -> list[dict[str, Any]]:
    """Atributos del manuscrito con nombre de personaje, para inspección (FR-013)."""
    result = sess.run(
        """
        MATCH (c:Character {manuscript_id: $mid})-[:HAS_ATTRIBUTE]->(a:Attribute)
        RETURN c.character_id AS character_id,
               c.canonical_name AS character_name,
               a.key AS key,
               a.value_norm AS value_norm,
               a.attr_class AS attr_class,
               a.confidence AS confidence,
               a.evidence_count AS evidence_count,
               a.first_evidence_id AS first_evidence_id
        ORDER BY c.canonical_name, a.key, a.value_norm
        """,
        mid=manuscript_id,
    )
    return [dict(rec) for rec in result]


def has_attributes(sess: Session, manuscript_id: str) -> bool:
    result = sess.run(
        """
        MATCH (:Character {manuscript_id: $mid})-[:HAS_ATTRIBUTE]->(:Attribute)
        RETURN count(*) > 0 AS present
        """,
        mid=manuscript_id,
    )
    row = result.single()
    return bool(row["present"]) if row else False
