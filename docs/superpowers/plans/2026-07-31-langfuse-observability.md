# Observabilidad de producción con Langfuse — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** poder depurar una extracción real (API o CLI) contra un manuscrito real viendo, agrupadas por manuscrito, todas las llamadas LLM que produjo — sin que el eval harness ni CI dependan nunca de que Langfuse esté arriba.

**Architecture:** ver `docs/adr/0003-langfuse-observability.md`. Dos capas independientes que Langfuse anida solo vía contexto OpenTelemetry: (1) callback nativo de litellm dentro de `litellm_client.py`, (2) decorador propio `traced()` en un módulo nuevo `backend/observability/`, usado por las tres pipelines de extracción. Ambas capas leen el mismo par de señales (`LOOM_DISABLE_LANGFUSE`, `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`) pero cada una con su propia comprobación — deliberadamente duplicada y no importada de la otra, para que `backend/llm/` no dependa de `backend/observability/` (ver ADR, alternativas consideradas).

**Tech Stack:** Python 3.12, litellm 1.88.1 (ya instalado), `langfuse` SDK Python v3 (nuevo, no instalado — se añade en Task 1), pytest, Langfuse self-hosted vía Docker Compose (Postgres + ClickHouse + Redis + MinIO + langfuse-web/worker).

## Global Constraints

- **Principio IV (una sola puerta por dependencia externa):** ningún módulo fuera de `backend/llm/litellm_client.py` y `backend/observability/tracing.py` puede importar `langfuse` ni `litellm`.
- **Principio VI (idempotencia y cache por hash):** las trazas se taggean con los mismos campos que ya componen la clave de cache (`manuscript_id`, modelo, `PROMPT_VERSION`, `SCHEMA_VERSION`) — no se introduce un mecanismo de identidad paralelo.
- **Fail-open, siempre:** ningún fallo de Langfuse (SDK no instalado, host inalcanzable, excepción de la integración) puede propagar y romper una extracción real. Todo punto de contacto con Langfuse va en `try/except`, logueando `WARNING`.
- **Aislamiento del eval harness, obligatorio:** `eval/seed.py` fija `LOOM_DISABLE_LANGFUSE=1` antes de instanciar `LiteLLMClient`, sin importar qué haya en el entorno. CI y `make gates` nunca dependen de que Langfuse esté arriba.
- **Self-hosted, opt-in:** Langfuse Cloud queda descartado (el texto que pasa por el LLM son fragmentos de novelas con derechos de terceros). El stack de Langfuse vive en `docker-compose.langfuse.yml`, separado del `docker-compose.yml` del proyecto (Neo4j, puertos ya remapeados a `17474`/`17687`); la mayoría de sesiones de desarrollo y el CI nunca lo levantan.
- **Sin cambios de firma en el protocolo LLM:** `LLMClient.complete_structured(system, user, schema)` no cambia. La propagación de contexto es vía OpenTelemetry (SDK de Langfuse), no parámetros nuevos.

## File Structure

**Nuevos:**
- `backend/observability/__init__.py` — paquete vacío.
- `backend/observability/tracing.py` — `traced(name, metadata_fn=None)`, la puerta única a Langfuse fuera de `backend/llm/`.
- `tests/unit/test_tracing.py` — cubre no-op (flag/config ausente), wrap real (mockeado), fail-open ante fallo de import o de adjuntar metadata.
- `tests/unit/test_attributes_cache.py` — cubre las 3 properties nuevas de `AttributesCache` (no existe test unitario previo de esta clase; no se backfillea cobertura completa, solo lo que este plan añade).
- `tests/unit/test_eval_disables_langfuse.py` — que `eval/seed.py::_use_frozen_cache` fija el flag de aislamiento.
- `docker-compose.langfuse.yml` — stack oficial de Langfuse self-hosted, opt-in.

