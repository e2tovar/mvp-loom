"""Segmentación de escenas — Nivel 0 + Nivel 1 (FR-003, FR-004, research.md D5).

- Nivel 0: la frontera de capítulo abre la primera escena.
- Nivel 1: cada bloque `separator` cierra la escena actual y abre la siguiente.

Determinista y sin estado entre ejecuciones (preserva SC-005).
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.ingest.models import BoundaryReason
from backend.ingest.parsers.base import Block


@dataclass
class SceneDraft:
    text: str
    boundary_reason: BoundaryReason


def segment_scenes(chapter_blocks: list[Block]) -> list[SceneDraft]:
    """Divide los bloques de un capítulo en escenas por separadores explícitos."""
    scenes: list[SceneDraft] = []
    current: list[str] = []
    reason: BoundaryReason = "chapter_start"

    def flush() -> None:
        nonlocal current
        if current:
            scenes.append(SceneDraft(text="\n\n".join(current), boundary_reason=reason))
            current = []

    for block in chapter_blocks:
        if block.kind == "separator":
            flush()
            reason = "separator"
            continue
        if block.kind == "paragraph" and block.text.strip():
            current.append(block.text.strip())

    flush()
    return scenes
