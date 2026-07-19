"""Contratos Pydantic de la extracción de atributos (specs/004 data-model.md).

SCHEMA_VERSION entra en la clave de cache junto con PROMPT_VERSION: cambiar
cualquiera invalida los resultados cacheados (mismo patrón que M1/M2).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION: int = 1

AttrKey = Literal["eye_color", "hair", "height", "scar", "age", "gender", "status"]

#: Keys cuya semántica es de transición (no de igualdad). La LÓGICA de transición
#: vive en la spec de continuidad posterior (FR-017); aquí solo se etiqueta.
STATEFUL_KEYS: set[str] = {"status"}


def key_class(key: str) -> Literal["static", "stateful"]:
    """Clase del atributo: `stateful` si compara por transición, si no `static`."""
    return "stateful" if key in STATEFUL_KEYS else "static"


# ── Entrada (construida por el pipeline, no por el LLM) ───────────────────────


class CastEntry(BaseModel):
    """Personaje del cast de la escena, pasado como contexto al LLM."""

    character_id: str
    canonical_name: str
    aliases: list[str]


class AttributeSceneContext(BaseModel):
    """Contexto de una escena para la extracción de atributos."""

    scene_id: str
    chapter_title: str | None
    scene_text: str
    cast: list[CastEntry]


# ── Salida (validada; lo que el LLM devuelve) ─────────────────────────────────


class SceneAttributeEvidence(BaseModel):
    """Afirmación de un atributo de un personaje del cast en esta escena."""

    character_id: str
    key: AttrKey
    value_norm: str
    value_quote: str
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("value_norm")
    @classmethod
    def _value_norm_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("value_norm vacío")
        return v.strip().lower()


class SceneAttributes(BaseModel):
    """Salida completa de la extracción de atributos de una escena."""

    evidences: list[SceneAttributeEvidence]
    notes: str | None = None
