"""Tests unitarios de la puerta LLM (T009).

Sin red: se usa un transporte falso que intercepta litellm.completion.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import litellm
import pytest
from pydantic import BaseModel

from backend.core.errors import ExtractionError, LLMUnavailableError
from backend.llm.litellm_client import LiteLLMClient


class _SimpleSchema(BaseModel):
    name: str
    value: int


def _make_response(payload: dict) -> MagicMock:
    """Construye un objeto de respuesta falso con la estructura de LiteLLM."""
    tool_call = MagicMock()
    tool_call.function.arguments = json.dumps(payload)
    choice = MagicMock()
    choice.message.tool_calls = [tool_call]
    resp = MagicMock()
    resp.choices = [choice]
    resp._hidden_params = {"response_cost": 0.0001}
    return resp


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("LOOM_LLM_MODEL", "openai/test-model")
    monkeypatch.setenv("LOOM_LLM_API_KEY", "test-key")
    return LiteLLMClient()


def test_returns_validated_schema(client, monkeypatch):
    """La salida válida del LLM se convierte en un objeto Pydantic correcto."""
    with patch("backend.llm.litellm_client.litellm.completion") as mock_completion:
        mock_completion.return_value = _make_response({"name": "Hamlet", "value": 42})
        result = client.complete_structured("sys", "user", _SimpleSchema)
    assert isinstance(result, _SimpleSchema)
    assert result.name == "Hamlet"
    assert result.value == 42


def test_generation_name_tagged_with_schema_name(client):
    """El nombre del schema viaja como metadata.generation_name (ADR-0003): distingue
    en Langfuse las llamadas de extracción de las de resolución/otros tipos, sin
    tocar la firma de complete_structured — `schema` ya es parte del protocolo."""
    with patch("backend.llm.litellm_client.litellm.completion") as mock_completion:
        mock_completion.return_value = _make_response({"name": "Hamlet", "value": 42})
        client.complete_structured("sys", "user", _SimpleSchema)

    _, call_kwargs = mock_completion.call_args
    assert call_kwargs["metadata"] == {"generation_name": "_SimpleSchema"}


def test_retries_on_invalid_response(client, monkeypatch):
    """Si la primera respuesta no supera la validación, reintenta una vez."""
    bad_response = _make_response({"name": "Hamlet"})  # falta value
    good_response = _make_response({"name": "Hamlet", "value": 7})
    with patch("backend.llm.litellm_client.litellm.completion") as mock_completion:
        mock_completion.side_effect = [bad_response, good_response]
        result = client.complete_structured("sys", "user", _SimpleSchema)
    assert result.value == 7
    assert mock_completion.call_count == 2


def test_raises_extraction_error_after_retries_exhausted(client, monkeypatch):
    """Después de agotar los reintentos se lanza ExtractionError."""
    bad_response = _make_response({"name": "Hamlet"})  # falta value
    with patch("backend.llm.litellm_client.litellm.completion") as mock_completion:
        mock_completion.return_value = bad_response
        with pytest.raises(ExtractionError):
            client.complete_structured("sys", "user", _SimpleSchema)


def test_retries_once_when_no_tool_call_then_succeeds(client, monkeypatch):
    """Si la primera respuesta no trae tool call, reintenta una vez y acepta la segunda."""
    no_tool_response = _make_response({"name": "Hamlet", "value": 42})
    no_tool_response.choices[0].message.tool_calls = None
    good_response = _make_response({"name": "Hamlet", "value": 42})
    with patch("backend.llm.litellm_client.litellm.completion") as mock_completion:
        mock_completion.side_effect = [no_tool_response, good_response]
        result = client.complete_structured("sys", "user", _SimpleSchema)
    assert result.name == "Hamlet"
    assert result.value == 42
    assert mock_completion.call_count == 2


def test_raises_after_retries_when_no_tool_call_persists(client, monkeypatch):
    """Si ninguna respuesta trae tool call, se agota el reintento y se lanza ExtractionError."""
    no_tool_response = _make_response({"name": "Hamlet", "value": 42})
    no_tool_response.choices[0].message.tool_calls = []
    with patch("backend.llm.litellm_client.litellm.completion") as mock_completion:
        mock_completion.return_value = no_tool_response
        with pytest.raises(ExtractionError):
            client.complete_structured("sys", "user", _SimpleSchema)
    assert mock_completion.call_count == 2


def test_raises_llm_unavailable_without_model(monkeypatch):
    """Sin LOOM_LLM_MODEL configurado se lanza LLMUnavailableError al construir."""
    monkeypatch.delenv("LOOM_LLM_MODEL", raising=False)
    with pytest.raises(LLMUnavailableError):
        LiteLLMClient()


def test_raises_llm_unavailable_on_auth_error(client, monkeypatch):
    """Un error de autenticación del proveedor se convierte en LLMUnavailableError."""
    import litellm as _litellm

    with patch("backend.llm.litellm_client.litellm.completion") as mock_completion:
        mock_completion.side_effect = _litellm.exceptions.AuthenticationError(
            "Unauthorized", llm_provider="openai", model="test"
        )
        with pytest.raises(LLMUnavailableError):
            client.complete_structured("sys", "user", _SimpleSchema)


def test_langfuse_callback_registered_when_enabled(monkeypatch):
    monkeypatch.setenv("LOOM_LLM_MODEL", "openai/test-model")
    monkeypatch.delenv("LOOM_DISABLE_LANGFUSE", raising=False)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    # Se siembra un callback ajeno: registrar Langfuse debe añadir, no pisar.
    monkeypatch.setattr(litellm, "success_callback", ["some_other_callback"])

    LiteLLMClient()

    # "langfuse_otel" (v3-compatible), no el "langfuse" legacy atado al SDK 2.x.
    assert litellm.success_callback == ["some_other_callback", "langfuse_otel"]

    # Idempotente: una segunda instancia no duplica el callback.
    LiteLLMClient()
    assert litellm.success_callback == ["some_other_callback", "langfuse_otel"]


def test_langfuse_callback_not_registered_when_disabled(monkeypatch):
    monkeypatch.setenv("LOOM_LLM_MODEL", "openai/test-model")
    monkeypatch.setenv("LOOM_DISABLE_LANGFUSE", "1")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setattr(litellm, "success_callback", [])

    LiteLLMClient()

    assert litellm.success_callback == []


def test_langfuse_callback_not_registered_without_keys(monkeypatch):
    monkeypatch.setenv("LOOM_LLM_MODEL", "openai/test-model")
    monkeypatch.delenv("LOOM_DISABLE_LANGFUSE", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.setattr(litellm, "success_callback", [])

    LiteLLMClient()

    assert litellm.success_callback == []


def test_langfuse_base_url_bridges_to_otel_host(monkeypatch):
    """litellm solo lee LANGFUSE_OTEL_HOST/LANGFUSE_HOST (hardcodeado en su propio
    código); sin este puente, con solo LANGFUSE_BASE_URL fijada (la única variable
    de host documentada en .env.example) la capa 1 caería en silencio al Langfuse
    Cloud público — el escenario que ADR-0003 rechazó."""
    monkeypatch.setenv("LOOM_LLM_MODEL", "openai/test-model")
    monkeypatch.delenv("LOOM_DISABLE_LANGFUSE", raising=False)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.delenv("LANGFUSE_OTEL_HOST", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3000")
    monkeypatch.setattr(litellm, "success_callback", [])

    LiteLLMClient()

    assert os.environ.get("LANGFUSE_OTEL_HOST") == "http://localhost:3000"
    assert litellm.success_callback == ["langfuse_otel"]


def test_langfuse_existing_otel_host_not_overridden(monkeypatch):
    """Si LANGFUSE_OTEL_HOST ya está fijada explícitamente, el puente no la pisa."""
    monkeypatch.setenv("LOOM_LLM_MODEL", "openai/test-model")
    monkeypatch.delenv("LOOM_DISABLE_LANGFUSE", raising=False)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_OTEL_HOST", "http://explicit-host:3000")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:3000")
    monkeypatch.setattr(litellm, "success_callback", [])

    LiteLLMClient()

    assert os.environ.get("LANGFUSE_OTEL_HOST") == "http://explicit-host:3000"
