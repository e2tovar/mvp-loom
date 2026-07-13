"""Invariante de no-pérdida (SC-004, INV-2) y no-contaminación (SC-007, INV-4) — T037.

Solo usa el pipeline; no requiere Neo4j.
"""

from __future__ import annotations

import pytest

from backend.core.hashing import normalize_narrative
from backend.ingest.pipeline import parse_manuscript

pytestmark = pytest.mark.unit


def test_narrative_reconstructs_without_loss(fixtures_dir):
    m = parse_manuscript(fixtures_dir / "crafted-three-chapters.txt", "txt")
    reconstructed = "\n\n".join(
        s.text for c in m.chapters for s in c.scenes
    )
    # El texto narrativo reconstruido contiene las frases narrativas...
    assert "vieja casa junto al río" in reconstructed
    assert "Elena abrió la puerta" in reconstructed
    assert "tren se detuvo en un pueblo sin nombre" in reconstructed
    # ...y es estable bajo la normalización (no hay basura adicional).
    assert reconstructed == normalize_narrative(reconstructed)


def test_non_narrative_not_in_scenes(fixtures_dir):
    m = parse_manuscript(fixtures_dir / "crafted-three-chapters.txt", "txt")
    scene_text = " ".join(s.text for c in m.chapters for s in c.scenes)
    # Front matter / back matter excluidos de la narrativa (SC-007).
    assert "Copyright" not in scene_text
    assert "TABLE OF CONTENTS" not in scene_text
    assert "trailing license boilerplate" not in scene_text
    # Los separadores no forman parte del texto de ninguna escena.
    assert "* * *" not in scene_text


def test_scene_offsets_are_ordered_and_non_overlapping(fixtures_dir):
    m = parse_manuscript(fixtures_dir / "crafted-three-chapters.txt", "txt")
    scenes = [s for c in m.chapters for s in c.scenes]
    orders = [s.order_narrative_global for s in scenes]
    assert orders == list(range(len(scenes)))  # INV-3: permutación 0..N-1 sin huecos
    for s in scenes:
        assert s.end_offset > s.start_offset
