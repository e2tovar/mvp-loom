"""Siembra el grafo con lo que los gates de eval necesitan medir.

python -m eval.seed [--force]

Determinista y sin coste: apunta LOOM_CACHE_DIR a las respuestas LLM congeladas
(eval/fixtures/llm-cache), así que las 21 escenas de las 4 obras crafted salen de
disco en vez de la API. Si falta una entrada — porque cambió PROMPT_VERSION, el
esquema o el modelo — el pipeline llamará al LLM de verdad y hará falta
LOOM_LLM_API_KEY. Eso es deliberado: cambiar el prompt obliga a re-medir.

Idempotente: los manuscript_id son hashes de contenido y los pipelines cachean,
así que re-ejecutar no duplica nodos ni gasta cuota.

NUNCA borra nada. Solo escribe las obras del gate; cualquier otro manuscrito del
grafo queda intacto (ver docs/known-issues.md → follow-up 1 de M1).
"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
FROZEN_CACHE_DIR = FIXTURES_DIR / "llm-cache"

log = logging.getLogger("eval.seed")


@dataclass(frozen=True)
class SeedWork:
    """Una obra del gate y las capas de extracción que sus gates exigen."""

    filename: str
    source_format: str
    layers: tuple[str, ...]


# Qué mide cada gate (verificado 2026-07-30):
#   test_characters_gate  → crafted-three-chapters.txt, crafted-two-chapters.epub
#   test_relations_gate   → crafted-relations.txt   (necesita M1 antes)
#   test_attributes_gate  → crafted-attributes.txt  (necesita M1 antes)
GATE_WORKS: tuple[SeedWork, ...] = (
    SeedWork("crafted-three-chapters.txt", "txt", ("m1",)),
    SeedWork("crafted-two-chapters.epub", "epub", ("m1",)),
    SeedWork("crafted-relations.txt", "txt", ("m1", "m2")),
    SeedWork("crafted-attributes.txt", "txt", ("m1", "m3")),
)


def _use_frozen_cache() -> None:
    """Apunta las cachés LLM al directorio versionado, si no se fijó otra raíz."""
    os.environ.setdefault("LOOM_CACHE_DIR", str(FROZEN_CACHE_DIR))


def _ingest(work: SeedWork) -> str:
    """Escribe la capa cruda de la obra y devuelve su manuscript_id."""
    from backend.graph import raw_layer, schema
    from backend.graph.client import session as db_session
    from backend.ingest.pipeline import parse_manuscript

    manuscript = parse_manuscript(FIXTURES_DIR / work.filename, work.source_format)
    with db_session() as sess:
        schema.apply_schema(sess)
        # write_raw_layer hace MERGE por manuscript_id: idempotente, no borra.
        raw_layer.write_raw_layer(sess, manuscript)
    return manuscript.manuscript_id


def _extract(work: SeedWork, manuscript_id: str, force: bool) -> None:
    """Ejecuta las capas M1/M2/M3 que esta obra necesita, en orden."""
    from backend.extraction.attributes.prompts import (
        PROMPT_VERSION as ATTR_PROMPT_VERSION,
    )
    from backend.extraction.attributes.schemas import (
        SCHEMA_VERSION as ATTR_SCHEMA_VERSION,
    )
    from backend.extraction.prompts import PROMPT_VERSION as M1_PROMPT_VERSION
    from backend.extraction.relations.prompts import (
        PROMPT_VERSION as REL_PROMPT_VERSION,
    )
    from backend.extraction.relations.schemas import (
        SCHEMA_VERSION as REL_SCHEMA_VERSION,
    )
    from backend.extraction.schemas import SCHEMA_VERSION as M1_SCHEMA_VERSION
    from backend.llm.cache import AttributesCache, ExtractionCache, RelationsCache
    from backend.llm.litellm_client import LiteLLMClient

    model = os.environ.get("LOOM_LLM_MODEL", "unknown")
    llm = LiteLLMClient()

    if "m1" in work.layers:
        from backend.extraction.pipeline import run_pipeline

        cache = ExtractionCache(
            prompt_version=M1_PROMPT_VERSION,
            schema_version=M1_SCHEMA_VERSION,
            model=model,
        )
        res = run_pipeline(
            manuscript_id=manuscript_id, llm_client=llm, cache=cache, force=force
        )
        m1_cache_hits = sum(1 for r in res.scene_results if r.cache_hit)
        log.info(
            "%s · M1: %d escenas, %d cache hits",
            work.filename, res.scenes_processed, m1_cache_hits,
        )

    if "m2" in work.layers:
        from backend.extraction.relations.pipeline import run_relations_pipeline

        cache = RelationsCache(
            prompt_version=REL_PROMPT_VERSION,
            schema_version=REL_SCHEMA_VERSION,
            model=model,
        )
        res = run_relations_pipeline(
            manuscript_id=manuscript_id, llm_client=llm, cache=cache, force=force
        )
        log.info(
            "%s · M2: %d escenas, %d cache hits",
            work.filename, res.scenes_processed, res.cache_hits,
        )

    if "m3" in work.layers:
        from backend.extraction.attributes.pipeline import run_attributes_pipeline

        cache = AttributesCache(
            prompt_version=ATTR_PROMPT_VERSION,
            schema_version=ATTR_SCHEMA_VERSION,
            model=model,
        )
        res = run_attributes_pipeline(
            manuscript_id=manuscript_id, llm_client=llm, cache=cache, force=force
        )
        log.info(
            "%s · M3: %d escenas, %d cache hits",
            work.filename, res.scenes_processed, res.cache_hits,
        )


def seed_all(force: bool = False) -> dict[str, str]:
    """Siembra las 4 obras del gate. Devuelve {filename: manuscript_id}."""
    from dotenv import load_dotenv

    load_dotenv()
    _use_frozen_cache()

    ids: dict[str, str] = {}
    for work in GATE_WORKS:
        mid = _ingest(work)
        _extract(work, mid, force)
        ids[work.filename] = mid
    return ids


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    p = argparse.ArgumentParser(description="Siembra el grafo para los gates de eval.")
    p.add_argument(
        "--force",
        action="store_true",
        help="Ignora la caché y re-extrae (CUESTA CUOTA LLM: 21 llamadas).",
    )
    args = p.parse_args()

    ids = seed_all(force=args.force)
    print(f"\n{'─' * 60}")
    for name, mid in ids.items():
        print(f"  {name:32s} {mid[:16]}…")
    print(f"  Caché LLM: {os.environ.get('LOOM_CACHE_DIR')}")
    print(f"{'─' * 60}\n")


if __name__ == "__main__":
    main()
