"""Rutas de manuscritos (contracts/api.md).

POST /manuscripts            — ingiere y segmenta (síncrono); 201 nuevo, 200 idempotente.
GET  /manuscripts/{id}/structure — resumen estructural inspeccionable.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import JSONResponse

from backend.core.errors import (
    InvalidFileError,
    LoomError,
    ManuscriptNotFoundError,
    NoNarrativeContentError,
    UnsupportedFormatError,
)
from backend.graph import client, raw_layer
from backend.ingest.models import SourceFormat
from backend.ingest.pipeline import parse_manuscript

router = APIRouter()

_SUPPORTED: set[str] = {"epub", "txt", "docx"}
_ERROR_STATUS: dict[str, int] = {
    "unsupported_format": 415,
    "invalid_file": 400,
    "no_narrative_content": 422,
    "not_found": 404,
}


def _error_response(exc: LoomError) -> JSONResponse:
    status = _ERROR_STATUS.get(exc.code, 400)
    return JSONResponse(status_code=status, content={"error": exc.code, "detail": str(exc)})


@router.post("/manuscripts")
async def ingest_manuscript(file: UploadFile = File(...)) -> JSONResponse:  # noqa: B008
    suffix = Path(file.filename or "").suffix.lower().lstrip(".")
    if suffix not in _SUPPORTED:
        return _error_response(
            UnsupportedFormatError(f"Formato '.{suffix}' no soportado. Use epub, txt o docx.")
        )

    data = await file.read()
    if not data:
        return _error_response(InvalidFileError("El archivo está vacío o no se pudo leer."))

    source_format: SourceFormat = suffix  # type: ignore[assignment]
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{suffix}", delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            manuscript = parse_manuscript(tmp_path, source_format)
        finally:
            tmp_path.unlink(missing_ok=True)
    except (UnsupportedFormatError, InvalidFileError, NoNarrativeContentError) as exc:
        return _error_response(exc)

    with client.session() as sess:
        created = not raw_layer.manuscript_exists(sess, manuscript.manuscript_id)
        raw_layer.write_raw_layer(sess, manuscript)

    body = {
        "manuscript_id": manuscript.manuscript_id,
        "title": manuscript.title,
        "source_format": manuscript.source_format,
        "word_count": manuscript.word_count,
        "chapter_count": manuscript.chapter_count,
        "scene_count": manuscript.scene_count,
        "non_narrative_block_count": len(manuscript.non_narrative_blocks),
        "created": created,
    }
    return JSONResponse(status_code=201 if created else 200, content=body)


@router.get("/manuscripts/{manuscript_id}/structure")
def get_manuscript_structure(
    manuscript_id: str,
    include_snippets: bool = Query(default=True),
    snippet_len: int = Query(default=120, ge=1, le=2000),
) -> JSONResponse:
    try:
        with client.session() as sess:
            structure = raw_layer.get_structure(
                sess,
                manuscript_id,
                include_snippets=include_snippets,
                snippet_len=snippet_len,
            )
    except ManuscriptNotFoundError as exc:
        return _error_response(exc)
    return JSONResponse(status_code=200, content=structure)
