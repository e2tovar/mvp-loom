"""Cache contenido-direccionada de respuestas LLM (research R6, Principio VI).

Clave: SHA-256(scene_text + str(PROMPT_VERSION) + model + str(SCHEMA_VERSION))
Store: JSON en .cache/extraction/<hex>.json (gitignored).
Invalidación automática al cambiar PROMPT_VERSION, SCHEMA_VERSION o modelo.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from backend.extraction.schemas import SceneContext, SceneExtraction

log = logging.getLogger(__name__)

_CACHE_DIR = Path(".cache") / "extraction"


class ExtractionCache:
    """Cache en disco para SceneExtraction, keyed por contenido + versiones."""

    def __init__(
        self,
        prompt_version: int,
        schema_version: int,
        model: str,
        cache_dir: Path | None = None,
    ) -> None:
        self._prompt_version = prompt_version
        self._schema_version = schema_version
        self._model = model
        self._dir = (cache_dir or _CACHE_DIR).resolve()
        self._dir.mkdir(parents=True, exist_ok=True)

    def _key(self, ctx: SceneContext) -> str:
        raw = (
            ctx.scene_text
            + str(self._prompt_version)
            + self._model
            + str(self._schema_version)
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def get(self, ctx: SceneContext) -> SceneExtraction | None:
        """Devuelve la extracción cacheada o None si no existe / es inválida."""
        path = self._path(self._key(ctx))
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SceneExtraction.model_validate(data)
        except Exception as exc:
            log.warning("Cache inválida en %s: %s — ignorada", path, exc)
            return None

    def set(self, ctx: SceneContext, extraction: SceneExtraction) -> None:
        """Guarda la extracción en disco."""
        path = self._path(self._key(ctx))
        try:
            path.write_text(
                extraction.model_dump_json(indent=2), encoding="utf-8"
            )
        except Exception as exc:
            log.warning("No se pudo escribir en cache %s: %s", path, exc)
