"""Aísla el eval harness de Langfuse (ADR-0003): _use_frozen_cache() fija
LOOM_DISABLE_LANGFUSE=1 de forma dura, sin importar qué haya en el entorno — el
aislamiento es obligatorio, no opcional, y no tiene escape hatch. (LOOM_CACHE_DIR
sí sigue siendo setdefault: ese sí es un valor que el entorno puede legítimamente
sobreescribir.)"""

from __future__ import annotations

import os

from eval.seed import _use_frozen_cache


def test_use_frozen_cache_disables_langfuse_by_default(monkeypatch):
    monkeypatch.delenv("LOOM_DISABLE_LANGFUSE", raising=False)
    _use_frozen_cache()
    assert os.environ["LOOM_DISABLE_LANGFUSE"] == "1"


def test_use_frozen_cache_overrides_existing_langfuse_flag(monkeypatch):
    """Un LOOM_DISABLE_LANGFUSE=0 preexistente NO sobrevive: sin escape hatch."""
    monkeypatch.setenv("LOOM_DISABLE_LANGFUSE", "0")
    _use_frozen_cache()
    assert os.environ["LOOM_DISABLE_LANGFUSE"] == "1"
