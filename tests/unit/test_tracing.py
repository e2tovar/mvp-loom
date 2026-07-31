"""Tests unitarios de la puerta de tracing Langfuse (ADR-0003).

Sin red, sin depender de que langfuse esté realmente configurado: se simula
vía sys.modules cuando hace falta y se bloquea el import cuando se prueba el
modo no-op.
"""

from __future__ import annotations

import builtins
import sys
import types

from backend.observability.tracing import traced


def test_traced_is_noop_when_disabled(monkeypatch):
    monkeypatch.setenv("LOOM_DISABLE_LANGFUSE", "1")
    calls = []

    @traced("test.op")
    def fn(x):
        calls.append(x)
        return x * 2

    assert fn(3) == 6
    assert calls == [3]


def test_traced_does_not_import_langfuse_when_disabled(monkeypatch):
    monkeypatch.setenv("LOOM_DISABLE_LANGFUSE", "1")
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "langfuse":
            raise AssertionError("no debería importar langfuse con el flag activo")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    @traced("test.op")
    def fn():
        return 1

    assert fn() == 1


def test_traced_is_noop_when_not_configured(monkeypatch):
    monkeypatch.delenv("LOOM_DISABLE_LANGFUSE", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    @traced("test.op")
    def fn():
        return "ok"

    assert fn() == "ok"


def test_traced_wraps_with_langfuse_observe_when_enabled(monkeypatch):
    monkeypatch.delenv("LOOM_DISABLE_LANGFUSE", raising=False)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    observe_kwargs = []

    def fake_observe(**kwargs):
        def decorator(func):
            observe_kwargs.append(kwargs)
            return func

        return decorator

    fake_module = types.ModuleType("langfuse")
    fake_module.observe = fake_observe
    monkeypatch.setitem(sys.modules, "langfuse", fake_module)

    @traced("test.op")
    def fn(x):
        return x + 1

    assert fn(1) == 2
    assert [kw["name"] for kw in observe_kwargs] == ["test.op"]


def test_traced_disables_input_capture(monkeypatch):
    """capture_input=False es obligatorio: la captura por defecto serializaría el
    `llm_client` que reciben las pipelines, cuyo __dict__ expone `_api_key`."""
    monkeypatch.delenv("LOOM_DISABLE_LANGFUSE", raising=False)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    observe_kwargs = []

    def fake_observe(**kwargs):
        def decorator(func):
            observe_kwargs.append(kwargs)
            return func

        return decorator

    fake_module = types.ModuleType("langfuse")
    fake_module.observe = fake_observe
    monkeypatch.setitem(sys.modules, "langfuse", fake_module)

    @traced("test.op")
    def fn(secret):
        return "ok"

    assert fn("sk-SUPERSECRET") == "ok"
    assert observe_kwargs == [{"name": "test.op", "capture_input": False}]


def test_traced_fails_open_when_langfuse_import_raises(monkeypatch):
    monkeypatch.delenv("LOOM_DISABLE_LANGFUSE", raising=False)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.delitem(sys.modules, "langfuse", raising=False)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "langfuse":
            raise ModuleNotFoundError("simulado: langfuse no disponible")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    @traced("test.op")
    def fn():
        return "ok"

    assert fn() == "ok"


def test_traced_calls_metadata_fn_and_attaches_to_trace(monkeypatch):
    monkeypatch.delenv("LOOM_DISABLE_LANGFUSE", raising=False)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    attached = []

    def fake_observe(**_kwargs):
        def decorator(func):
            return func

        return decorator

    class _FakeClient:
        def update_current_trace(self, *, metadata):
            attached.append(metadata)

    fake_module = types.ModuleType("langfuse")
    fake_module.observe = fake_observe
    fake_module.get_client = lambda: _FakeClient()
    monkeypatch.setitem(sys.modules, "langfuse", fake_module)

    def _metadata(manuscript_id, **_kwargs):
        return {"manuscript_id": manuscript_id}

    @traced("test.op", metadata_fn=_metadata)
    def fn(manuscript_id):
        return manuscript_id.upper()

    assert fn("abc123") == "ABC123"
    assert attached == [{"manuscript_id": "abc123"}]


def test_traced_metadata_attachment_fails_open(monkeypatch):
    monkeypatch.delenv("LOOM_DISABLE_LANGFUSE", raising=False)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    def fake_observe(**_kwargs):
        def decorator(func):
            return func

        return decorator

    class _BoomClient:
        def update_current_trace(self, *, metadata):
            raise RuntimeError("boom")

    fake_module = types.ModuleType("langfuse")
    fake_module.observe = fake_observe
    fake_module.get_client = lambda: _BoomClient()
    monkeypatch.setitem(sys.modules, "langfuse", fake_module)

    @traced("test.op", metadata_fn=lambda **_: {"x": 1})
    def fn():
        return "ok"

    assert fn() == "ok"
