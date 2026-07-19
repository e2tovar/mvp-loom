"""Métricas del eval de atributos (spec FR-010).

Detección de tripletas (personaje, key, value_norm), desglosada por clase de key
(static / stateful / all). El matching gold↔pred de personajes reusa la
alineación por aliases de M1/M2.
"""

from __future__ import annotations

from typing import Any

from eval.characters.metrics import _f1
from eval.relations.metrics import align_gold_to_pred  # reexport para el runner


def _triples_from_gold(
    gold_attrs: list[dict[str, Any]],
    alignment: dict[str, str],
    bucket: str,
) -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    for g in gold_attrs:
        if bucket != "all" and g["class"] != bucket:
            continue
        cid = alignment.get(g["character"])
        if cid is None:
            continue  # no alinea → miss garantizado (cuenta en recall vía total)
        out.add((cid, g["key"], g["value_norm"]))
    return out


def _triples_from_pred(
    pred_attrs: list[dict[str, Any]], bucket: str
) -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    for p in pred_attrs:
        if bucket != "all" and p["attr_class"] != bucket:
            continue
        out.add((p["character_id"], p["key"], p["value_norm"]))
    return out


def attribute_metrics(
    gold_attrs: list[dict[str, Any]],
    pred_attrs: list[dict[str, Any]],
    alignment: dict[str, str],
) -> dict[str, Any]:
    """triple_detection por bucket {static, stateful, all}."""
    detection: dict[str, dict[str, float]] = {}
    for bucket in ("static", "stateful", "all"):
        # gold_total incluye tripletas sin alineación (miss garantizado en recall)
        gold_total = sum(
            1 for g in gold_attrs if bucket == "all" or g["class"] == bucket
        )
        gold = _triples_from_gold(gold_attrs, alignment, bucket)
        pred = _triples_from_pred(pred_attrs, bucket)
        tp = len(gold & pred)
        precision = tp / len(pred) if pred else (1.0 if gold_total == 0 else 0.0)
        recall = tp / gold_total if gold_total else (1.0 if not pred else 0.0)
        detection[bucket] = {
            "precision": precision,
            "recall": recall,
            "f1": _f1(precision, recall),
        }
    return {"triple_detection": detection}


__all__ = ["align_gold_to_pred", "attribute_metrics"]
