"""Errores de dominio de la ingestión (M0).

Se mapean a códigos HTTP en la capa de API (ver backend/api/routes_manuscripts.py).
"""

from __future__ import annotations


class LoomError(Exception):
    """Base de los errores de dominio de Loom."""

    #: Código estable usado en las respuestas de error de la API.
    code: str = "loom_error"


class UnsupportedFormatError(LoomError):
    """El formato del archivo no está soportado en M0 (solo epub/txt/docx)."""

    code = "unsupported_format"


class InvalidFileError(LoomError):
    """El archivo está vacío, corrupto o no se pudo leer (FR-011)."""

    code = "invalid_file"


class NoNarrativeContentError(LoomError):
    """El archivo se leyó pero no contiene contenido narrativo segmentable."""

    code = "no_narrative_content"


class ManuscriptNotFoundError(LoomError):
    """No existe un manuscrito con el id solicitado."""

    code = "not_found"
