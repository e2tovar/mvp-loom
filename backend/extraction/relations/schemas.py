"""Contratos Pydantic de la extracción de relaciones (specs/003 data-model.md).

SCHEMA_VERSION entra en la clave de cache junto con PROMPT_VERSION: cambiar
cualquiera invalida los resultados cacheados (mismo patrón que M1).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION: int = 1

RelType = Literal[
    "family", "romantic", "friendship", "antagonism", "professional", "social", "other"
]


# ── Entrada (construida por el pipeline, no por el LLM) ───────────────────────


class CastEntry(BaseModel):
    """Personaje del cast de la escena, pasado como contexto al LLM."""

    character_id: str
    canonical_name: str
    aliases: list[str]


class RelationSceneContext(BaseModel):
    """Contexto de una escena para la extracción de relaciones."""

    scene_id: str
    chapter_title: str | None
    scene_text: str
    cast: list[CastEntry]


# ── Salida (validada; lo que el LLM devuelve) ─────────────────────────────────


class SceneRelationEvidence(BaseModel):
    """Señal de relación entre un par del cast en esta escena."""

    character_a_id: str
    character_b_id: str
    rel_type: RelType
    descriptor: str
    role_a: str | None = None
    role_b: str | None = None
    provenance: Literal["extracted", "inferred"]
    confidence: float = Field(ge=0.0, le=1.0)
    quote: str

    @model_validator(mode="after")
    def _distinct_pair(self) -> SceneRelationEvidence:
        if self.character_a_id == self.character_b_id:
            raise ValueError("auto-relación inválida: character_a_id == character_b_id")
        return self


class SceneRelations(BaseModel):
    """Salida completa de la extracción de relaciones de una escena."""

    evidences: list[SceneRelationEvidence]
    notes: str | None = None
