"""Umbrales versionados del eval de relaciones (spec SC-001/SC-002).

Para recalibrar: cambiar el valor + comentario con fecha, métrica real y obra.
"""

from __future__ import annotations

# SC-001: F1 de detección de pares extracted ≥ 0.90 (gate, obras crafted)
PAIR_DETECTION_F1_EXTRACTED: float = 0.90

# SC-002: accuracy de tipo sobre pares acertados ≥ 0.90 (gate, obras crafted)
TYPE_ACCURACY: float = 0.90
