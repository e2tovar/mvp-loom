"""Runner del harness de evaluación de personajes (contracts/api.md CLI).

python -m eval.characters.runner [--work <obra>] [--compare]

Sin llamadas LLM: compara salida del grafo contra el golden dataset.
Escribe eval/results/characters-<obra>-<fecha>-<sha>.json.
Exit ≠ 0 si alguna métrica queda bajo umbral (SC-007).
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
GOLD_SUFFIX = ".characters.gold.json"


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def _load_gold(work: str) -> dict:
    path = FIXTURES_DIR / f"{work}{GOLD_SUFFIX}"
    if not path.exists():
        raise FileNotFoundError(f"Gold dataset no encontrado: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_system_output(manuscript_id: str) -> tuple[list[dict], list[list[str]]]:
    """Carga personajes y clusters de menciones del grafo Neo4j."""
    from dotenv import load_dotenv

    load_dotenv()
    from backend.graph import characters as char_graph
    from backend.graph.client import session as db_session

    with db_session() as sess:
        char_list = char_graph.get_characters_list(sess, manuscript_id)
        # Clusters de menciones: una lista de mention_ids por personaje
        clusters = []
        for c in char_list:
            detail = char_graph.get_character_detail(sess, manuscript_id, c["character_id"])
            if detail:
                cluster = [m["mention_id"] for m in detail.get("mentions", [])]
                if cluster:
                    clusters.append(cluster)
    return char_list, clusters


def _build_gold_clusters(gold: dict) -> tuple[list[dict], list[list[str]]]:
    """Construye clusters ficticios de gold (gold_id como pseudo-mention_id)."""
    gold_entities = gold["characters"]
    clusters = [[f"gold:{c['gold_id']}:{i}" for i in range(1)] for c in gold_entities]
    return gold_entities, clusters


def run_eval(work: str, manuscript_id: str | None = None) -> dict:
    """Ejecuta el harness para una obra. Devuelve el EvalResult."""
    from eval.characters.metrics import bcubed_f1, count_silent_bad_merges, detection_f1
    from eval.characters.thresholds import (
        DETECTION_F1,
        RESOLUTION_B3_F1,
        SILENT_BAD_MERGES,
    )

    gold = _load_gold(work)
    gold_entities = gold["characters"]

    mid = manuscript_id or work
    try:
        pred_entities, pred_clusters = _load_system_output(mid)
    except Exception as exc:
        print(f"[eval] No se pudo cargar la salida del sistema: {exc}", file=sys.stderr)
        print(
            "[eval] ¿Se ejecutó la extracción? (python -m backend.extraction.run)",
            file=sys.stderr,
        )
        sys.exit(1)

    # Para B-cubed gold usamos un cluster por entidad gold (simplificado: cada entidad = 1 mention)
    # Los clusters de pred se alinean a clusters de gold por alias matching (simplificado)
    # Para una eval completa se necesitan mention_ids compartidos; aquí usamos entity-level
    det = detection_f1(gold_entities, pred_entities)

    # B-cubed a nivel de entidades (proxy cuando no hay mention_ids de gold)
    gold_entity_clusters = [[c["gold_id"]] for c in gold_entities]
    pred_entity_clusters = [
        [f"pred:{p['character_id']}"] for p in pred_entities
    ]
    b3 = bcubed_f1(gold_entity_clusters, pred_entity_clusters)

    sbm = count_silent_bad_merges(gold_entities, pred_entities, [])

    passed = (
        det.f1 >= DETECTION_F1
        and b3.f1 >= RESOLUTION_B3_F1
        and sbm <= SILENT_BAD_MERGES
    )

    import os
    model = os.environ.get("LOOM_LLM_MODEL", "unknown")

    from backend.extraction.prompts import PROMPT_VERSION

    result = {
        "work": work,
        "run_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "prompt_version": PROMPT_VERSION,
        "model": model,
        "detection": {"precision": det.precision, "recall": det.recall, "f1": det.f1},
        "resolution_b3": {"precision": b3.precision, "recall": b3.recall, "f1": b3.f1},
        "silent_bad_merges": sbm,
        "thresholds": {
            "detection_f1": DETECTION_F1,
            "resolution_b3_f1": RESOLUTION_B3_F1,
            "silent_bad_merges": SILENT_BAD_MERGES,
        },
        "passed": passed,
    }
    return result


def _save_result(result: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    work = result["work"].replace("/", "-").replace(".", "-")
    date = datetime.now(UTC).strftime("%Y%m%d")
    sha = result.get("git_sha", "unknown")[:7]
    filename = f"characters-{work}-{date}-{sha}.json"
    path = RESULTS_DIR / filename
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _last_result(work: str) -> dict | None:
    pattern = f"characters-{work.replace('/', '-').replace('.', '-')}-*.json"
    files = sorted(RESULTS_DIR.glob(pattern))
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))


def _print_result(result: dict, compare: dict | None = None) -> None:
    gate = "✅ PASS" if result["passed"] else "❌ FAIL"
    print(f"\n{'─'*60}")
    print(f"  Obra       : {result['work']}")
    print(f"  Modelo     : {result['model']}")
    print(f"  Gate       : {gate}")
    det_f1 = result["detection"]["f1"]
    det_thr = result["thresholds"]["detection_f1"]
    b3_f1 = result["resolution_b3"]["f1"]
    b3_thr = result["thresholds"]["resolution_b3_f1"]
    sbm = result["silent_bad_merges"]
    sbm_thr = result["thresholds"]["silent_bad_merges"]
    print(f"  Detection  : F1={det_f1:.3f}  (≥{det_thr})")
    print(f"  B³ Resol.  : F1={b3_f1:.3f}  (≥{b3_thr})")
    print(f"  Silent err.: {sbm}  (≤{sbm_thr})")
    if compare:
        dd = result["detection"]["f1"] - compare.get("detection", {}).get("f1", 0)
        db = result["resolution_b3"]["f1"] - compare.get("resolution_b3", {}).get("f1", 0)
        print(f"  Δ Detection: {dd:+.3f}   Δ B³: {db:+.3f}  (vs {compare.get('run_at','?')[:10]})")
    print(f"{'─'*60}\n")


def main() -> None:
    p = argparse.ArgumentParser(description="Eval harness de personajes M1.")
    p.add_argument("--work", default="pride-and-prejudice.txt", help="Nombre de la obra (sin path)")
    p.add_argument("--manuscript-id", default=None, help="manuscript_id en Neo4j (default=work)")
    p.add_argument("--compare", action="store_true", help="Comparar con el último resultado")
    args = p.parse_args()

    result = run_eval(args.work, args.manuscript_id)
    path = _save_result(result)
    print(f"[eval] Resultado guardado en {path}")

    prev = _last_result(args.work) if args.compare else None
    _print_result(result, compare=prev)

    if not result["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
