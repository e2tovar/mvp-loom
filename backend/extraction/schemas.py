"""Contratos Pydantic de la extracción LLM (contracts/extraction-schema.md).

SCHEMA_VERSION se incluye en la clave de cache junto con PROMPT_VERSION: cambiar
cualquiera de los dos invalida todos los resultados cacheados.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

SCHEMA_VERSION: int = 2


# ── Entrada (construida por el pipeline, no por el LLM) ───────────────────────


class RegistryEntry(BaseModel):
    """Entidad ya conocida, pasada como contexto al LLM."""

    canonical_name: str
    aliases: list[str]
    role: str


class SceneContext(BaseModel):
    """Contexto de una escena que se entrega al pipeline de extracción."""

    scene_id: str
    chapter_title: str | None
    scene_text: str
    known_entities: list[RegistryEntry]


# ── Salida (validada; lo que el LLM devuelve) ─────────────────────────────────


class MentionOut(BaseModel):
    """Una mención de personaje detectada en la escena."""

    surface: str
    kind: Literal["name", "alias", "title", "description", "pronoun_resolved"]
    links_to: str | None
    quote: str


class CharacterCandidateOut(BaseModel):
    """Entidad nueva propuesta (no presente en el registro)."""

    canonical_name: str
    aliases: list[str] = []
    role: Literal["protagonist", "antagonist", "secondary", "minor", "unknown"] = "unknown"
    is_present_in_scene: bool


class SceneExtraction(BaseModel):
    """Salida completa de la extracción de una escena."""

    mentions: list[MentionOut]
    new_characters: list[CharacterCandidateOut]
    present_entities: list[str] = []
    notes: str | None = None


# ── Resolución de fusiones (nivel 2 de la cascada) ───────────────────────────


class MergeJudgement(BaseModel):
    """Veredicto del LLM sobre si dos entidades son el mismo personaje."""

    same_entity: bool
    confidence: float
    rationale: str
