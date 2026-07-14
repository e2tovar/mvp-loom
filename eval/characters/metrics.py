"""Métricas de evaluación de extracción de personajes (research R4).

- Detection: precision/recall/F1 de entidades (matching por solapamiento de aliases).
- Resolution: B-cubed precision/recall/F1 sobre menciones.
- silent_bad_merges: pares del gold que se fusionaron sin pasar por la cola humana.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass
class F1Scores:
    precision: float
    recall: float
    f1: float


# ── Detection: F1 de entidades ────────────────────────────────────────────────


def _fold(text: str) -> str:
    """casefold + eliminación de acentos (NFKD) — 'Nicolás' == 'nicolas'."""
    nfkd = unicodedata.normalize("NFKD", text)
    return nfkd.encode("ascii", "ignore").decode("ascii").casefold().strip()


def _aliases_set(entity: dict) -> set[str]:
    """Conjunto normalizado (case+accent-fold) de names + aliases de una entidad."""
    names = {_fold(entity["canonical_name"])}
    for a in entity.get("aliases", []):
        names.add(_fold(a))
    return names


def _entities_match(gold: dict, pred: dict) -> bool:
    """Dos entidades coinciden si sus alias sets se solapan."""
    return bool(_aliases_set(gold) & _aliases_set(pred))


def detection_f1(
    gold_entities: list[dict],
    pred_entities: list[dict],
) -> F1Scores:
    """F1 de detección de entidades.

    Un `pred` se considera True Positive si hay al menos un `gold` con solapamiento
    de alias (greedy matching: cada gold se empareja a lo sumo una vez).
    """
    if not gold_entities and not pred_entities:
        return F1Scores(1.0, 1.0, 1.0)
    if not pred_entities:
        return F1Scores(0.0, 0.0, 0.0)
    if not gold_entities:
        return F1Scores(0.0, 0.0, 0.0)

    matched_gold: set[int] = set()
    tp = 0
    for pred in pred_entities:
        for gi, gold in enumerate(gold_entities):
            if gi not in matched_gold and _entities_match(gold, pred):
                tp += 1
                matched_gold.add(gi)
                break

    precision = tp / len(pred_entities)
    recall = tp / len(gold_entities)
    f1 = _f1(precision, recall)
    return F1Scores(precision=precision, recall=recall, f1=f1)


# ── Resolution: B-cubed F1 sobre menciones ───────────────────────────────────

def bcubed_f1(
    gold_clusters: list[list[str]],
    pred_clusters: list[list[str]],
) -> F1Scores:
    """B-cubed precision/recall/F1.

    Args:
        gold_clusters: Lista de grupos gold; cada grupo es una lista de mention_ids.
        pred_clusters: Lista de grupos predichos.

    Cada mention_id debe aparecer en exactamente un cluster.
    """
    if not gold_clusters and not pred_clusters:
        return F1Scores(1.0, 1.0, 1.0)
    if not pred_clusters or not gold_clusters:
        return F1Scores(0.0, 0.0, 0.0)

    # Mapas mention_id → cluster_id
    gold_map: dict[str, int] = {}
    for ci, cluster in enumerate(gold_clusters):
        for m in cluster:
            gold_map[m] = ci

    pred_map: dict[str, int] = {}
    for ci, cluster in enumerate(pred_clusters):
        for m in cluster:
            pred_map[m] = ci

    all_mentions = set(gold_map) | set(pred_map)
    if not all_mentions:
        return F1Scores(1.0, 1.0, 1.0)

    # Tamaños de clusters para eficiencia
    gold_sizes: dict[int, int] = {}
    for cid in gold_map.values():
        gold_sizes[cid] = gold_sizes.get(cid, 0) + 1

    pred_sizes: dict[int, int] = {}
    for cid in pred_map.values():
        pred_sizes[cid] = pred_sizes.get(cid, 0) + 1

    total_prec = 0.0
    total_rec = 0.0
    n = 0

    for m in all_mentions:
        if m not in gold_map or m not in pred_map:
            # Si solo aparece en uno de los dos conjuntos
            total_prec += 0.0
            total_rec += 0.0
            n += 1
            continue

        gc = gold_map[m]
        pc = pred_map[m]

        # Menciones en el mismo pred cluster que también están en el mismo gold cluster
        overlap = sum(
            1 for other in pred_clusters[pc]
            if gold_map.get(other) == gc
        )
        prec_m = overlap / pred_sizes[pc]
        rec_m = overlap / gold_sizes[gc]
        total_prec += prec_m
        total_rec += rec_m
        n += 1

    if n == 0:
        return F1Scores(0.0, 0.0, 0.0)

    precision = total_prec / n
    recall = total_rec / n
    f1 = _f1(precision, recall)
    return F1Scores(precision=precision, recall=recall, f1=f1)


# ── Silent bad merges ─────────────────────────────────────────────────────────


def count_silent_bad_merges(
    gold_entities: list[dict],
    pred_entities: list[dict],
    candidate_pairs: list[tuple[dict, dict]],
) -> int:
    """Pares del gold distintos que aparecen fusionados en pred sin candidate.

    Un "silent bad merge" es: dos gold_ids que el sistema colapsó en una sola
    entidad predicha pero sin MergeCandidate registrado para ese par.

    Args:
        candidate_pairs: Pares (char_a, char_b) de MergeCandidate del grafo
            (cualquier status); cada elemento es un dict de entidad con
            `canonical_name` y `aliases`. El matching usa solapamiento de
            aliases, igual que la detección.
    """
    bad = 0
    for i, ga in enumerate(gold_entities):
        for gb in gold_entities[i + 1 :]:
            if _entities_match(ga, gb):
                # Son entidades distintas en gold pero podrían coincidir en pred
                continue
            # Buscar si pred fusionó ga y gb en la misma entidad
            pred_a = next((p for p in pred_entities if _entities_match(ga, p)), None)
            pred_b = next((p for p in pred_entities if _entities_match(gb, p)), None)
            if pred_a is None or pred_b is None:
                continue
            if pred_a["canonical_name"] == pred_b["canonical_name"]:
                # Están fusionadas — ¿existe un candidate para el par?
                pair_known = any(
                    (_entities_match(ga, ca) and _entities_match(gb, cb))
                    or (_entities_match(ga, cb) and _entities_match(gb, ca))
                    for ca, cb in candidate_pairs
                )
                if not pair_known:
                    bad += 1
    return bad


# ── Helpers ───────────────────────────────────────────────────────────────────


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)