**Modificados:**
- `backend/llm/cache.py` — properties públicas de solo lectura `model`, `prompt_version`, `schema_version` en `ExtractionCache`, `RelationsCache`, `AttributesCache`.
- `backend/llm/litellm_client.py` — registrar `litellm.success_callback = ["langfuse"]` condicionado al flag, fail-open.
- `tests/unit/test_llm_client.py` — tests del registro condicional del callback.
- `backend/extraction/pipeline.py` — decorar `run_pipeline` con `@traced("extraction.characters", metadata_fn=...)`.
- `backend/extraction/relations/pipeline.py` — decorar `run_relations_pipeline` con `@traced("extraction.relations", metadata_fn=...)`.
- `backend/extraction/attributes/pipeline.py` — decorar `run_attributes_pipeline` con `@traced("extraction.attributes", metadata_fn=...)`.
- `tests/unit/test_extraction_cache.py`, `tests/unit/test_relations_cache.py` — tests de las properties nuevas.
- `eval/seed.py` — `_use_frozen_cache()` fija también `LOOM_DISABLE_LANGFUSE`.
- `pyproject.toml` — añadir dependencia `langfuse`.
- `.env.example` — variables nuevas de Langfuse.
- `README.md` §11 (estructura del repo) y §13 (convenciones).

---

### Task 1: Módulo `backend/observability/tracing.py` + dependencia `langfuse`

**Files:**
- Modify: `pyproject.toml`
- Create: `backend/observability/__init__.py`
- Create: `backend/observability/tracing.py`
- Test: `tests/unit/test_tracing.py`

**Interfaces:**
- Consumes: nada (primera task, sin dependencias de otras).
- Produces: `traced(name: str, metadata_fn: Callable[..., dict] | None = None) -> Callable[[F], F]` — decorador que Task 4 usa sobre las tres pipelines. `metadata_fn`, si se pasa, recibe los mismos argumentos que la función decorada y su dict de retorno se adjunta a la traza vía `get_client().update_current_trace(metadata=...)`.

- [ ] **Step 1: Añadir la dependencia `langfuse` a `pyproject.toml`**

En `pyproject.toml`, dentro de `dependencies = [...]`, añadir tras `"litellm>=1.56",`:

```toml
    "litellm>=1.56",
    "langfuse>=3.0,<4",
```

- [ ] **Step 2: Instalar y confirmar la API del SDK instalado**

Run: `uv sync`

Luego: `python -c "from langfuse import observe, get_client; print('ok')"`

Expected: imprime `ok`. Si la versión resuelta NO expone `observe`/`get_client` con esos nombres, es un cambio de import de una línea en `tracing.py` (Step 4) — no de arquitectura. Confirmar antes de continuar.

- [ ] **Step 3: Escribir el paquete vacío**

Crear `backend/observability/__init__.py` con contenido vacío (0 bytes o solo un docstring de una línea).

- [ ] **Step 4: Escribir los tests que fallan**

```python
# tests/unit/test_tracing.py
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

    observed_names = []

    def fake_observe(*, name):
        def decorator(func):
            observed_names.append(name)
            return func

        return decorator

    fake_module = types.ModuleType("langfuse")
    fake_module.observe = fake_observe
    monkeypatch.setitem(sys.modules, "langfuse", fake_module)

    @traced("test.op")
    def fn(x):
        return x + 1

    assert fn(1) == 2
    assert observed_names == ["test.op"]


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

    def fake_observe(*, name):
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

    def fake_observe(*, name):
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
```

- [ ] **Step 5: Ejecutar y verificar que fallan**

Run: `pytest tests/unit/test_tracing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.observability.tracing'`.

- [ ] **Step 6: Implementar `tracing.py`**

```python
# backend/observability/tracing.py
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

            return functools.wraps(func)(observe(name=name)(_inner))
        except Exception as exc:
            log.warning("Langfuse configurado pero no disponible (%s); sin trazas.", exc)
            return func

    return decorator
```

