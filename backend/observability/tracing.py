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
from collections.abc import Callable
from typing import TypeVar

log = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)


def _langfuse_enabled() -> bool:
    """Señal de habilitación duplicada a propósito de `backend/llm/litellm_client.py`
    (ADR-0003): las dos capas son independientes y ninguna importa a la otra.

    Momento de decisión asimétrico (deliberado): aquí se evalúa al DECORAR, es decir
    al importar el módulo de la pipeline; en `LiteLLMClient` se evalúa al CONSTRUIR el
    cliente. Consecuencia práctica: cambiar `LOOM_DISABLE_LANGFUSE`/`LANGFUSE_*`
    después de importar la pipeline ya no afecta a `traced`, pero sí a un
    `LiteLLMClient` creado más tarde.
    """
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

        def _inner(*args, **kwargs):
            if metadata_fn is not None:
                try:
                    from langfuse import get_client

                    get_client().update_current_trace(metadata=metadata_fn(*args, **kwargs))
                except Exception as exc:
                    log.warning("No se pudo adjuntar metadata a la traza Langfuse: %s", exc)
            return func(*args, **kwargs)

        try:
            from langfuse import observe

            # capture_input=False: la captura por defecto serializa los kwargs tal
            # cual, y las pipelines reciben el propio `llm_client` — cuyo `__dict__`
            # incluye `_api_key`. Eso escribiría la clave del proveedor en claro en
            # Postgres/ClickHouse/MinIO. `metadata_fn` ya aporta lo que el ADR quiere
            # de las entradas, así que capturarlas es riesgo puro.
            return functools.wraps(func)(observe(name=name, capture_input=False)(_inner))
        except Exception as exc:
            log.warning("Langfuse configurado pero no disponible (%s); sin trazas.", exc)
            return func

    return decorator
