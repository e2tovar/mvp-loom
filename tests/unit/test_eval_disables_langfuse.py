"""Aísla el eval harness de Langfuse (ADR-0003): mismo patrón que
_use_frozen_cache() ya aplica para LOOM_CACHE_DIR — setdefault, nunca pisa un
valor que el entorno ya trae."""

from __future__ import annotations

import os

from eval.seed import _use_frozen_cache


def test_use_frozen_cache_disables_langfuse_by_default(monkeypatch):
    monkeypatch.delenv("LOOM_DISABLE_LANGFUSE", raising=False)
    _use_frozen_cache()
    assert os.environ["LOOM_DISABLE_LANGFUSE"] == "1"


def test_use_frozen_cache_respects_existing_langfuse_flag(monkeypatch):
    monkeypatch.setenv("LOOM_DISABLE_LANGFUSE", "0")
    _use_frozen_cache()
    assert os.environ["LOOM_DISABLE_LANGFUSE"] == "0"