**Nota post-review (corrección aplicada tras Task 1):** la primera versión de este
código llamaba a `observe(name=name)(func)` fuera del `try/except` del import (un
fallo ahí rompía el import del módulo pipeline entero, no solo esa llamada — viola
"fail-open, siempre") y llamaba a `update_current_trace` **antes** de ejecutar la
función observada, cuando el SDK de Langfuse todavía no tiene una traza activa en
contexto (la metadata nunca se adjuntaba realmente). La versión de arriba mete
`observe(...)` dentro del mismo `try/except` que el import, y mueve la llamada a
`update_current_trace` a `_inner`, que `observe()` envuelve directamente — así corre
con el contexto de traza ya activo.

- [ ] **Step 7: Ejecutar y verificar que pasan**

Run: `pytest tests/unit/test_tracing.py -v`
Expected: 7 PASSED (el número correcto de tests del Step 4 — no 8).

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock backend/observability/ tests/unit/test_tracing.py
git commit -m "feat: add Langfuse tracing gate (backend/observability/tracing.py)"
```

---

### Task 2: Properties de metadata en las clases Cache

**Files:**
- Modify: `backend/llm/cache.py`
- Modify: `tests/unit/test_extraction_cache.py`
- Modify: `tests/unit/test_relations_cache.py`
- Create: `tests/unit/test_attributes_cache.py`

**Interfaces:**
- Consumes: nada.
- Produces: `ExtractionCache.model -> str`, `.prompt_version -> int`, `.schema_version -> int`; análogo en `RelationsCache` y `AttributesCache`. Task 4 los usa para construir la metadata de cada traza sin acceder a atributos privados (`_model`, `_prompt_version`, `_schema_version`) desde otro módulo.

Confirmado por grep contra el código real: las tres clases guardan `self._model`, `self._prompt_version`, `self._schema_version` en su `__init__` (idéntico patrón en `ExtractionCache` línea 48-50, `RelationsCache` línea 108-110, `AttributesCache` línea 168-170 de `backend/llm/cache.py`). Ninguna expone hoy properties públicas para esos tres campos — solo `.dir`.

- [ ] **Step 1: Escribir los tests que fallan (uno por clase)**

Añadir al final de `tests/unit/test_extraction_cache.py`:

```python
def test_exposes_model_and_versions_as_public_properties(cache_dir):
    cache = ExtractionCache(3, 2, "openai/kimi-k2.5", cache_dir=cache_dir)
    assert cache.model == "openai/kimi-k2.5"
    assert cache.prompt_version == 3
    assert cache.schema_version == 2
```

Añadir al final de `tests/unit/test_relations_cache.py`:

```python
def test_exposes_model_and_versions_as_public_properties(tmp_path):
    cache = RelationsCache(1, 1, "test-model", cache_dir=tmp_path)
    assert cache.model == "test-model"
    assert cache.prompt_version == 1
    assert cache.schema_version == 1
```

Crear `tests/unit/test_attributes_cache.py`:

```python
"""Properties públicas de AttributesCache (ADR-0003, metadata de tracing).

No backfillea cobertura completa de AttributesCache — eso es alcance de M3.
Cubre únicamente las 3 properties de solo lectura que este plan añade.
"""

from __future__ import annotations

from backend.llm.cache import AttributesCache


def test_exposes_model_and_versions_as_public_properties(tmp_path):
    cache = AttributesCache(2, 1, "test-model", cache_dir=tmp_path)
    assert cache.model == "test-model"
    assert cache.prompt_version == 2
    assert cache.schema_version == 1
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `pytest tests/unit/test_extraction_cache.py tests/unit/test_relations_cache.py tests/unit/test_attributes_cache.py -v -k public_properties`
Expected: FAIL — `AttributeError: 'ExtractionCache' object has no attribute 'model'` (y análogo para las otras dos).

- [ ] **Step 3: Implementar las properties**

En `backend/llm/cache.py`, en cada una de las tres clases, añadir tras la property `dir` existente (mismo patrón: solo lectura, sin setter):

```python
    @property
    def model(self) -> str:
        """Modelo LLM con el que se compone la clave de cache (solo lectura)."""
        return self._model

    @property
    def prompt_version(self) -> int:
        """PROMPT_VERSION con el que se compone la clave de cache (solo lectura)."""
        return self._prompt_version

    @property
    def schema_version(self) -> int:
        """SCHEMA_VERSION con el que se compone la clave de cache (solo lectura)."""
        return self._schema_version
```

