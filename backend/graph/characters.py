"""Escritura/lectura idempotente de Character/Mention en Neo4j (contracts/graph-schema.cypher).

Todos los ids son deterministas para garantizar idempotencia (Principio VI, INV-M1-1).
Las consultas Cypher viven aquí nombradas; ninguna otra capa las repite (constitución).
"""

from __future__ import annotations

import hashlib
import unicodedata
from typing import Any

from neo4j import Session

# ── Generación de ids deterministas ──────────────────────────────────────────


def character_id(manuscript_id: str, canonical_name: str) -> str:
    """Id estable: hash del par (manuscrito, nombre canónico normalizado)."""
    key = f"{manuscript_id}::{_norm(canonical_name)}"
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    return f"{manuscript_id}:ch:{digest}"


def mention_id(scene_id: str, surface: str, start_offset: int) -> str:
    key = f"{scene_id}::{surface}::{start_offset}"
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    return f"{scene_id}:mn:{digest}"


def merge_candidate_id(char_id_a: str, char_id_b: str) -> str:
    a, b = sorted([char_id_a, char_id_b])
    digest = hashlib.sha256(f"{a}::{b}".encode()).hexdigest()[:16]
    return f"mc:{digest}"


def _norm(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name)
    return nfkd.encode("ascii", "ignore").decode("ascii").casefold().strip()


# ── Escritura ─────────────────────────────────────────────────────────────────


def upsert_character(
    sess: Session,
    manuscript_id: str,
    canonical_name: str,
    aliases: list[str],
    role: str,
    is_mentioned_only: bool,
    first_scene_id: str,
) -> str:
    """MERGE idempotente de un nodo Character; devuelve su character_id."""
    cid = character_id(manuscript_id, canonical_name)
    sess.run(
        """
        MERGE (c:Character {character_id: $cid})
        ON CREATE SET
            c.manuscript_id      = $manuscript_id,
            c.canonical_name     = $canonical_name,
            c.aliases            = $aliases,
            c.role               = $role,
            c.is_mentioned_only  = $is_mentioned_only,
            c.first_scene_id     = $first_scene_id,
            c.appearance_count   = 0,
            c.mention_count      = 0
        ON MATCH SET
            c.aliases            = $aliases,
            c.role               = CASE WHEN c.role = 'unknown' THEN $role ELSE c.role END,
            c.is_mentioned_only  = c.is_mentioned_only AND $is_mentioned_only
        WITH c
        MATCH (m:Manuscript {manuscript_id: $manuscript_id})
        MERGE (m)-[:HAS_CHARACTER]->(c)
        """,
        cid=cid,
        manuscript_id=manuscript_id,
        canonical_name=canonical_name,
        aliases=aliases,
        role=role,
        is_mentioned_only=is_mentioned_only,
        first_scene_id=first_scene_id,
    )
    return cid


def upsert_mention(
    sess: Session,
    scene_id: str,
    manuscript_id: str,
    character_id_val: str,
    surface: str,
    kind: str,
    start_offset: int,
    end_offset: int,
    quote: str,
) -> str:
    """MERGE idempotente de Mention + relaciones HAS_MENTION e IN_SCENE."""
    mid = mention_id(scene_id, surface, start_offset)
    sess.run(
        """
        MERGE (mn:Mention {mention_id: $mid})
        ON CREATE SET
            mn.scene_id      = $scene_id,
            mn.manuscript_id = $manuscript_id,
            mn.surface       = $surface,
            mn.kind          = $kind,
            mn.start_offset  = $start_offset,
            mn.end_offset    = $end_offset,
            mn.quote         = $quote
        WITH mn
        MATCH (c:Character {character_id: $cid})
        MERGE (c)-[:HAS_MENTION]->(mn)
        WITH mn
        MATCH (s:Scene {scene_id: $scene_id})
        MERGE (mn)-[:IN_SCENE]->(s)
        """,
        mid=mid,
        scene_id=scene_id,
        manuscript_id=manuscript_id,
        surface=surface,
        kind=kind,
        start_offset=start_offset,
        end_offset=end_offset,
        quote=quote,
        cid=character_id_val,
    )
    return mid


