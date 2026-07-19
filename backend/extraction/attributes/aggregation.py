"""Agregación determinista de evidencias → nodos Attribute (spec FR-005).

Sin LLM: recomputable desde las evidencias. A DIFERENCIA de M2 (que colapsa a un
tipo dominante), aquí NO se colapsa: cada value_norm distinto de un (personaje,
key) produce su propio nodo. Esa multiplicidad ES la señal de continuidad
(SC-004). No hay umbral de escritura: se escribe siempre y la confianza queda
como propiedad, para no ocultar un posible gazapo (Open Question #4 resuelta).
"""

from __future__ import annotations

from typing import Any

from backend.extraction.attributes.schemas import key_class


def aggregate_character_attributes(
    evidences: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Agrupa por (character_id, key, value_norm) SIN colapsar valores distintos."""
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for ev in evidences:
        groups.setdefault(
            (ev["character_id"], ev["key"], ev["value_norm"]), []
        ).append(ev)

    nodes: list[dict[str, Any]] = []
    for (cid, key, value_norm), evs in groups.items():
        first = min(evs, key=lambda e: e["narrative_order"])
        best = max(evs, key=lambda e: e["confidence"])
        nodes.append(
            {
                "character_id": cid,
                "key": key,
                "value_norm": value_norm,
                "attr_class": key_class(key),
                "confidence": best["confidence"],
                "evidence_count": len(evs),
                "first_evidence_id": first["evidence_id"],
            }
        )
    return nodes
