"""Runner del eval de atributos (spec 004, FR-010/011/012).

python -m eval.attributes.runner [--work <obra>] [--manuscript-id ...]

Sin llamadas LLM: compara el grafo contra los golds. Escribe
eval/results/attributes-<obra>-<fecha>-<sha>.json. Exit ≠ 0 si el gate falla.
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
ATTR_GOLD_SUFFIX = ".attributes.gold.json"
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
    from eval.attributes.metrics import align_gold_to_pred, attribute_metrics
    from eval.attributes.thresholds import TRIPLE_DETECTION_F1

    attr_gold = _load_json(FIXTURES_DIR / f"{work}{ATTR_GOLD_SUFFIX}")
    char_gold = _load_json(FIXTURES_DIR / f"{work}{CHAR_GOLD_SUFFIX}")

    mid = manuscript_id or work
    from dotenv import load_dotenv

    load_dotenv()
    from backend.graph import attributes as attr_graph
    from backend.graph import characters as char_graph
    from backend.graph.client import session as db_session

    try:
        with db_session() as sess:
            pred_entities = char_graph.get_characters_list(sess, mid)
            pred_entities = [
                c for c in pred_entities if c.get("entity_kind", "person") != "animal"
            ]
            pred_attrs = attr_graph.get_attributes_list(sess, mid)
        if not pred_entities:
            raise RuntimeError(f"Sin extracción M1 para manuscript_id={mid!r}")
        if not pred_attrs:
            raise RuntimeError(f"Sin atributos M3 para manuscript_id={mid!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"[eval] No se pudo cargar la salida del sistema: {exc}", file=sys.stderr)
        print("[eval] ¿Se ejecutó M1 y M3?", file=sys.stderr)
        sys.exit(1)

    alignment = align_gold_to_pred(char_gold["characters"], pred_entities)
    m = attribute_metrics(attr_gold["attributes"], pred_attrs, alignment)

    f1_all = m["triple_detection"]["all"]["f1"]
    passed = f1_all >= TRIPLE_DETECTION_F1

    import os

    from backend.extraction.attributes.prompts import PROMPT_VERSION

    return {
        "work": work,
        "run_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "prompt_version": PROMPT_VERSION,
        "model": os.environ.get("LOOM_LLM_MODEL", "unknown"),
        "triple_detection": m["triple_detection"],
        "thresholds": {"triple_detection_f1": TRIPLE_DETECTION_F1},
        "passed": passed,
    }


def _save_result(result: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    work = result["work"].replace("/", "-").replace(".", "-")
    date = datetime.now(UTC).strftime("%Y%m%d")
    sha = result.get("git_sha", "unknown")[:7]
    path = RESULTS_DIR / f"attributes-{work}-{date}-{sha}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _print_result(result: dict) -> None:
    gate = "✅ PASS" if result["passed"] else "❌ FAIL"
    det = result["triple_detection"]
    thr = result["thresholds"]
    print(f"\n{'─'*60}")
    print(f"  Obra        : {result['work']}")
    print(f"  Modelo      : {result['model']}")
    print(f"  Gate        : {gate}")
    print(f"  Tripletas   : F1={det['all']['f1']:.3f}  (≥{thr['triple_detection_f1']})")
    print(f"  Por clase   : static F1={det['static']['f1']:.3f} · "
          f"stateful F1={det['stateful']['f1']:.3f}")
    print(f"{'─'*60}\n")


def main() -> None:
    p = argparse.ArgumentParser(description="Eval harness de atributos M3.")
    p.add_argument("--work", default="crafted-attributes.txt")
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
