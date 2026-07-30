"""Puerta única a Langfuse fuera de backend/llm/ (ADR-0003, capa 2 de 2).

`traced(name, metadata_fn=None)` decora las funciones de entrada de las tres
pipelines de extracción. No-op transparente —no importa `langfuse`— si
LOOM_DISABLE_LANGFUSE=1 o si LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY no están
configuradas. Fail-open: cualquier fallo de la integración se loguea en
WARNING y la función decorada sigue devolviendo su resultado normal.
"""

from __future__ import annotations

import functools
import logging
import os
from typing import Callable, TypeVar

log = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)


def _langfuse_enabled() -> bool:
    if os.environ.get("LOOM_DISABLE_LANGFUSE") == "1":
        return False
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY")) and bool(
        os.environ.get("LANGFUSE_SECRET_KEY")
    )


def traced(
    name: str,
    metadata_fn: Callable[..., dict] | None = None,
) -> Callable[[F], F]:
    """Envuelve `func` en una traza Langfuse de nivel superior llamada `name`.

    `metadata_fn`, si se da, recibe los mismos argumentos que `func` y su
    resultado (un dict) se adjunta a la traza. Un fallo en cualquier punto de
    la integración con Langfuse nunca impide que `func` devuelva su resultado.
    """

    def decorator(func: F) -> F:
        if not _langfuse_enabled():
            return func

        try:
            from langfuse import observe
        except Exception as exc:
            log.warning("Langfuse configurado pero no disponible (%s); sin trazas.", exc)
            return func

        observed = observe(name=name)(func)

        if metadata_fn is None:
            return observed

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                from langfuse import get_client

                get_client().update_current_trace(metadata=metadata_fn(*args, **kwargs))
            except Exception as exc:
                log.warning("No se pudo adjuntar metadata a la traza Langfuse: %s", exc)
            return observed(*args, **kwargs)

        return wrapper

    return decorator
