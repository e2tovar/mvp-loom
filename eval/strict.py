"""Política de omisión de los gates de eval.

En local, un gate se omite si el grafo no tiene la extracción sembrada: extraer
cuesta cuota LLM y no queremos pagarla en cada corrida de tests. En CI esa misma
política es un agujero — la suite pasaría en verde sin haber medido nada.

`LOOM_EVAL_STRICT=1` invierte la política: cada motivo de omisión pasa a ser un
fallo. El CI lo activa; el sembrador (`eval/seed.py`) deja el grafo en el estado
que hace innecesaria la omisión.

Ver docs/known-issues.md → "M3 · Follow-ups", punto 4.
"""

from __future__ import annotations

import os
from typing import NoReturn

STRICT_ENV = "LOOM_EVAL_STRICT"


def is_strict() -> bool:
    """True si el modo estricto está activo (exactamente `LOOM_EVAL_STRICT=1`)."""
    return os.environ.get(STRICT_ENV) == "1"


def skip_or_fail(reason: str) -> NoReturn:
    """Omite el gate, o lo hace fallar si el modo estricto está activo."""
    import pytest

    if is_strict():
        pytest.fail(
            f"{reason}\n"
            f"[{STRICT_ENV}=1] En modo estricto un gate no puede omitirse: "
            f"siembra el grafo con `python -m eval.seed` y vuelve a ejecutar."
        )
    pytest.skip(reason)
