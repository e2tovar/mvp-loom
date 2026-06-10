"""Endpoints de inspección de personajes y cola de fusiones (contracts/api.md).

GET  /manuscripts/{id}/characters
GET  /manuscripts/{id}/characters/{character_id}
GET  /manuscripts/{id}/merge-candidates
POST /merge-candidates/{candidate_id}/resolve
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.errors import (
    AlreadyResolvedError,
    ManuscriptNotFoundError,
)
from backend.graph import characters as char_graph
from backend.graph.client import session as db_session
from backend.graph.merge_candidates import (
    get_merge_candidates,
    resolve_merge_candidate,
)
from backend.graph.raw_layer import manuscript_exists

router = APIRouter()


# ── Characters ────────────────────────────────────────────────────────────────


@router.get("/manuscripts/{manuscript_id}/characters")
def list_characters(
    manuscript_id: str,
    role: str | None = None,
    include_mentioned_only: bool = True,
    order_by: Literal["appearances", "first_appearance", "name"] = "appearances",
):
    with db_session() as sess:
        if not manuscript_exists(sess, manuscript_id):
            raise HTTPException(404, {"error": "not_found", "detail": "Manuscrito no encontrado."})
        if not char_graph.has_extraction(sess, manuscript_id):
            raise HTTPException(
                409, {"error": "not_extracted", "detail": "Extracción no ejecutada."}
            )
        characters = char_graph.get_characters_list(
            sess,
            manuscript_id,
            role=role,
            include_mentioned_only=include_mentioned_only,
            order_by=order_by,
        )
        pending = char_graph.count_pending_merge_candidates(sess, manuscript_id)
    return {
        "manuscript_id": manuscript_id,
        "character_count": len(characters),
        "pending_merge_candidates": pending,
        "characters": characters,
    }


@router.get("/manuscripts/{manuscript_id}/characters/{character_id}")
def get_character(manuscript_id: str, character_id: str):
    with db_session() as sess:
        if not manuscript_exists(sess, manuscript_id):
            raise HTTPException(404, {"error": "not_found", "detail": "Manuscrito no encontrado."})
        detail = char_graph.get_character_detail(sess, manuscript_id, character_id)
    if detail is None:
        raise HTTPException(404, {"error": "not_found", "detail": "Personaje no encontrado."})
    return detail


# ── Merge candidates ─────────────────────────────────────────────────────────


@router.get("/manuscripts/{manuscript_id}/merge-candidates")
def list_merge_candidates(
    manuscript_id: str,
    status: Literal["pending", "accepted", "rejected", "all"] = "pending",
):
    with db_session() as sess:
        if not manuscript_exists(sess, manuscript_id):
            raise HTTPException(404, {"error": "not_found", "detail": "Manuscrito no encontrado."})
        candidates = get_merge_candidates(sess, manuscript_id, status=status)
    return {"candidates": candidates}


class ResolveBody(BaseModel):
    decision: Literal["accept", "reject"]


@router.post("/merge-candidates/{candidate_id}/resolve")
def resolve_candidate_endpoint(candidate_id: str, body: ResolveBody):
    try:
        with db_session() as sess:
            result = resolve_merge_candidate(sess, candidate_id, body.decision)
    except ManuscriptNotFoundError as exc:
        raise HTTPException(404, {"error": "not_found", "detail": str(exc)}) from exc
    except AlreadyResolvedError as exc:
        raise HTTPException(409, {"error": "already_resolved", "detail": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(400, {"error": "invalid_decision", "detail": str(exc)}) from exc
    return result
