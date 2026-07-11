"""Alineación de menciones gold↔pred para B-cubed (cierra docs/known-issues.md M1).

El espacio compartido de IDs es la clave `"c{cap}/s{escena}::{surface_normalizada}"`.
Funciona porque el pipeline solo escribe la primera ocurrencia de cada surface por
escena (pipeline._find_offset) y mention_id es determinista: (coordenada de escena,
surface) identifica unívocamente una mención predicha.

Las menciones `pronoun_resolved` se excluyen del espacio B³: el gold solo anota
menciones nombradas (name/alias/title/description) — ver eval/fixtures/README.md.
"""

from __future__ import annotations

_EXCLUDED_KINDS = {"pronoun_resolved"}


def mention_key(scene_coord: str, surface: str) -> str:
    """Clave compartida gold↔pred de una mención."""
    return f"{scene_coord}::{surface.casefold().strip()}"


def gold_mention_clusters(gold: dict) -> list[list[str]] | None:
    """Clusters gold de menciones; None si el gold no está anotado a nivel de mención.

    Raises:
        ValueError: si solo algunos personajes tienen `mentions` (gold inconsistente).
    """
    chars = gold["characters"]
    annotated = [c for c in chars if "mentions" in c]
    if not annotated:
        return None
    if len(annotated) != len(chars):
        missing = [c["gold_id"] for c in chars if "mentions" not in c]
        raise ValueError(f"Gold inconsistente: personajes sin 'mentions': {missing}")

    clusters: list[list[str]] = []
    for c in chars:
        cluster: list[str] = []
        for m in c["mentions"]:
            key = mention_key(m["scene"], m["surface"])
            if key not in cluster:
                cluster.append(key)
        if cluster:
            clusters.append(cluster)
    return clusters


def pred_mention_clusters(
    characters_mentions: list[list[dict]],
    scene_coords: dict[str, str],
) -> list[list[str]]:
    """Clusters pred en el mismo espacio de claves que el gold.

    Args:
        characters_mentions: por personaje, sus menciones del grafo
            (dicts con `scene_id`, `surface`, `kind`).
        scene_coords: mapa scene_id → coordenada "c{n}/s{m}".
    """
    clusters: list[list[str]] = []
    for mentions in characters_mentions:
        cluster: list[str] = []
        for m in mentions:
            if m.get("kind") in _EXCLUDED_KINDS:
                continue
            coord = scene_coords.get(m["scene_id"])
            if coord is None:
                continue
            key = mention_key(coord, m["surface"])
            if key not in cluster:
                cluster.append(key)
        if cluster:
            clusters.append(cluster)
    return clusters
