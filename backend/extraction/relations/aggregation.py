"""Agregación determinista de evidencias por par → RELATES_TO (spec FR-004/FR-005).

Sin LLM: recomputable desde las evidencias en cualquier momento. Los pesos y el
umbral son la política de la spec; recalibrar = cambiar aquí + registrar por qué.
"""

from __future__ import annotations

from typing import Any

#: Umbral de escritura (FR-005): confianza agregada por debajo → sin arista.
WRITE_THRESHOLD: float = 0.5

#: Peso de una evidencia extracted vs inferred al elegir el tipo dominante.
_PROVENANCE_WEIGHT = {"extracted": 2, "inferred": 1}


def aggregate_pair(evidences: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Consolida las evidencias de UN par en la relación agregada, o None.

    Precondición: todas las evidencias comparten el mismo par canónico.
    """
    if not evidences:
        return None

    # 1. Tipo ganador por peso; empate → extracted más tardía; si no, más tardía.
    weights: dict[str, int] = {}
    for ev in evidences:
        weights[ev["rel_type"]] = (
            weights.get(ev["rel_type"], 0) + _PROVENANCE_WEIGHT[ev["provenance"]]
        )
    max_weight = max(weights.values())
    tied = {t for t, w in weights.items() if w == max_weight}
    if len(tied) == 1:
        winner = tied.pop()
    else:
        tied_evs = [ev for ev in evidences if ev["rel_type"] in tied]
        extracted = [ev for ev in tied_evs if ev["provenance"] == "extracted"]
        pool = extracted or tied_evs
        winner = max(pool, key=lambda ev: ev["narrative_order"])["rel_type"]

    winning = [ev for ev in evidences if ev["rel_type"] == winner]

    # 2-4. Descriptor, roles y confianza del tipo ganador.
    best = max(winning, key=lambda ev: ev["confidence"])
    role_a, role_b = _consistent_roles(winning)
    confidence = best["confidence"]
    if confidence < WRITE_THRESHOLD:
        return None

    first = min(evidences, key=lambda ev: ev["narrative_order"])
    provenance = (
        "extracted"
        if any(ev["provenance"] == "extracted" for ev in winning)
        else "inferred"
    )

    return {
        "character_a_id": evidences[0]["character_a_id"],
        "character_b_id": evidences[0]["character_b_id"],
        "rel_type": winner,
        "descriptor": best["descriptor"],
        "role_a": role_a,
        "role_b": role_b,
        "provenance": provenance,
        "confidence": confidence,
        "evidence_count": len(evidences),
        "first_evidence_id": first["evidence_id"],
    }


def _consistent_roles(
    winning: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    """Primeros roles no nulos en orden narrativo; conflicto → (None, None)."""
    role_a: str | None = None
    role_b: str | None = None
    for ev in sorted(winning, key=lambda e: e["narrative_order"]):
        for key, current in (("role_a", role_a), ("role_b", role_b)):
            value = ev.get(key)
            if value is None:
                continue
            if current is None:
                if key == "role_a":
                    role_a = value
                else:
                    role_b = value
            elif current != value:
                return None, None
    return role_a, role_b
