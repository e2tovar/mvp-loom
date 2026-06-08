"""Contratos Pydantic v2 de la capa cruda (Principio III, data-model.md).

Estos modelos son la salida validada del pipeline de ingestión antes de escribir al
grafo. Solo incluyen lo necesario para M0 (segmentación estructural).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, NonNegativeInt, model_validator

SourceFormat = Literal["epub", "txt", "docx"]
ChapterKind = Literal["chapter", "prologue", "epilogue", "interlude", "other"]
BoundaryReason = Literal["chapter_start", "separator"]
NonNarrativeKind = Literal["license", "toc", "cover", "frontmatter", "backmatter", "other"]
NonNarrativePosition = Literal["before", "between", "after"]


class Scene(BaseModel):
    """Unidad mínima de la capa cruda; vive dentro de un capítulo."""

    scene_id: str
    chapter_id: str
    manuscript_id: str
    order_in_chapter: NonNegativeInt
    order_narrative_global: NonNegativeInt
    text: str
    char_count: NonNegativeInt
    start_offset: NonNegativeInt
    end_offset: NonNegativeInt
    boundary_reason: BoundaryReason
    snippet: str

    @model_validator(mode="after")
    def _check(self) -> Scene:
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset debe ser > start_offset")
        if self.char_count != len(self.text):
            raise ValueError("char_count debe coincidir con len(text)")
        return self


class Chapter(BaseModel):
    """Unidad estructural de primer nivel."""

    chapter_id: str
    manuscript_id: str
    order_narrative: NonNegativeInt
    title: str | None = None
    kind: ChapterKind = "chapter"
    word_count: NonNegativeInt
    start_offset: NonNegativeInt
    end_offset: NonNegativeInt
    scenes: list[Scene] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> Chapter:
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset debe ser > start_offset")
        if not self.scenes:
            raise ValueError("un capítulo debe tener al menos una escena (INV-5)")
        return self


class NonNarrativeBlock(BaseModel):
    """Contenido detectado como no narrativo: marcado, nunca contamina la narrativa."""

    block_id: str
    manuscript_id: str
    kind: NonNarrativeKind
    text: str
    detected_by: str
    position: NonNarrativePosition


class Manuscript(BaseModel):
    """La fuente inmutable; su identidad deriva del contenido (hashing.py)."""

    manuscript_id: str
    title: str | None = None
    source_format: SourceFormat
    word_count: NonNegativeInt
    chapter_count: NonNegativeInt
    ingested_at: datetime
    chapters: list[Chapter] = Field(default_factory=list)
    non_narrative_blocks: list[NonNarrativeBlock] = Field(default_factory=list)

    @property
    def scene_count(self) -> int:
        return sum(len(c.scenes) for c in self.chapters)

    @model_validator(mode="after")
    def _check(self) -> Manuscript:
        if self.chapter_count < 1:
            raise ValueError("un manuscrito válido tiene chapter_count >= 1 (INV-5)")
        if self.chapter_count != len(self.chapters):
            raise ValueError("chapter_count debe coincidir con len(chapters)")
        return self
