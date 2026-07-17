"""Gate de CI del eval de relaciones (marker `eval`).

SKIP POLICY (idéntica a test_characters_gate.py):
  - Neo4j no disponible → skip.
  - Extracción M1 o M2 no ejecutada para la obra → skip con instrucción.
FAILURE POLICY: falla solo si hay salida y las métricas extracted < umbral.
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "eval" / "fixtures"
EVAL_WORKS = [
    "crafted-relations.txt",
]


def _neo4j_available() -> bool:
    try:
        from backend.graph import client

        client.get_driver().verify_connectivity()
        return True
    except Exception:  # noqa: BLE001
        return False


def _manuscript_id(work: str) -> str:
    from backend.ingest.pipeline import parse_manuscript

    fmt = Path(work).suffix.lstrip(".")
    return parse_manuscript(FIXTURES_DIR / work, fmt).manuscript_id  # type: ignore[arg-type]


def _has_layer(manuscript_id: str, checker: str) -> bool:
    try:
        from backend.graph import characters as char_graph
        from backend.graph import relations as rel_graph
        from backend.graph.client import session as db_session

        with db_session() as sess:
            if checker == "m1":
                return char_graph.has_extraction(sess, manuscript_id)
            return rel_graph.has_relations(sess, manuscript_id)
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.eval
@pytest.mark.parametrize("work", EVAL_WORKS)
def test_relations_gate(work: str) -> None:
    if not _neo4j_available():
        pytest.skip("Neo4j no disponible — docker compose up para el gate")
    if not (FIXTURES_DIR / f"{work}.relations.gold.json").exists():
        pytest.skip(f"Gold de relaciones no encontrado para {work}")

    mid = _manuscript_id(work)
    if not _has_layer(mid, "m1"):
        pytest.skip(f"M1 sin ejecutar para '{work}': python -m backend.extraction.run {mid}")
    if not _has_layer(mid, "m2"):
        pytest.skip(
            f"M2 sin ejecutar para '{work}': python -m backend.extraction.relations.run {mid}"
        )

    from eval.relations.runner import run_eval

    result = run_eval(work, manuscript_id=mid)
    assert result["passed"], (
        f"Gate de relaciones FAIL para '{work}':\n"
        f"  Pares extracted F1 = {result['pair_detection']['extracted']['f1']:.3f} "
        f"(≥ {result['thresholds']['pair_detection_f1_extracted']})\n"
        f"  Type accuracy = {result['type_accuracy']['extracted']} "
        f"(≥ {result['thresholds']['type_accuracy']})"
    )
