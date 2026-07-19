"""Umbrales versionados del eval de atributos (spec SC-001).

Para recalibrar: cambiar el valor + comentario con fecha, métrica real y obra.
"""

from __future__ import annotations

# SC-001: F1 de detección de tripletas (personaje, key, valor) ≥ 0.90 (gate crafted)
TRIPLE_DETECTION_F1: float = 0.90