def upsert_appears_in(
    sess: Session,
    character_id_val: str,
    scene_id: str,
    kind: str,
    first_mention_id: str = "",
) -> None:
    """MERGE idempotente de APPEARS_IN. kind solo mejora (mentioned → present).

    Los contadores NO se tocan aquí: los deriva recompute_counters() al final
    del pipeline (idempotencia, INV-M1-1).
    """
    sess.run(
        """
        MATCH (c:Character {character_id: $cid})
        MATCH (s:Scene {scene_id: $scene_id})
        MERGE (c)-[r:APPEARS_IN]->(s)
        ON CREATE SET
            r.kind             = $kind,
            r.first_mention_id = $first_mention_id
        ON MATCH SET
            r.kind = CASE
                WHEN r.kind = 'present' OR $kind = 'present' THEN 'present'
                ELSE r.kind
            END
        """,
        cid=character_id_val,
        scene_id=scene_id,
        kind=kind,
        first_mention_id=first_mention_id,
    )


def recompute_counters(sess: Session, manuscript_id: str) -> None:
    """Deriva todos los contadores del grafo (idempotente por construcción).

    Reemplaza los incrementos in-place que inflaban mention_count ~11x en
    re-runs (Elizabeth: 2961 acumulado vs 273 real).
    """
    sess.run(
        """
        MATCH (c:Character {manuscript_id: $mid})
        OPTIONAL MATCH (c)-[:HAS_MENTION]->(mn:Mention)
        WITH c, count(mn) AS mc
        SET c.mention_count = mc
        """,
        mid=manuscript_id,
    )
    sess.run(
        """
        MATCH (c:Character {manuscript_id: $mid})
        OPTIONAL MATCH (c)-[:APPEARS_IN]->(s:Scene)
        WITH c, count(s) AS ac
        SET c.appearance_count = ac
        """,
        mid=manuscript_id,
    )
    sess.run(
        """
        MATCH (c:Character {manuscript_id: $mid})-[r:APPEARS_IN]->(s:Scene)
        OPTIONAL MATCH (c)-[:HAS_MENTION]->(mn:Mention)
        WHERE mn.scene_id = s.scene_id
        WITH r, count(mn) AS rmc, collect(mn) AS mns
        SET r.mention_count = rmc
        WITH r, mns
        UNWIND CASE WHEN size(mns) = 0 THEN [null] ELSE mns END AS mn
        WITH r, mn ORDER BY mn.start_offset ASC
        WITH r, collect(mn.mention_id)[0] AS first_id
        SET r.first_mention_id = coalesce(first_id, r.first_mention_id)
        """,
        mid=manuscript_id,
    )
    # is_mentioned_only derivado del grafo: un personaje "solo mencionado" es el
    # que NO tiene ninguna aparición física (APPEARS_IN kind='present'). Esto
    # corrige el flag para personajes cuya primera extracción fue una mención
    # (Elizabeth: 273 menciones, presente en muchas escenas, marcada mo=True).
    sess.run(
        """
        MATCH (c:Character {manuscript_id: $mid})
        OPTIONAL MATCH (c)-[r:APPEARS_IN {kind: 'present'}]->(:Scene)
        WITH c, count(r) AS present_count
        SET c.is_mentioned_only = (present_count = 0)
        """,
        mid=manuscript_id,
    )


# ── Lectura ───────────────────────────────────────────────────────────────────


