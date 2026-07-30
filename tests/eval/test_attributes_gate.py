"""Gate de CI del eval de atributos (marker `eval`).

SKIP POLICY (idéntica a test_relations_gate.py):
  - Neo4j no disponible → skip.
  - Gold de atributos o de personajes ausente → skip (el runner alinea gold↔pred
    en el espacio de personajes, así que necesita ambos).
  - Extracción M1 o M3 no ejecutada para la obra → skip con instrucción.
FAILURE POLICY: falla solo si hay salida y el gate (`GATE_KEYS`) queda bajo umbral.
El diagnóstico de todas las keys (incluye `gender`/`age`) no bloquea — ver
`eval/attributes/thresholds.py::GATE_KEYS`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eval.strict import skip_or_fail

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "eval" / "fixtures"
ATTR_GOLD_SUFFIX = ".attributes.gold.json"
CHAR_GOLD_SUFFIX = ".characters.gold.json"
EVAL_WORKS = [
    "crafted-attributes.txt",
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
        from backend.graph import attributes as attr_graph
        from backend.graph import characters as char_graph
        from backend.graph.client import session as db_session

        with db_session() as sess:
            if checker == "m1":
                return char_graph.has_extraction(sess, manuscript_id)
            return attr_graph.has_attributes(sess, manuscript_id)
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.eval
@pytest.mark.parametrize("work", EVAL_WORKS)
def test_attributes_gate(work: str) -> None:
    if not _neo4j_available():
        skip_or_fail("Neo4j no disponible — docker compose up para el gate")
    for suffix in (ATTR_GOLD_SUFFIX, CHAR_GOLD_SUFFIX):
        if not (FIXTURES_DIR / f"{work}{suffix}").exists():
            skip_or_fail(f"Gold {suffix} no encontrado para {work}")

    mid = _manuscript_id(work)
    if not _has_layer(mid, "m1"):
        skip_or_fail(f"M1 sin ejecutar para '{work}': python -m backend.extraction.run {mid}")
    if not _has_layer(mid, "m3"):
        skip_or_fail(
            f"M3 sin ejecutar para '{work}': "
            f"python -m backend.extraction.attributes.run {mid}"
        )

    from eval.attributes.runner import run_eval

    result = run_eval(work, manuscript_id=mid)
    gate = result["gate_detection"]["all"]
    diag = result["triple_detection"]["all"]
    assert result["passed"], (
        f"Gate de atributos FAIL para '{work}':\n"
        f"  Gate F1 (keys {', '.join(result['gate_keys'])}) = {gate['f1']:.3f} "
        f"(≥ {result['thresholds']['triple_detection_f1']})\n"
        f"  Diagnóstico (todas las keys) F1 = {diag['f1']:.3f} — no bloqueante"
    )


@pytest.mark.parametrize("work", EVAL_WORKS)
def test_manuscript_id_resolves_to_content_hash(work: str) -> None:
    """El gate deriva el manuscript_id real (hash de contenido), no el filename."""
    mid = _manuscript_id(work)
    assert mid and mid != work


def test_gate_keys_are_a_subset_of_the_annotated_gold() -> None:
    """`GATE_KEYS` no puede referirse a keys que el gold no anota.

    Si una key del gate desaparece del gold, el gate mediría sobre menos tripletas
    sin que nada avise — el fallo silencioso que hace pasar un gate vacío.
    """
    import json

    from eval.attributes.thresholds import GATE_KEYS

    gold = json.loads(
        (FIXTURES_DIR / f"{EVAL_WORKS[0]}{ATTR_GOLD_SUFFIX}").read_text(encoding="utf-8")
    )
    annotated = {a["key"] for a in gold["attributes"]}
    missing = GATE_KEYS - annotated
    assert not missing, f"GATE_KEYS sin anotación en el gold: {sorted(missing)}"
