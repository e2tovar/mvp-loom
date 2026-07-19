"""Umbrales versionados del eval de atributos (spec SC-001).

Para recalibrar: cambiar el valor + comentario con fecha, métrica real y obra.
"""

from __future__ import annotations

# SC-001: F1 de detección de tripletas (personaje, key, valor) ≥ 0.90 (gate crafted)
TRIPLE_DETECTION_F1: float = 0.90

# Keys que BLOQUEAN el gate: los que el modelo extrae con fiabilidad medida.
# Patrón M2 (el gate solo mira `extracted`): `gender` y `age` se miden como
# diagnóstico NO bloqueante y quedan fuera del gate.
#   · gender: el modelo no lo enuncia desde nombres/pronombres (recall 0 medido
#     el 2026-07-19 sobre crafted-attributes con openai/kimi-k2.5).
#   · age: vago y ambiguo por diálogo ("Tienes cuarenta años…") — Open Question #2
#     de la spec; el modelo lo mal-atribuye e infiere de adjetivos ("viejo").
# Recalibrar = mover un key aquí + comentario con fecha/métrica.
GATE_KEYS: frozenset[str] = frozenset(
    {"eye_color", "hair", "height", "scar", "status"}
)