def get_characters_list(
    sess: Session,
    manuscript_id: str,
    role: str | None = None,
    include_mentioned_only: bool = True,
    order_by: str = "appearances",
) -> list[dict[str, Any]]:
    """Lista de personajes de un manuscrito con filtros y orden."""
    order_clause = {
        "appearances": "c.appearance_count DESC",
        "first_appearance": "c.first_scene_id ASC",
        "name": "c.canonical_name ASC",
    }.get(order_by, "c.appearance_count DESC")

    filters = ["c.manuscript_id = $manuscript_id"]
    params: dict[str, Any] = {"manuscript_id": manuscript_id}
    if role:
        filters.append("c.role = $role")
        params["role"] = role
    if not include_mentioned_only:
        filters.append("c.is_mentioned_only = false")

    where = " AND ".join(filters)
    result = sess.run(
        f"""
        MATCH (c:Character)
        WHERE {where}
        OPTIONAL MATCH (c)-[:APPEARS_IN]->(s:Scene)
        WITH c, min(s.order_narrative_global) AS first_order
        OPTIONAL MATCH (c)-[r:APPEARS_IN]->(fs:Scene)
        WHERE fs.order_narrative_global = first_order
        OPTIONAL MATCH (primary_mn:Mention {{mention_id: r.first_mention_id}})
        WITH c, first_order, fs, primary_mn
        OPTIONAL MATCH (c)-[:HAS_MENTION]->(fallback_mn:Mention)
        WHERE fallback_mn.scene_id = fs.scene_id
        WITH c, first_order, fs, primary_mn, fallback_mn
        ORDER BY fallback_mn.start_offset ASC
        WITH c, first_order, fs, primary_mn, collect(fallback_mn)[0] AS fallback_first
        RETURN c {{
            .character_id, .canonical_name, .aliases, .role,
            .is_mentioned_only, .appearance_count, .mention_count,
            .first_scene_id
        }}, fs.scene_id AS first_scene_id_actual,
           first_order AS chapter_order,
           coalesce(primary_mn.quote, fallback_first.quote) AS first_quote
        ORDER BY {order_clause}
        """,
        **params,
    )
    rows = []
    for rec in result:
        char = dict(rec["c"])
        char["first_appearance"] = {
            "scene_id": rec["first_scene_id_actual"],
            "chapter_order": rec["chapter_order"],
            "quote": rec["first_quote"],
        }
        rows.append(char)
    return rows


def get_character_detail(
    sess: Session,
    manuscript_id: str,
    character_id_val: str,
) -> dict[str, Any] | None:
    """Detalle de un personaje con apariciones y menciones."""
    result = sess.run(
        """
        MATCH (c:Character {character_id: $cid, manuscript_id: $mid})
        RETURN c {.character_id, .canonical_name, .aliases, .role,
                  .is_mentioned_only, .appearance_count, .mention_count}
        """,
        cid=character_id_val,
        mid=manuscript_id,
    )
    row = result.single()
    if row is None:
        return None

    char = dict(row["c"])

    appearances = sess.run(
        """
        MATCH (c:Character {character_id: $cid})-[r:APPEARS_IN]->(s:Scene)
        RETURN s.scene_id AS scene_id, r.kind AS kind, r.mention_count AS mention_count
        ORDER BY s.order_narrative_global
        """,
        cid=character_id_val,
    )
    char["appearances"] = [dict(r) for r in appearances]

    mentions = sess.run(
        """
        MATCH (c:Character {character_id: $cid})-[:HAS_MENTION]->(mn:Mention)
        RETURN mn {.mention_id, .surface, .kind, .scene_id,
                   .start_offset, .end_offset, .quote}
        ORDER BY mn.scene_id, mn.start_offset
        """,
        cid=character_id_val,
    )
    char["mentions"] = [dict(r["mn"]) for r in mentions]
    return char


def get_scene_coordinates(sess: Session, manuscript_id: str) -> dict[str, str]:
    """Mapa scene_id → coordenada 'c{cap}/s{escena}' (mismo formato que el gold del eval)."""
    result = sess.run(
        """
        MATCH (m:Manuscript {manuscript_id: $mid})-[:HAS_CHAPTER]->(c:Chapter)
              -[:HAS_SCENE]->(s:Scene)
        RETURN s.scene_id AS scene_id,
               c.order_narrative AS chapter_order,
               s.order_in_chapter AS scene_order
        """,
        mid=manuscript_id,
    )
    return {
        rec["scene_id"]: f"c{rec['chapter_order']}/s{rec['scene_order']}"
        for rec in result
    }


def count_pending_merge_candidates(sess: Session, manuscript_id: str) -> int:
    result = sess.run(
        """
        MATCH (mc:MergeCandidate {manuscript_id: $mid, status: 'pending'})
        RETURN count(mc) AS n
        """,
        mid=manuscript_id,
    )
    row = result.single()
    return row["n"] if row else 0


def has_extraction(sess: Session, manuscript_id: str) -> bool:
    result = sess.run(
        """
        MATCH (c:Character {manuscript_id: $mid})
        RETURN count(c) > 0 AS extracted
        """,
        mid=manuscript_id,
    )
    row = result.single()
    return bool(row["extracted"]) if row else False
