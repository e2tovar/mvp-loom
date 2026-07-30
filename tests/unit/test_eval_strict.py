"""El modo estricto convierte los skips de los gates en fallos.

En local un gate se omite si no hay extracción sembrada (extraer cuesta cuota
LLM). En CI eso es inaceptable: la suite pasaría en verde sin haber medido nada.
LOOM_EVAL_STRICT=1 invierte la política.
"""

from __future__ import annotations

import pytest

from eval.strict import is_strict, skip_or_fail


def test_default_is_lenient_and_skips(monkeypatch):
    monkeypatch.delenv("LOOM_EVAL_STRICT", raising=False)
    assert is_strict() is False
    with pytest.raises(pytest.skip.Exception) as exc:
        skip_or_fail("M1 sin ejecutar")
    assert "M1 sin ejecutar" in str(exc.value)


def test_strict_mode_fails_instead_of_skipping(monkeypatch):
    monkeypatch.setenv("LOOM_EVAL_STRICT", "1")
    assert is_strict() is True
    with pytest.raises(pytest.fail.Exception) as exc:
        skip_or_fail("M1 sin ejecutar")
    msg = str(exc.value)
    assert "M1 sin ejecutar" in msg
    assert "LOOM_EVAL_STRICT" in msg, "el fallo debe decir por qué no se omitió"


@pytest.mark.parametrize("value", ["0", "", "false", "no", "true", "yes"])
def test_only_the_exact_string_1_enables_strict(monkeypatch, value):
    """Sin adivinar booleanos: solo "1" activa. Un typo no debe apagar el gate
    en silencio ni activarlo por accidente."""
    monkeypatch.setenv("LOOM_EVAL_STRICT", value)
    assert is_strict() is False
    with pytest.raises(pytest.skip.Exception):
        skip_or_fail("cualquier motivo")
