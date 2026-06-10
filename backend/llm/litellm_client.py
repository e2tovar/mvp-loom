"""Implementación LiteLLM del protocolo LLMClient (Principio IV).

LiteLLM es la ÚNICA dependencia de proveedor; ningún otro módulo la importa.
Tool-calling forzado con tool_choice="required", temperatura 0, validación Pydantic
con un reintento ante ValidationError.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TypeVar

import litellm
from pydantic import BaseModel, ValidationError

from backend.core.errors import ExtractionError, LLMUnavailableError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_MAX_RETRIES = 1


def _build_tool(schema: type[BaseModel]) -> dict:
    """Convierte un modelo Pydantic en una tool definition de OpenAI."""
    return {
        "type": "function",
        "function": {
            "name": schema.__name__,
            "description": schema.__doc__ or schema.__name__,
            "parameters": schema.model_json_schema(),
        },
    }


class LiteLLMClient:
    """Cliente LLM multi-proveedor basado en LiteLLM.

    Proveedor seleccionado 100 % por variables de entorno (research R1):
    - LOOM_LLM_MODEL / LOOM_LLM_API_BASE / LOOM_LLM_API_KEY  → OpenCode Go u otro
      endpoint OpenAI-compatible.
    - LOOM_LLM_MODEL=azure/<deployment> + AZURE_API_KEY/BASE/VERSION → Azure OpenAI.
    """

    def __init__(self) -> None:
        self._model = os.environ.get("LOOM_LLM_MODEL", "")
        if not self._model:
            raise LLMUnavailableError(
                "LOOM_LLM_MODEL no está configurado. "
                "Define las variables en .env (ver .env.example)."
            )
        self._api_base = os.environ.get("LOOM_LLM_API_BASE") or None
        self._api_key = os.environ.get("LOOM_LLM_API_KEY") or None

    def complete_structured(
        self,
        system: str,
        user: str,
        schema: type[T],
    ) -> T:
        """Llama al LLM y devuelve una instancia validada de `schema`.

        Reintenta una vez ante ValidationError de Pydantic. El coste de la llamada
        se registra en DEBUG para observabilidad.
        """
        tool = _build_tool(schema)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "tools": [tool],
            "tool_choice": {"type": "function", "function": {"name": schema.__name__}},
            "temperature": 0,
        }
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if self._api_key:
            kwargs["api_key"] = self._api_key

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                response = litellm.completion(**kwargs)
            except litellm.exceptions.AuthenticationError as exc:
                raise LLMUnavailableError(f"Error de autenticación LLM: {exc}") from exc
            except litellm.exceptions.APIConnectionError as exc:
                raise LLMUnavailableError(f"LLM no disponible: {exc}") from exc
            except Exception as exc:
                raise LLMUnavailableError(f"Error inesperado del LLM: {exc}") from exc

            cost = getattr(response, "_hidden_params", {}).get("response_cost")
            if cost is not None:
                log.debug("LLM cost=%.6f model=%s", cost, self._model)

            tool_calls = response.choices[0].message.tool_calls
            if not tool_calls:
                raise ExtractionError("El LLM no devolvió ninguna tool call.")

            raw = tool_calls[0].function.arguments
            try:
                return schema.model_validate(json.loads(raw))
            except (ValidationError, json.JSONDecodeError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    log.warning(
                        "Reintentando llamada LLM (intento %d) tras error de validación: %s",
                        attempt + 1,
                        exc,
                    )
                    continue
                raise ExtractionError(
                    f"La salida del LLM no superó la validación tras {_MAX_RETRIES + 1} "
                    f"intentos: {exc}"
                ) from last_exc

        raise ExtractionError("No se obtuvo respuesta válida del LLM.")
