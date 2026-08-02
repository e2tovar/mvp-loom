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


def _langfuse_enabled() -> bool:
    """Señal de habilitación duplicada a propósito de `backend/observability/tracing.py`
    (ADR-0003): esta capa (callback nativo de litellm) y la de `traced()` son
    independientes — ninguna importa a la otra."""
    if os.environ.get("LOOM_DISABLE_LANGFUSE") == "1":
        return False
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY")) and bool(
        os.environ.get("LANGFUSE_SECRET_KEY")
    )


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
        # LOOM_LLM_EXTRA_BODY: JSON opcional para parámetros específicos del proveedor,
        # p. ej. '{"thinking_budget_tokens": 0}' para desactivar thinking en Kimi K2.5.
        raw_extra = os.environ.get("LOOM_LLM_EXTRA_BODY", "")
        self._extra_body: dict | None = json.loads(raw_extra) if raw_extra.strip() else None

        if _langfuse_enabled():
            try:
                # litellm resuelve el host del callback "langfuse_otel" leyendo él mismo
                # LANGFUSE_OTEL_HOST/LANGFUSE_HOST del entorno (litellm/integrations/
                # langfuse/langfuse_otel.py) — no conoce LANGFUSE_BASE_URL, que es la
                # variable que usa el SDK langfuse (capa 2, tracing.py) y la única que
                # documentamos en .env.example. Sin este puente, con las keys puestas
                # pero sin LANGFUSE_OTEL_HOST/LANGFUSE_HOST, litellm cae por defecto al
                # Langfuse Cloud público — justo lo que ADR-0003 rechazó. Se traduce acá,
                # en memoria, para que `.env` tenga una sola variable de host.
                if not os.environ.get("LANGFUSE_OTEL_HOST") and not os.environ.get(
                    "LANGFUSE_HOST"
                ):
                    base_url = os.environ.get("LANGFUSE_BASE_URL")
                    if base_url:
                        os.environ["LANGFUSE_OTEL_HOST"] = base_url

                # "langfuse_otel", NO "langfuse": el callback llamado "langfuse" es la
                # integración legacy de litellm, atada al SDK langfuse 2.x
                # (`from langfuse.client import Langfuse`), que no existe con el pin
                # `langfuse>=3.0,<4` de pyproject.toml. "langfuse_otel" es el logger
                # compatible con v3 y además emite spans OTel en el contexto ambiente,
                # que es el mecanismo por el que anidan bajo traced() (ADR-0003).
                # Se añade sin pisar callbacks que otro componente ya hubiera registrado.
                if "langfuse_otel" not in litellm.success_callback:
                    litellm.success_callback.append("langfuse_otel")
            except Exception as exc:  # fail-open (ADR-0003)
                log.warning("No se pudo activar el callback nativo de Langfuse: %s", exc)

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
            # Nombra el span "raw_gen_ai_request" del callback langfuse_otel (capa 1,
            # ADR-0003) con el nombre del schema (SceneExtraction/MergeJudgement/…) en
            # vez del genérico por defecto — distingue tipos de llamada (extracción vs.
            # resolución de personajes) sin tocar la firma de complete_structured, ya
            # que `schema` ya es un parámetro del protocolo.
            "metadata": {"generation_name": schema.__name__},
        }
        if self._api_base:
            kwargs["api_base"] = self._api_base
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._extra_body:
            kwargs["extra_body"] = self._extra_body

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
                last_exc = ExtractionError("El LLM no devolvió ninguna tool call.")
                if attempt < _MAX_RETRIES:
                    log.warning(
                        "Reintentando llamada LLM (intento %d): respuesta sin tool call.",
                        attempt + 1,
                    )
                    continue
                raise last_exc

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
