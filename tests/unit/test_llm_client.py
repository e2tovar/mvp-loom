"""Tests unitarios de la puerta LLM (T009).

Sin red: se usa un transporte falso que intercepta litellm.completion.
"""

from __future__ import annotations

import json
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
    monkeypatch.setattr(litellm, "success_callback", [])

    LiteLLMClient()

    assert litellm.success_callback == ["langfuse"]


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
