"""Cache contenido-direccionada de respuestas LLM (research R6, Principio VI).

Clave: SHA-256(scene_text + str(PROMPT_VERSION) + model + str(SCHEMA_VERSION))
Store: JSON en <LOOM_CACHE_DIR o .cache>/{extraction,relations,attributes}/<hex>.json
       Por defecto gitignored; el eval apunta LOOM_CACHE_DIR a un directorio
       versionado (eval/fixtures/llm-cache) para que sus gates no dependan de
       llamadas de pago.
Invalidación automática al cambiar PROMPT_VERSION, SCHEMA_VERSION o modelo.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from backend.extraction.schemas import SceneContext, SceneExtraction

log = logging.getLogger(__name__)

_CACHE_ROOT_ENV = "LOOM_CACHE_DIR"
_DEFAULT_CACHE_ROOT = Path(".cache")


def _cache_root() -> Path:
    """Raíz de las cachés LLM, configurable por entorno.

    Se lee en cada instanciación (no al importar) para que el sembrador del eval
    pueda apuntar a `eval/fixtures/llm-cache` sin tocar los CLIs de extracción.
    """
    import os

    raw = os.environ.get(_CACHE_ROOT_ENV)
    return Path(raw) if raw else _DEFAULT_CACHE_ROOT


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
        self._dir = (cache_dir or _cache_root() / "extraction").resolve()
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def dir(self) -> Path:
        """Directorio donde esta caché lee y escribe (solo lectura)."""
        return self._dir

    @property
    def model(self) -> str:
        """Modelo LLM con el que se compone la clave de cache (solo lectura)."""
        return self._model

    @property
    def prompt_version(self) -> int:
        """PROMPT_VERSION con el que se compone la clave de cache (solo lectura)."""
        return self._prompt_version

    @property
    def schema_version(self) -> int:
        """SCHEMA_VERSION con el que se compone la clave de cache (solo lectura)."""
        return self._schema_version

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


class RelationsCache:
    """Cache en disco para SceneRelations (M2), keyed por contenido + cast.

    A diferencia de ExtractionCache, la clave incluye el fingerprint del cast:
    si M1 cambia el cast de la escena, la entrada se invalida sola (FR-008).
    """

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
        self._dir = (cache_dir or _cache_root() / "relations").resolve()
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def dir(self) -> Path:
        """Directorio donde esta caché lee y escribe (solo lectura)."""
        return self._dir

    @property
    def model(self) -> str:
        """Modelo LLM con el que se compone la clave de cache (solo lectura)."""
        return self._model

    @property
    def prompt_version(self) -> int:
        """PROMPT_VERSION con el que se compone la clave de cache (solo lectura)."""
        return self._prompt_version

    @property
    def schema_version(self) -> int:
        """SCHEMA_VERSION con el que se compone la clave de cache (solo lectura)."""
        return self._schema_version

    def _key(self, ctx: RelationSceneContext) -> str:  # noqa: F821
        cast_fp = ",".join(sorted(c.character_id for c in ctx.cast))
        raw = (
            ctx.scene_text
            + cast_fp
            + str(self._prompt_version)
            + self._model
            + str(self._schema_version)
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def get(self, ctx: RelationSceneContext) -> SceneRelations | None:  # noqa: F821
        from backend.extraction.relations.schemas import SceneRelations

        path = self._path(self._key(ctx))
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SceneRelations.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            log.warning("Cache inválida en %s: %s — ignorada", path, exc)
            return None

    def set(self, ctx: RelationSceneContext, out: SceneRelations) -> None:  # noqa: F821
        path = self._path(self._key(ctx))
        try:
            path.write_text(out.model_dump_json(indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            log.warning("No se pudo escribir en cache %s: %s", path, exc)


class AttributesCache:
    """Cache en disco para SceneAttributes (M3), keyed por contenido + cast.

    Igual que RelationsCache, la clave incluye el fingerprint del cast: si M1
    cambia el cast de la escena, la entrada se invalida sola (FR-007).
    """

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
        self._dir = (cache_dir or _cache_root() / "attributes").resolve()
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def dir(self) -> Path:
        """Directorio donde esta caché lee y escribe (solo lectura)."""
        return self._dir

    @property
    def model(self) -> str:
        """Modelo LLM con el que se compone la clave de cache (solo lectura)."""
        return self._model

    @property
    def prompt_version(self) -> int:
        """PROMPT_VERSION con el que se compone la clave de cache (solo lectura)."""
        return self._prompt_version

    @property
    def schema_version(self) -> int:
        """SCHEMA_VERSION con el que se compone la clave de cache (solo lectura)."""
        return self._schema_version

    def _key(self, ctx: AttributeSceneContext) -> str:  # noqa: F821
        cast_fp = ",".join(sorted(c.character_id for c in ctx.cast))
        raw = (
            ctx.scene_text
            + cast_fp
            + str(self._prompt_version)
            + self._model
            + str(self._schema_version)
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def get(self, ctx: AttributeSceneContext) -> SceneAttributes | None:  # noqa: F821
        from backend.extraction.attributes.schemas import SceneAttributes

        path = self._path(self._key(ctx))
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SceneAttributes.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            log.warning("Cache inválida en %s: %s — ignorada", path, exc)
            return None

    def set(self, ctx: AttributeSceneContext, out: SceneAttributes) -> None:  # noqa: F821
        path = self._path(self._key(ctx))
        try:
            path.write_text(out.model_dump_json(indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            log.warning("No se pudo escribir en cache %s: %s", path, exc)
