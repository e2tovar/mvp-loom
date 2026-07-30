"""Cola de fusiones: crear, listar y resolver MergeCandidate (contracts/graph-schema.cypher).

accept: mover menciones/apariciones de B a A, fusionar aliases, eliminar B.
reject: marcar permanentemente; el par no se vuelve a proponer (INV-M1-4).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from neo4j import Session

from backend.core.errors import AlreadyResolvedError, ManuscriptNotFoundError


def get_merge_candidates(
    sess: Session,
    manuscript_id: str,
    status: str = "pending",
) -> list[dict[str, Any]]:
    """Lista candidatos de fusión con el detalle de los dos personajes implicados."""
    if status == "all":
        where = "mc.manuscript_id = $mid"
    else:
        where = "mc.manuscript_id = $mid AND mc.status = $status"

    result = sess.run(
        f"""
        MATCH (mc:MergeCandidate)
        WHERE {where}
        MATCH (a:Character {{character_id: mc.character_a_id}})
        MATCH (b:Character {{character_id: mc.character_b_id}})
        RETURN mc {{
            .candidate_id, .confidence, .rationale,
            .evidence_json, .status
        }},
        a {{.character_id, .canonical_name, .aliases}} AS char_a,
        b {{.character_id, .canonical_name, .aliases}} AS char_b
        ORDER BY mc.confidence DESC
        """,
        mid=manuscript_id,
        status=status,
    )
    candidates = []
    for rec in result:
        mc = dict(rec["mc"])
        mc["characters"] = [dict(rec["char_a"]), dict(rec["char_b"])]
        try:
            mc["evidence"] = json.loads(mc.pop("evidence_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            mc["evidence"] = []
        candidates.append(mc)
    return candidates


def resolve_merge_candidate(
    sess: Session,
    candidate_id: str,
    decision: Literal["accept", "reject"],
) -> dict[str, Any]:
    """Aplica la decisión humana sobre un MergeCandidate.

    Returns:
        Character resultante (accept) o {"status": "rejected"} (reject).
    """
    if decision not in ("accept", "reject"):
        raise ValueError(f"Decisión inválida: {decision!r}. Usa 'accept' o 'reject'.")

    rec = sess.run(
        "MATCH (mc:MergeCandidate {candidate_id: $cid}) RETURN mc",
        cid=candidate_id,
    ).single()
    if rec is None:
        raise ManuscriptNotFoundError(f"MergeCandidate no encontrado: {candidate_id}")

    mc = rec["mc"]
    if mc["status"] != "pending":
        raise AlreadyResolvedError(
            f"El candidato {candidate_id} ya fue resuelto ({mc['status']})."
        )

    now = datetime.now(UTC).isoformat()
    char_a_id: str = mc["character_a_id"]
    char_b_id: str = mc["character_b_id"]

    if decision == "reject":
        sess.run(
            """
            MATCH (mc:MergeCandidate {candidate_id: $cid})
            SET mc.status = 'rejected', mc.resolved_at = $now
            """,
            cid=candidate_id,
            now=now,
        )
        return {"status": "rejected", "candidate_id": candidate_id}

    # accept: mover menciones y apariciones de B → A, fusionar aliases, borrar B
    # 1. Mover HAS_MENTION de B a A
    sess.run(
        """
        MATCH (b:Character {character_id: $bid})-[r:HAS_MENTION]->(mn:Mention)
        MATCH (a:Character {character_id: $aid})
        MERGE (a)-[:HAS_MENTION]->(mn)
        DELETE r
        """,
        bid=char_b_id,
        aid=char_a_id,
    )
    # 2. Mover APPEARS_IN de B a A (acumular mention_count)
    sess.run(
        """
        MATCH (b:Character {character_id: $bid})-[rb:APPEARS_IN]->(s:Scene)
        MATCH (a:Character {character_id: $aid})
        MERGE (a)-[ra:APPEARS_IN]->(s)
        ON CREATE SET ra.kind = rb.kind,
                      ra.mention_count = rb.mention_count,
                      ra.first_mention_id = rb.first_mention_id
        ON MATCH SET  ra.mention_count = ra.mention_count + rb.mention_count
        DELETE rb
        """,
        bid=char_b_id,
        aid=char_a_id,
    )
    # 3. Fusionar aliases y actualizar contadores en A
    result_a = sess.run(
        "MATCH (a:Character {character_id: $aid}) RETURN a",
        aid=char_a_id,
    ).single()
    result_b = sess.run(
        "MATCH (b:Character {character_id: $bid}) RETURN b",
        bid=char_b_id,
    ).single()
    if result_a and result_b:
        a_node = result_a["a"]
        b_node = result_b["b"]
        merged_aliases = list(
            set(a_node.get("aliases", []))
            | {b_node["canonical_name"]}
            | set(b_node.get("aliases", []))
        )
        merged_from = list(set(a_node.get("merged_from", []) or []) | {char_b_id})
        sess.run(
            """
            MATCH (a:Character {character_id: $aid})
            SET a.aliases = $aliases,
                a.merged_from = $merged_from,
                a.mention_count = a.mention_count + $b_mentions,
                a.appearance_count = a.appearance_count + $b_appearances
            """,
            aid=char_a_id,
            aliases=merged_aliases,
            merged_from=merged_from,
            b_mentions=b_node.get("mention_count", 0),
            b_appearances=b_node.get("appearance_count", 0),
        )
    # 4. Actualizar candidate y borrar B
    sess.run(
        """
        MATCH (mc:MergeCandidate {candidate_id: $cid})
        SET mc.status = 'accepted', mc.resolved_at = $now
        WITH mc
        MATCH (b:Character {character_id: $bid})
        DETACH DELETE b
        """,
        cid=candidate_id,
        now=now,
        bid=char_b_id,
    )
    # 5. Devolver el Character resultante
    final = sess.run(
        "MATCH (a:Character {character_id: $aid}) RETURN a",
        aid=char_a_id,
    ).single()
    return dict(final["a"]) if final else {"character_id": char_a_id}
