"""Métricas del eval de relaciones (spec FR-011/FR-012).

Detección de pares no ordenados + type accuracy, desglosadas por provenance.
El matching gold↔pred de personajes reusa el solapamiento de aliases de M1.
"""

from __future__ import annotations

from typing import Any

from eval.characters.metrics import F1Scores, _entities_match, _f1


def align_gold_to_pred(
    gold_chars: list[dict[str, Any]],
    pred_entities: list[dict[str, Any]],
) -> dict[str, str]:
    """gold_id → character_id (greedy: cada pred se empareja a lo sumo una vez)."""
    alignment: dict[str, str] = {}
    used: set[str] = set()
    for gold in gold_chars:
        for pred in pred_entities:
            cid = pred["character_id"]
            if cid not in used and _entities_match(gold, pred):
                alignment[gold["gold_id"]] = cid
                used.add(cid)
                break
    return alignment


def _pair_key(cid_a: str, cid_b: str) -> tuple[str, str]:
    return (cid_a, cid_b) if cid_a <= cid_b else (cid_b, cid_a)


def relation_metrics(
    gold_relations: list[dict[str, Any]],
    pred_relations: list[dict[str, Any]],
    alignment: dict[str, str],
) -> dict[str, Any]:
    """pair_detection y type_accuracy por bucket {extracted, inferred, all}."""
    # Mapa de pares gold (en espacio character_id) → gold rel
    gold_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for rel in gold_relations:
        cid_a, cid_b = alignment.get(rel["a"]), alignment.get(rel["b"])
        if cid_a is None or cid_b is None:
            continue  # miss garantizado: no alinea, cuenta en recall via g_in
        gold_by_pair[_pair_key(cid_a, cid_b)] = rel

    pred_pairs = {
        _pair_key(p["character_a_id"], p["character_b_id"]): p for p in pred_relations
    }

    buckets = ("extracted", "inferred", "all")
    detection: dict[str, dict[str, float]] = {}
    accuracy: dict[str, float | None] = {}

    for bucket in buckets:
        g_in = [
            r
            for r in gold_relations
            if bucket == "all" or r["provenance"] == bucket
        ]
        g_pairs_in = {
            pk: r
            for pk, r in gold_by_pair.items()
            if bucket == "all" or r["provenance"] == bucket
        }
        p_in = {
            pk: p
            for pk, p in pred_pairs.items()
            if bucket == "all" or p["provenance"] == bucket
        }

        matched = [pk for pk in g_pairs_in if pk in p_in]
        recall = len(matched) / len(g_in) if g_in else (1.0 if not p_in else 0.0)
        tp_pred = sum(1 for pk in p_in if pk in gold_by_pair)
        precision = tp_pred / len(p_in) if p_in else (1.0 if not g_in else 0.0)
        detection[bucket] = {
            "precision": precision,
            "recall": recall,
            "f1": _f1(precision, recall),
        }

        if matched:
            hits = sum(
                1
                for pk in matched
                if pred_pairs[pk]["rel_type"] == g_pairs_in[pk]["rel_type"]
            )
            accuracy[bucket] = hits / len(matched)
        else:
            accuracy[bucket] = None

    return {"pair_detection": detection, "type_accuracy": accuracy}


__all__ = ["F1Scores", "align_gold_to_pred", "relation_metrics"]
