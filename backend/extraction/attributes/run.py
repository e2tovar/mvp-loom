# backend/extraction/attributes/run.py
"""CLI de atributos: python -m backend.extraction.attributes.run <manuscript_id> [--force].

Exit codes:
  0 — éxito
  1 — error de configuración / manuscrito no encontrado / M1 sin ejecutar
  2 — error durante la extracción
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("attributes.run")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Extrae atributos de personaje (requiere capa M1)."
    )
    p.add_argument("manuscript_id", help="Id del manuscrito (ej. sha256-prefix)")
    p.add_argument("--force", action="store_true",
                   help="Ignora la cache; re-extrae todas las escenas.")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    from backend.core.errors import (
        LLMUnavailableError,
        ManuscriptNotFoundError,
        NotExtractedError,
    )
    from backend.extraction.attributes.pipeline import run_attributes_pipeline
    from backend.llm.litellm_client import LiteLLMClient

    try:
        llm_client = LiteLLMClient()
    except LLMUnavailableError as exc:
        log.error("LLM no configurado: %s", exc)
        sys.exit(1)

    import os

    from backend.extraction.attributes.prompts import PROMPT_VERSION
    from backend.extraction.attributes.schemas import SCHEMA_VERSION
    from backend.llm.cache import AttributesCache

    model = os.environ.get("LOOM_LLM_MODEL", "unknown")
    cache = AttributesCache(
        prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION, model=model,
    )

    log.info("Iniciando atributos de '%s' (force=%s)", args.manuscript_id, args.force)
    t0 = time.monotonic()

    try:
        result = run_attributes_pipeline(
            manuscript_id=args.manuscript_id, llm_client=llm_client,
            cache=cache, force=args.force,
        )
    except (ManuscriptNotFoundError, NotExtractedError) as exc:
        log.error("%s", exc)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        log.exception("Error durante la extracción de atributos: %s", exc)
        sys.exit(2)

    elapsed = time.monotonic() - t0
    print(
        f"\n{'─'*60}\n"
        f"  Atributos completados en {elapsed:.1f}s\n"
        f"  Escenas procesadas : {result.scenes_processed}"
        f" (skip: {result.scenes_skipped}, fail: {result.scenes_failed})\n"
        f"  Cache hits         : {result.cache_hits}\n"
        f"  Evidencias escritas: {result.evidences_written}\n"
        f"  Nodos Attribute    : {result.attributes_written}\n"
        f"{'─'*60}"
    )


if __name__ == "__main__":
    main()