(Repetir idéntico en `ExtractionCache`, `RelationsCache` y `AttributesCache` — los tres nombres de atributo privado son iguales en las tres clases.)

- [ ] **Step 4: Ejecutar y verificar que pasan**

Run: `pytest tests/unit/test_extraction_cache.py tests/unit/test_relations_cache.py tests/unit/test_attributes_cache.py -v`
Expected: todos PASSED (incluidos los tests preexistentes de estos archivos — regresión).

- [ ] **Step 5: Commit**

```bash
git add backend/llm/cache.py tests/unit/test_extraction_cache.py tests/unit/test_relations_cache.py tests/unit/test_attributes_cache.py
git commit -m "feat: expose model/prompt_version/schema_version as read-only cache properties"
```

---

### Task 3: Callback nativo de litellm en `litellm_client.py`

**Files:**
- Modify: `backend/llm/litellm_client.py`
- Modify: `tests/unit/test_llm_client.py`

**Interfaces:**
- Consumes: nada de Task 1/2 (capa independiente a propósito, ver Global Constraints).
- Produces: efecto secundario en `litellm.success_callback` al construir `LiteLLMClient()`. No cambia la firma de `LiteLLMClient.__init__()` ni de `complete_structured`.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir `import litellm` a los imports de `tests/unit/test_llm_client.py` (ya importa `from backend.llm.litellm_client import LiteLLMClient`) y añadir al final del archivo:

```python
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
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `pytest tests/unit/test_llm_client.py -v -k langfuse_callback`
Expected: FAIL — `assert [] == ["langfuse"]` en el primer test (el callback no se registra todavía).

- [ ] **Step 3: Implementar el registro condicional**

En `backend/llm/litellm_client.py`, añadir tras el import de `litellm` (línea 15) una función a nivel de módulo, antes de `class LiteLLMClient`:

```python
def _langfuse_enabled() -> bool:
    """Señal de habilitación duplicada a propósito de `backend/observability/tracing.py`
    (ADR-0003): esta capa (callback nativo de litellm) y la de `traced()` son
    independientes — ninguna importa a la otra."""
    if os.environ.get("LOOM_DISABLE_LANGFUSE") == "1":
        return False
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY")) and bool(
        os.environ.get("LANGFUSE_SECRET_KEY")
    )
```

Y al final de `LiteLLMClient.__init__` (tras la línea `self._extra_body: dict | None = ...`):

```python
        if _langfuse_enabled():
            try:
                litellm.success_callback = ["langfuse"]
            except Exception as exc:  # fail-open (ADR-0003)
                log.warning("No se pudo activar el callback nativo de Langfuse: %s", exc)
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

Run: `pytest tests/unit/test_llm_client.py -v`
Expected: todos PASSED (incluidos los 7 tests preexistentes de este archivo — regresión).

- [ ] **Step 5: Commit**

```bash
git add backend/llm/litellm_client.py tests/unit/test_llm_client.py
git commit -m "feat: register litellm's native Langfuse callback when configured"
```

---

### Task 4: Decorar las tres pipelines de extracción

**Files:**
- Modify: `backend/extraction/pipeline.py`
- Modify: `backend/extraction/relations/pipeline.py`
- Modify: `backend/extraction/attributes/pipeline.py`
- Create: `tests/unit/test_pipeline_trace_metadata.py`

**Interfaces:**
- Consumes: `traced(name, metadata_fn)` de Task 1; `.model`/`.prompt_version`/`.schema_version` de Task 2.
- Produces: nada nuevo para tasks posteriores — es hoja del árbol de dependencias.

Firmas confirmadas contra el código real (idénticas en las tres pipelines):

```python
def run_pipeline(manuscript_id: str, llm_client=None, cache=None, force: bool = False) -> PipelineResult: ...
def run_relations_pipeline(manuscript_id: str, llm_client=None, cache=None, force: bool = False) -> RelationsPipelineResult: ...
def run_attributes_pipeline(manuscript_id: str, llm_client=None, cache=None, force: bool = False) -> AttributesPipelineResult: ...
```

