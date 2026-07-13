"""CLI de extracción: python -m backend.extraction.run <manuscript_id> [--force].

Exit codes:
  0 — éxito
  1 — error de configuración / manuscrito no encontrado
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
log = logging.getLogger("extraction.run")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Extrae personajes de un manuscrito ya ingerido (M0)."
    )
    p.add_argument("manuscript_id", help="Id del manuscrito (ej. sha256-prefix)")
    p.add_argument(
        "--force",
        action="store_true",
        help="Ignora la cache; re-extrae todas las escenas.",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    manuscript_id: str = args.manuscript_id
    force: bool = args.force

    from backend.core.errors import LLMUnavailableError, ManuscriptNotFoundError
    from backend.extraction.pipeline import run_pipeline
    from backend.llm.litellm_client import LiteLLMClient

    try:
        llm_client = LiteLLMClient()
    except LLMUnavailableError as exc:
        log.error("LLM no configurado: %s", exc)
        sys.exit(1)

    import os

    from backend.extraction.prompts import PROMPT_VERSION
    from backend.extraction.schemas import SCHEMA_VERSION
    from backend.llm.cache import ExtractionCache

    model = os.environ.get("LOOM_LLM_MODEL", "unknown")
    cache = ExtractionCache(
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        model=model,
    )

    log.info("Iniciando extracción de '%s' (force=%s)", manuscript_id, force)
    t0 = time.monotonic()

    try:
        result = run_pipeline(
            manuscript_id=manuscript_id,
            llm_client=llm_client,
            cache=cache,
            force=force,
        )
    except ManuscriptNotFoundError as exc:
        log.error("Manuscrito no encontrado: %s", exc)
        sys.exit(1)
    except Exception as exc:
        log.exception("Error durante la extracción: %s", exc)
        sys.exit(2)

    elapsed = time.monotonic() - t0
    print(
        f"\n{'─'*60}\n"
        f"  Extracción completada en {elapsed:.1f}s\n"
        f"  Escenas procesadas : {result.scenes_processed}\n"
        f"  Personajes únicos  : {result.total_characters}\n"
        f"  Menciones escritas : {result.total_mentions}\n"
        f"  Candidatos revisión: {result.total_merge_candidates}\n"
        f"{'─'*60}"
    )


if __name__ == "__main__":
    main()
