"""Gate de CI del eval harness de personajes (T026, marker `eval`).

Ejecuta el harness sobre las obras de fixtures con extracción presente en el grafo.
Skip claro si no hay extracción (documentado abajo).

SKIP POLICY:
  Este test se omite automáticamente si:
  - Neo4j no está disponible.
  - No se ha ejecutado la extracción para la obra (`python -m backend.extraction.run`).
  Ambos casos producen un skip con mensaje claro (no un fallo).

FAILURE POLICY:
  El test falla (exit ≠ 0) únicamente si la extracción existe y las métricas
  quedan bajo los umbrales definidos en `eval/characters/thresholds.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "eval" / "fixtures"
GOLD_SUFFIX = ".characters.gold.json"
EVAL_WORKS = [
    "crafted-three-chapters.txt",
    "crafted-two-chapters.epub",
]


def _neo4j_available() -> bool:
    try:
        from backend.graph import client

        client.get_driver().verify_connectivity()
        return True
    except Exception:
        return False


def _has_extraction(manuscript_id: str) -> bool:
    try:
        from backend.graph import characters as char_graph
        from backend.graph.client import session as db_session

        with db_session() as sess:
            return char_graph.has_extraction(sess, manuscript_id)
    except Exception:
        return False


@pytest.mark.eval
@pytest.mark.parametrize("work", EVAL_WORKS)
def test_characters_gate(work: str) -> None:
    """Gate: métricas ≥ umbrales para la obra `work`."""
    if not _neo4j_available():
        pytest.skip("Neo4j no disponible — levanta docker compose up para el gate")

    gold_path = FIXTURES_DIR / f"{work}{GOLD_SUFFIX}"
    if not gold_path.exists():
        pytest.skip(f"Gold dataset no encontrado: {gold_path}")

    manuscript_id = work
    if not _has_extraction(manuscript_id):
        pytest.skip(
            f"Extracción no ejecutada para '{work}'. "
            f"Ejecuta: python -m backend.extraction.run {manuscript_id}"
        )

    from eval.characters.runner import run_eval

    result = run_eval(work, manuscript_id=manuscript_id)

    assert result["passed"], (
        f"Gate FAIL para '{work}':\n"
        f"  Detection F1 = {result['detection']['f1']:.3f} "
        f"(umbral ≥ {result['thresholds']['detection_f1']})\n"
        f"  B³ F1 = {result['resolution_b3']['f1']:.3f} "
        f"(umbral ≥ {result['thresholds']['resolution_b3_f1']})\n"
        f"  Silent bad merges = {result['silent_bad_merges']} "
        f"(umbral ≤ {result['thresholds']['silent_bad_merges']})"
    )