`cache` puede ser `None` (ver firma) — la función de metadata debe tolerarlo sin lanzar, para no romper llamadas que no pasan cache (ADR: fail-open también aquí, aunque el fallo esté dentro de `traced`, no vale la pena arriesgar una excepción no capturada en la propia extracción de metadata).

- [ ] **Step 1: Escribir el test que falla (función de metadata, unidad pura — sin BD, sin Langfuse)**

```python
# tests/unit/test_pipeline_trace_metadata.py
"""Metadata de tracing por pipeline (ADR-0003): unidad pura, sin BD ni Langfuse."""

from __future__ import annotations

from backend.extraction.attributes.pipeline import _trace_metadata as attributes_trace_metadata
from backend.extraction.pipeline import _trace_metadata as characters_trace_metadata
from backend.extraction.relations.pipeline import _trace_metadata as relations_trace_metadata
from backend.llm.cache import AttributesCache, ExtractionCache, RelationsCache


def test_characters_trace_metadata(tmp_path):
    cache = ExtractionCache(3, 2, "openai/kimi-k2.5", cache_dir=tmp_path)
    meta = characters_trace_metadata("ms-1", llm_client=None, cache=cache, force=False)
    assert meta == {
        "manuscript_id": "ms-1",
        "model": "openai/kimi-k2.5",
        "prompt_version": 3,
        "schema_version": 2,
    }


def test_relations_trace_metadata(tmp_path):
    cache = RelationsCache(1, 1, "test-model", cache_dir=tmp_path)
    meta = relations_trace_metadata("ms-2", llm_client=None, cache=cache, force=True)
    assert meta == {
        "manuscript_id": "ms-2",
        "model": "test-model",
        "prompt_version": 1,
        "schema_version": 1,
    }


def test_attributes_trace_metadata(tmp_path):
    cache = AttributesCache(2, 1, "test-model", cache_dir=tmp_path)
    meta = attributes_trace_metadata("ms-3", llm_client=None, cache=cache, force=False)
    assert meta == {
        "manuscript_id": "ms-3",
        "model": "test-model",
        "prompt_version": 2,
        "schema_version": 1,
    }


def test_trace_metadata_tolerates_missing_cache():
    meta = characters_trace_metadata("ms-4", llm_client=None, cache=None, force=False)
    assert meta == {
        "manuscript_id": "ms-4",
        "model": None,
        "prompt_version": None,
        "schema_version": None,
    }
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `pytest tests/unit/test_pipeline_trace_metadata.py -v`
Expected: FAIL — `ImportError: cannot import name '_trace_metadata'`.

- [ ] **Step 3: Implementar `_trace_metadata` + decorar cada pipeline**

En `backend/extraction/pipeline.py`, añadir el import y la función antes de `def run_pipeline(`, y decorar `run_pipeline`:

```python
from backend.observability.tracing import traced

# ... (resto de imports existentes sin cambios)


def _trace_metadata(manuscript_id: str, llm_client=None, cache=None, force: bool = False) -> dict:
    return {
        "manuscript_id": manuscript_id,
        "model": cache.model if cache is not None else None,
        "prompt_version": cache.prompt_version if cache is not None else None,
        "schema_version": cache.schema_version if cache is not None else None,
    }


@traced("extraction.characters", metadata_fn=_trace_metadata)
def run_pipeline(
    manuscript_id: str,
    llm_client=None,
    cache=None,
    force: bool = False,
) -> PipelineResult:
    ...  # cuerpo existente sin cambios
```

Repetir el mismo patrón en `backend/extraction/relations/pipeline.py` (`@traced("extraction.relations", metadata_fn=_trace_metadata)` sobre `run_relations_pipeline`) y en `backend/extraction/attributes/pipeline.py` (`@traced("extraction.attributes", metadata_fn=_trace_metadata)` sobre `run_attributes_pipeline`). Cada archivo define su propia `_trace_metadata` local (idéntica en las tres — duplicación deliberada de 6 líneas, no vale la pena una abstracción compartida para esto).

- [ ] **Step 4: Ejecutar y verificar que pasan**

Run: `pytest tests/unit/test_pipeline_trace_metadata.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Regresión — confirmar que decorar no rompe nada existente**

Run: `pytest tests/unit/test_extraction_pipeline.py tests/unit/test_relations_pipeline.py -v`
Expected: todos PASSED sin modificar esos archivos. En un entorno de test sin `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` configuradas, `traced(...)` es no-op y devuelve la función original sin envolver — cero cambio de comportamiento.

No existe hoy un archivo `tests/unit/test_attributes_pipeline.py` (M3 en progreso, ver `tests/integration/test_attributes_e2e.py`). Verificación mínima de que el módulo sigue siendo importable:

Run: `python -c "import backend.extraction.attributes.pipeline"`
Expected: sin errores. Si `tests/integration/test_attributes_e2e.py` puede correrse con Neo4j levantado (`docker compose up -d`), ejecutarlo también como regresión: `pytest tests/integration/test_attributes_e2e.py -v`.

- [ ] **Step 6: Commit**

```bash
git add backend/extraction/pipeline.py backend/extraction/relations/pipeline.py backend/extraction/attributes/pipeline.py tests/unit/test_pipeline_trace_metadata.py
git commit -m "feat: wrap extraction pipelines with Langfuse traces (ADR-0003)"
```

---

### Task 5: Aislamiento explícito del eval harness

**Files:**
- Modify: `eval/seed.py`
- Create: `tests/unit/test_eval_disables_langfuse.py`

**Interfaces:**
- Consumes: nada (independiente de Tasks 1-4; el flag `LOOM_DISABLE_LANGFUSE` ya es lo que ambas capas de Task 1/3 consultan, pero este task no importa código de esas tasks).
- Produces: garantía de que `eval/seed.py::seed_all` nunca deja pasar trazas de eval a Langfuse.

Confirmado por lectura directa de `eval/seed.py`: solo esta función (no los runners de `eval/{characters,relations,attributes}/runner.py`, que no instancian `LiteLLMClient` — son de solo lectura del grafo) instancia el cliente LLM, en `_extract()` línea 92, siempre después de que `seed_all()` (línea 149) ha llamado a `_use_frozen_cache()` (línea 53-55). Ese es el punto correcto de aislamiento — mismo patrón que ya usa para `LOOM_CACHE_DIR`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
# tests/unit/test_eval_disables_langfuse.py
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
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `pytest tests/unit/test_eval_disables_langfuse.py -v`
Expected: FAIL — `KeyError: 'LOOM_DISABLE_LANGFUSE'` en el primer test.

- [ ] **Step 3: Implementar**

En `eval/seed.py`, modificar `_use_frozen_cache()` (líneas 53-55):

```python
def _use_frozen_cache() -> None:
    """Apunta las cachés LLM al directorio versionado y aísla de Langfuse (ADR-0003)."""
    os.environ.setdefault("LOOM_CACHE_DIR", str(FROZEN_CACHE_DIR))
    os.environ.setdefault("LOOM_DISABLE_LANGFUSE", "1")
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

Run: `pytest tests/unit/test_eval_disables_langfuse.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Regresión del eval harness completo**

Run: `pytest tests/unit/test_cache_dir_config.py tests/unit/test_eval_runner.py tests/unit/test_eval_strict.py -v`
Expected: todos PASSED — no se ha tocado el comportamiento de `LOOM_CACHE_DIR`, solo se añade el flag de Langfuse en la misma función.

- [ ] **Step 6: Commit**

```bash
git add eval/seed.py tests/unit/test_eval_disables_langfuse.py
git commit -m "fix: eval harness fija LOOM_DISABLE_LANGFUSE antes de instanciar LiteLLMClient"
```

---

### Task 6: Infra — `docker-compose.langfuse.yml`

**Files:**
- Create: `docker-compose.langfuse.yml`

**Interfaces:** ninguna — infraestructura pura, sin código Python.

- [ ] **Step 1: Obtener el compose oficial de Langfuse self-hosted**

Usar `WebFetch` sobre la documentación oficial de self-hosting de Langfuse (`https://langfuse.com/self-hosting/docker-compose`) para obtener el `docker-compose.yml` de referencia vigente (Postgres, ClickHouse, Redis/Valkey, MinIO, `langfuse-worker`, `langfuse-web`), con una versión de imagen pinneada (no `latest`). No transcribir de memoria — los puertos, nombres de variables y servicios de Langfuse cambian entre versiones del self-host oficial.

- [ ] **Step 2: Adaptar al proyecto**

Guardar el contenido obtenido como `docker-compose.langfuse.yml` en la raíz del repo. Cambios respecto al original:
- Prefijar `container_name` de cada servicio con `loom-langfuse-` (mismo estilo que `loom-neo4j` en `docker-compose.yml`).
- Revisar los puertos publicados de cada servicio contra los ya usados por `docker-compose.yml` (`17474`, `17687`) y remapear cualquier colisión (Langfuse suele usar `3000` para el web, `8123`/`9000` para ClickHouse, `9090`/`9091` para MinIO — confirmar contra el archivo obtenido en Step 1, no asumir).
- Añadir un comentario de cabecera: `# Stack Langfuse self-hosted (ADR-0003). Opt-in: docker compose -f docker-compose.yml -f docker-compose.langfuse.yml up`.

- [ ] **Step 3: Verificar que levanta sin conflicto de puertos**

Run: `docker compose -f docker-compose.yml -f docker-compose.langfuse.yml config`
Expected: sin error de parseo ni de puertos duplicados.

Run (si hay recursos disponibles para levantar ~6 contenedores): `docker compose -f docker-compose.yml -f docker-compose.langfuse.yml up -d` seguido de `docker compose -f docker-compose.yml -f docker-compose.langfuse.yml ps` — todos los servicios en estado `running`/`healthy`. Luego `docker compose -f docker-compose.yml -f docker-compose.langfuse.yml down`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.langfuse.yml
git commit -m "chore: add opt-in Langfuse self-hosted docker-compose stack"
```

---

### Task 7: Documentación — `.env.example` y `README.md`

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:** ninguna — solo documentación.

- [ ] **Step 1: Añadir variables a `.env.example`**

Al final de `.env.example`, siguiendo el mismo estilo de sección `── X ──` ya usado en el archivo:

```bash
# ── Observabilidad (opt-in, ADR-0003) ─────────────────────────────────────────
# Self-hosted Langfuse (docker-compose.langfuse.yml). Vacías = observabilidad
# deshabilitada por completo (fail-open, ninguna extracción depende de esto).
# LANGFUSE_PUBLIC_KEY=
# LANGFUSE_SECRET_KEY=
# LANGFUSE_HOST=http://localhost:3000
#
# El eval harness fija LOOM_DISABLE_LANGFUSE=1 por código (eval/seed.py), no
# hace falta fijarlo aquí salvo que quieras forzarlo también fuera del eval.
# LOOM_DISABLE_LANGFUSE=1
```

- [ ] **Step 2: Actualizar `README.md` §11 (estructura del repo)**

En el bloque de árbol de `## 11. Estructura del repositorio`, añadir una línea tras `│   ├── llm/                  # interfaz agnóstica de proveedor`:

```
│   ├── llm/                  # interfaz agnóstica de proveedor
│   ├── observability/        # puerta única a Langfuse (opt-in, ADR-0003)
```

- [ ] **Step 3: Actualizar `README.md` §13 (convenciones)**

Añadir un bullet al final de la lista de `## 13. Convenciones para los agentes de código`:

```markdown
- **Observabilidad opt-in, nunca gate.** Langfuse (ADR-0003) instrumenta corridas reales de extracción; el eval harness lo deshabilita explícitamente y CI nunca depende de que esté arriba.
```

- [ ] **Step 4: Verificación manual de cierre**

Con Langfuse self-hosted arriba (`docker compose -f docker-compose.yml -f docker-compose.langfuse.yml up`) y `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`/`LANGFUSE_HOST` configuradas en `.env` (sin `LOOM_DISABLE_LANGFUSE`), correr:

```bash
python -m backend.extraction.run <manuscript_id>
```

contra un manuscrito real y confirmar en el dashboard de Langfuse (`http://localhost:3000`) que aparece **una** traza `extraction.characters` con `manuscript_id`/`model`/`prompt_version`/`schema_version` en su metadata, y las llamadas LLM de sus escenas anidadas debajo (capa 1, callback nativo). No es un gate — es verificación manual, análoga a la de M0-M3 con manuscritos reales.

- [ ] **Step 5: Commit**

```bash
git add .env.example README.md
git commit -m "docs: document Langfuse observability (backend/observability/, opt-in)"
```

---

## Self-Review

**Cobertura del objetivo (ADR-0003):**

| Objetivo del ADR | Task |
|---|---|
| Callback nativo aislado en `backend/llm/` | 3 |
| Puerta única fuera de `backend/llm/` (`backend/observability/`) | 1 |
| Metadata cruzable con la clave de cache (`model`/`PROMPT_VERSION`/`SCHEMA_VERSION`) | 2, 4 |
| Anidado por manuscrito en las tres pipelines | 4 |
| Eval/CI nunca dependen de Langfuse | 5 |
| Fail-open ante Langfuse caído, no instalado, o SDK con API distinta | 1, 3 |
| Self-hosted, opt-in, sin chocar con Neo4j | 6 |
| Documentación no miente | 7 |

**Correcciones aplicadas respecto al mini-plan de alto nivel** (`docs/adr/0003-langfuse-observability.md` §Notas), tras verificar contra el código real:
- La referencia a "líneas 534-536" de `eval/seed.py` era incorrecta — el archivo real tiene 179 líneas; el punto de aislamiento correcto es `_use_frozen_cache()` (líneas 53-55), corregido en Task 5.
- Los runners de eval (`eval/{characters,relations,attributes}/runner.py`) NO instancian `LiteLLMClient` — son de solo lectura del grafo. Solo `eval/seed.py` lo hace. Task 5 ya no toca los runners.
- El mini-plan no contemplaba que `model`/`prompt_version`/`schema_version` son atributos **privados** de las clases Cache (`_model`, `_prompt_version`, `_schema_version`, sin properties públicas). Se añadió Task 2 (no estaba en el mini-plan) para exponerlos sin que Task 4 tenga que alcanzar atributos privados desde otro módulo.
- El paquete Python `langfuse` no estaba instalado ni en `pyproject.toml`/`uv.lock` (litellm lo importa de forma lazy dentro de su integración, confirmado por grep en el código instalado). Se añadió como Step 1 de Task 1, con verificación explícita de que expone `observe`/`get_client` antes de continuar.

**Orden y dependencias:** 1 y 2 son independientes entre sí y prerequisito de 4. 3 es independiente de 1/2/4 (capa separada a propósito, ver ADR). 5 es independiente de 1-4 (toca solo `eval/seed.py`) pero debe cerrarse antes de dar el ADR por "implementado" — es la mitigación del riesgo declarado. 6 es infraestructura pura, independiente del código, puede adelantarse en paralelo con cualquier task. 7 al final, cuando 1-6 ya existen para documentarlos con precisión.

**Lo que este plan NO hace** (idéntico al mini-plan, confirmado que sigue aplicando):
- No instrumenta el eval harness con trazas propias — decisión explícita del ADR, no un olvido.
- No cambia la firma de `LLMClient.complete_structured` ni de las tres `run_*_pipeline`.
- No decide dónde vive el dashboard de Langfuse en un despliegue de producción real — el proyecto no tiene despliegue fuera de `docker compose` todavía.
- No backfillea cobertura de test unitaria completa para `AttributesCache` ni para `run_attributes_pipeline` más allá de lo que este plan añade — ese backlog pertenece a M3, no a este ADR cross-cutting.
