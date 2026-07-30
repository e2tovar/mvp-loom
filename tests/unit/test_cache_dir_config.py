"""La raíz de las cachés LLM es configurable por entorno (LOOM_CACHE_DIR).

Necesario para que el sembrador del eval escriba/lea en el directorio versionado
(eval/fixtures/llm-cache) sin tocar los tres CLIs de extracción.
"""

from __future__ import annotations

import pytest

from backend.llm.cache import AttributesCache, ExtractionCache, RelationsCache

CACHES = [
    (ExtractionCache, "extraction"),
    (RelationsCache, "relations"),
    (AttributesCache, "attributes"),
]


@pytest.mark.parametrize(("cls", "subdir"), CACHES)
def test_default_root_is_dot_cache(cls, subdir, monkeypatch, tmp_path):
    """Sin LOOM_CACHE_DIR, la raíz sigue siendo .cache/<subdir> (compatibilidad)."""
    monkeypatch.delenv("LOOM_CACHE_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    c = cls(prompt_version=1, schema_version=1, model="m")
    assert c.dir == (tmp_path / ".cache" / subdir).resolve()


@pytest.mark.parametrize(("cls", "subdir"), CACHES)
def test_env_var_moves_the_root(cls, subdir, monkeypatch, tmp_path):
    """Con LOOM_CACHE_DIR, cada caché cuelga su subdirectorio de esa raíz."""
    root = tmp_path / "frozen"
    monkeypatch.setenv("LOOM_CACHE_DIR", str(root))
    c = cls(prompt_version=1, schema_version=1, model="m")
    assert c.dir == (root / subdir).resolve()
    assert c.dir.is_dir(), "el directorio se crea al instanciar"


@pytest.mark.parametrize(("cls", "subdir"), CACHES)
def test_explicit_cache_dir_wins_over_env(cls, subdir, monkeypatch, tmp_path):
    """El parámetro explícito tiene prioridad: los tests que lo pasan no cambian."""
    monkeypatch.setenv("LOOM_CACHE_DIR", str(tmp_path / "ignorado"))
    explicit = tmp_path / "explicito"
    c = cls(prompt_version=1, schema_version=1, model="m", cache_dir=explicit)
    assert c.dir == explicit.resolve()


def test_env_var_is_read_at_instantiation_not_at_import(monkeypatch, tmp_path):
    """Leer en runtime, no a nivel de módulo: el sembrador la fija antes de instanciar."""
    first = tmp_path / "a"
    monkeypatch.setenv("LOOM_CACHE_DIR", str(first))
    assert ExtractionCache(prompt_version=1, schema_version=1, model="m").dir == (
        first / "extraction"
    ).resolve()

    second = tmp_path / "b"
    monkeypatch.setenv("LOOM_CACHE_DIR", str(second))
    assert ExtractionCache(prompt_version=1, schema_version=1, model="m").dir == (
        second / "extraction"
    ).resolve()
