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
