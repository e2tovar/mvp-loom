"""Endpoint de inspección del mapa de relaciones (spec 003, FR-014).

GET /manuscripts/{id}/relations
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException

from backend.graph import relations as rel_graph
from backend.graph.client import session as db_session
from backend.graph.raw_layer import manuscript_exists

router = APIRouter()


@router.get("/manuscripts/{manuscript_id}/relations")
def list_relations(
    manuscript_id: str,
    provenance: Literal["extracted", "inferred"] | None = None,
):
    with db_session() as sess:
        if not manuscript_exists(sess, manuscript_id):
            raise HTTPException(404, {"error": "not_found", "detail": "Manuscrito no encontrado."})
        if not rel_graph.has_relations(sess, manuscript_id):
            raise HTTPException(
                409,
                {"error": "not_extracted", "detail": "Relaciones no extraídas para este manuscrito."},
            )
        relations = rel_graph.get_relations_list(sess, manuscript_id, provenance=provenance)
    return {
        "manuscript_id": manuscript_id,
        "relation_count": len(relations),
        "relations": relations,
    }
