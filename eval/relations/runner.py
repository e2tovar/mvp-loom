"""Runner del eval de relaciones (spec 003, FR-011/012/013).

python -m eval.relations.runner [--work <obra>] [--manuscript-id ...] [--compare]

Sin llamadas LLM: compara el grafo contra los golds. Escribe
eval/results/relations-<obra>-<fecha>-<sha>.json. Exit ≠ 0 si el gate falla.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = EVAL_DIR / "results"
FIXTURES_DIR = EVAL_DIR / "fixtures"
REL_GOLD_SUFFIX = ".relations.gold.json"
CHAR_GOLD_SUFFIX = ".characters.gold.json"


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Gold no encontrado: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def run_eval(work: str, manuscript_id: str | None = None) -> dict:
    """Ejecuta el eval de relaciones para una obra. Devuelve el EvalResult."""
    from eval.relations.metrics import align_gold_to_pred, relation_metrics
    from eval.relations.thresholds import PAIR_DETECTION_F1_EXTRACTED, TYPE_ACCURACY

    rel_gold = _load_json(FIXTURES_DIR / f"{work}{REL_GOLD_SUFFIX}")
    char_gold = _load_json(FIXTURES_DIR / f"{work}{CHAR_GOLD_SUFFIX}")

    mid = manuscript_id or work
    from dotenv import load_dotenv

    load_dotenv()
    from backend.graph import characters as char_graph
    from backend.graph import relations as rel_graph
    from backend.graph.client import session as db_session

    try:
        with db_session() as sess:
            pred_entities = char_graph.get_characters_list(sess, mid)
            pred_entities = [
                c for c in pred_entities if c.get("entity_kind", "person") != "animal"
            ]
            pred_relations = rel_graph.get_relations_list(sess, mid)
        if not pred_entities:
            raise RuntimeError(f"Sin extracción M1 para manuscript_id={mid!r}")
        if not pred_relations:
            raise RuntimeError(f"Sin relaciones M2 para manuscript_id={mid!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"[eval] No se pudo cargar la salida del sistema: {exc}", file=sys.stderr)
        print(
            "[eval] ¿Se ejecutó M1 y M2? "
            "(backend.extraction.run + backend.extraction.relations.run)",
            file=sys.stderr,
        )
        sys.exit(1)

    alignment = align_gold_to_pred(char_gold["characters"], pred_entities)
    m = relation_metrics(rel_gold["relations"], pred_relations, alignment)

    det_e = m["pair_detection"]["extracted"]
    acc_e = m["type_accuracy"]["extracted"]
    passed = det_e["f1"] >= PAIR_DETECTION_F1_EXTRACTED and (
        acc_e is None or acc_e >= TYPE_ACCURACY
    )

    import os

    from backend.extraction.relations.prompts import PROMPT_VERSION

    return {
        "work": work,
        "run_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "prompt_version": PROMPT_VERSION,
        "model": os.environ.get("LOOM_LLM_MODEL", "unknown"),
        "pair_detection": m["pair_detection"],
        "type_accuracy": m["type_accuracy"],
        "thresholds": {
            "pair_detection_f1_extracted": PAIR_DETECTION_F1_EXTRACTED,
            "type_accuracy": TYPE_ACCURACY,
        },
        "passed": passed,
    }


def _save_result(result: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    work = result["work"].replace("/", "-").replace(".", "-")
    date = datetime.now(UTC).strftime("%Y%m%d")
    sha = result.get("git_sha", "unknown")[:7]
    path = RESULTS_DIR / f"relations-{work}-{date}-{sha}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _print_result(result: dict) -> None:
    gate = "✅ PASS" if result["passed"] else "❌ FAIL"
    det = result["pair_detection"]
    acc = result["type_accuracy"]
    thr = result["thresholds"]
    print(f"\n{'─'*60}")
    print(f"  Obra        : {result['work']}")
    print(f"  Modelo      : {result['model']}")
    print(f"  Gate        : {gate}  (solo métricas extracted)")
    print(
        f"  Pares extr. : F1={det['extracted']['f1']:.3f}  "
        f"(≥{thr['pair_detection_f1_extracted']})"
    )
    acc_e = acc["extracted"]
    acc_str = "n/a (sin pares acertados)" if acc_e is None else f"{acc_e:.3f}"
    print(f"  Tipo extr.  : {acc_str}  (≥{thr['type_accuracy']})")
    print(
        f"  Diagnóstico : inferred F1={det['inferred']['f1']:.3f} · "
        f"all F1={det['all']['f1']:.3f}"
    )
    print(f"{'─'*60}\n")


def main() -> None:
    p = argparse.ArgumentParser(description="Eval harness de relaciones M2.")
    p.add_argument("--work", default="pride-and-prejudice.txt")
    p.add_argument("--manuscript-id", default=None)
    args = p.parse_args()

    result = run_eval(args.work, args.manuscript_id)
    path = _save_result(result)
    print(f"[eval] Resultado guardado en {path}")
    _print_result(result)
    if not result["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
