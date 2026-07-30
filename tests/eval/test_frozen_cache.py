"""Las respuestas LLM congeladas están completas y son las que los gates usarán.

Este test es la red que evita el peor fallo silencioso del enfoque: que falte una
entrada, el pipeline llame al LLM sin que nadie se dé cuenta, y el gate deje de
ser determinista (o falle en CI, donde no hay clave de API).

Puro: no necesita Neo4j ni cuota LLM. Solo calcula claves y mira el disco.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "eval" / "fixtures"
FROZEN = FIXTURES_DIR / "llm-cache"
MODEL = "openai/kimi-k2.5"  # el modelo del gate; la clave de caché lo incluye


def _m1_key(scene_text: str) -> str:
    from backend.extraction.prompts import PROMPT_VERSION
    from backend.extraction.schemas import SCHEMA_VERSION

    raw = scene_text + str(PROMPT_VERSION) + MODEL + str(SCHEMA_VERSION)
    return hashlib.sha256(raw.encode()).hexdigest()


def test_frozen_cache_directory_exists():
    assert FROZEN.is_dir(), (
        f"Falta {FROZEN}. Genéralo con: LOOM_CACHE_DIR={FROZEN} python -m eval.seed"
    )
    for sub in ("extraction", "relations", "attributes"):
        assert (FROZEN / sub).is_dir(), f"Falta el subdirectorio {sub}"


def test_every_m1_scene_of_every_gate_work_is_frozen():
    """Las 15 escenas de M1 (las 4 obras) tienen su respuesta congelada.

    Si este test falla tras cambiar PROMPT_VERSION o el modelo, es correcto que
    falle: hay que re-generar pagando y re-medir. No lo silencies.
    """
    from backend.ingest.pipeline import parse_manuscript
    from eval.seed import GATE_WORKS

    missing: list[str] = []
    total = 0
    for work in GATE_WORKS:
        m = parse_manuscript(FIXTURES_DIR / work.filename, work.source_format)
        for chapter in m.chapters:
            for scene in chapter.scenes:
                total += 1
                path = FROZEN / "extraction" / f"{_m1_key(scene.text)}.json"
                if not path.exists():
                    missing.append(f"{work.filename} · {scene.scene_id}")

    assert total == 15, f"Se esperaban 15 escenas en las 4 obras del gate, hay {total}"
    assert not missing, (
        "Respuestas M1 sin congelar:\n  " + "\n  ".join(missing) +
        f"\nRe-genera con: LOOM_CACHE_DIR={FROZEN} python -m eval.seed"
    )


@pytest.mark.parametrize("sub", ["extraction", "relations", "attributes"])
def test_frozen_entries_are_valid_json_with_content(sub):
    """Ninguna entrada vacía o corrupta: la caché las ignoraría en silencio
    (backend/llm/cache.py captura el error y devuelve None → llamada al LLM)."""
    entries = sorted((FROZEN / sub).glob("*.json"))
    assert entries, f"El subdirectorio {sub} está vacío"
    for path in entries:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict) and data, f"{path.name} vacío o no es objeto"


def test_frozen_cache_stays_small():
    """Guard de tamaño: aquí van solo las 4 obras crafted (5,4 KB de texto), nunca
    las novelas completas — esas son diagnóstico manual, no material del gate."""
    total = sum(p.stat().st_size for p in FROZEN.rglob("*.json"))
    assert total < 2_000_000, (
        f"La caché congelada pesa {total / 1e6:.1f} MB. ¿Se colaron las novelas?"
    )
