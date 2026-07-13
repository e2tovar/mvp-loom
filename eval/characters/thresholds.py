"""Umbrales versionados del eval harness de M1 (spec Assumptions, SC-001/002/003).

Para recalibrar: cambiar el valor + añadir una línea de comentario con la fecha,
la métrica real que motivó el cambio y la obra de referencia.
"""

from __future__ import annotations

# SC-001: F1 de detección de entidades ≥ 0.90
DETECTION_F1: float = 0.90

# SC-002: B-cubed F1 de resolución ≥ 0.85
RESOLUTION_B3_F1: float = 0.85

# SC-003: cero fusiones silenciosas erróneas
SILENT_BAD_MERGES: int = 0
