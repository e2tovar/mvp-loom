"""Endpoint de inspección de las fichas de atributos (spec 004, FR-013).

GET /manuscripts/{id}/attributes
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.graph import attributes as attr_graph
from backend.graph.client import session as db_session
from backend.graph.raw_layer import manuscript_exists

router = APIRouter()


@router.get("/manuscripts/{manuscript_id}/attributes")
def list_attributes(manuscript_id: str):
    with db_session() as sess:
        if not manuscript_exists(sess, manuscript_id):
            raise HTTPException(
                404, {"error": "not_found", "detail": "Manuscrito no encontrado."}
            )
        if not attr_graph.has_attributes(sess, manuscript_id):
            raise HTTPException(
                409,
                {"error": "not_extracted",
                 "detail": "Atributos no extraídos para este manuscrito."},
            )
        attributes = attr_graph.get_attributes_list(sess, manuscript_id)
    return {
        "manuscript_id": manuscript_id,
        "attribute_count": len(attributes),
        "attributes": attributes,
    }
