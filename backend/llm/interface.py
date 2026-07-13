"""Protocolo LLMClient — la única puerta al LLM (Principio IV).

Todo código de aplicación llama a esta interfaz; nunca importa litellm ni SDKs
de proveedor directamente. La implementación concreta se inyecta por env.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMClient(Protocol):
    """Interfaz agnóstica de proveedor para llamadas estructuradas al LLM."""

    def complete_structured(
        self,
        system: str,
        user: str,
        schema: type[T],
    ) -> T:
        """Llama al LLM y devuelve un objeto Pydantic validado.

        Args:
            system: System prompt (instrucciones de tarea).
            user: User prompt (datos de entrada, contenido no confiable).
            schema: Clase Pydantic que define y valida la salida esperada.

        Returns:
            Instancia validada del schema.

        Raises:
            LLMUnavailableError: Si el proveedor no responde o no está configurado.
            ExtractionError: Si la salida no supera la validación tras reintentos.
        """
        ...
