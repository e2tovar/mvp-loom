# Que los gates de eval no se salten solos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que "suite en verde" signifique "los tres milestones siguen midiendo lo que medían", en vez de "no había datos y los exámenes se omitieron".

**Architecture:** Hoy los tres gates (`tests/eval/test_{characters,relations,attributes}_gate.py`) hacen `pytest.skip` si el grafo no tiene la extracción sembrada, y sembrarla cuesta llamadas de pago al LLM. El plan corta esa dependencia congelando en el repo las respuestas del LLM de las 4 obras crafted (21 escenas en total), de modo que sembrar el grafo pase a ser determinista y gratuito. Con eso ya es defendible un modo estricto que convierta cada `skip` en `fail`, y un CI que lo ejecute sin secretos de API.

Lo que se congela es **solo** la respuesta del modelo a "qué ves en esta escena". Resolución de entidades, agregación, escritura al grafo y cálculo de métricas siguen ejecutándose de verdad en cada corrida — que es donde han vivido casi todos los bugs reales del proyecto (ver `docs/known-issues.md`, cascada de resolución por apellido).

**Tech Stack:** Python 3.12, pytest, Neo4j 5.x vía driver oficial, LiteLLM como única puerta al LLM, `uv` como gestor. GitHub Actions para el CI (repo: `e2tovar/mvp-loom`).

## Global Constraints

Copiados de la constitución del proyecto (`README.md` §11 y §13) y del estado verificado del repo el 2026-07-30:

- **Principio II — el grafo es la única fuente de verdad.** El sembrador escribe en Neo4j vía `backend/graph/`; no introduce un segundo store.
- **Una sola puerta al LLM.** Nada de SDKs nuevos: todo pasa por `backend/llm/`.
- **Cypher revisable.** Las consultas viven en `backend/graph/` con nombre. El sembrador NO incrusta Cypher propio; reutiliza `write_raw_layer` y los pipelines existentes.
- **Eval antes de merge.** El README ya lo declara; hoy es falso porque no existe `.github/workflows/`. Este plan lo hace cierto.
- **Idempotencia.** Re-ejecutar el sembrador sobre un grafo ya sembrado no debe duplicar nada ni gastar llamadas.
- **Modelo del gate:** `openai/kimi-k2.5` (`.env:13`). La clave de caché incluye el modelo, así que cambiar de modelo invalida lo congelado — comportamiento deseado.
- **Versiones vigentes al congelar:** `PROMPT_VERSION` de M1 = 4, `SCHEMA_VERSION` de M1 = 3. Cambiarlas invalida la caché y obliga a re-medir pagando. También deseado.
- **Aislamiento de la base (crítico).** Neo4j Community expone una sola base compartida con los datos reales de desarrollo. Ninguna operación de este plan puede borrar sin filtrar por `manuscript_id` — ver `docs/known-issues.md`, follow-up 1 de M1 (una regresión ahí destruyó la capa cruda de todos los libros tres veces en una sesión).

## Datos verificados durante el research (no re-derivar)

| Dato | Valor | Cómo se comprobó |
|---|---|---|
| Obras del gate y sus escenas | `crafted-three-chapters.txt` 6 · `crafted-two-chapters.epub` 3 · `crafted-relations.txt` 4 · `crafted-attributes.txt` 2 | `parse_manuscript` sobre cada fixture |
| Texto total de las 4 obras | 5 459 bytes | `wc -c` |
| Llamadas al LLM para congelar todo | **21** = 15 (M1, las 4 obras) + 4 (M2, `crafted-relations`) + 2 (M3, `crafted-attributes`) | Recuento de escenas por obra y por milestone |
| Escenas crafted ya en caché con prompt v4 / schema v3 | **0 de 15** | SHA-256 de `scene_text + "4" + "openai/kimi-k2.5" + "3"` contra `.cache/extraction/`. Las 340 entradas existentes son de las novelas y/o de versiones de prompt anteriores |
| El texto de `Scene.text` en la base es idéntico al que produce `parse_manuscript` | Sí | Comparado escena a escena ordenando por `c.order_narrative, sc.order_narrative` (ordenar solo por `sc.order_narrative` da resultados arbitrarios: es el orden **dentro** del capítulo, no global) |
| CI existente | Ninguno: no hay `.github/`, ni `Makefile`, ni `scripts/` | `ls` |
| Las tres clases de caché aceptan `cache_dir` | Sí, pero los tres CLIs no lo pasan (`backend/extraction/run.py:63`, `relations/run.py:65`, `attributes/run.py:63`) | `grep` de las instanciaciones |
| `eval/fixtures/` está versionado | Sí; `.gitignore` solo excluye `.cache/` (línea 21) y `eval/.cache/` (línea 66) | `git check-ignore` |
| `tests/eval/` no es paquete Python | No tiene `__init__.py` ni `conftest.py`; `tests/` sí tiene `__init__.py` | `test -f` |

## Riesgo conocido que este plan cristaliza (no introduce)

La clave de la caché de M1 es `SHA-256(scene_text + prompt_version + model + schema_version)` — **no incluye `known_entities`**, aunque el prompt sí recibe el registro de entidades acumulado y la respuesta del modelo depende de él (`backend/llm/cache.py:38-45` frente a `backend/extraction/pipeline.py:173-177`). Las cachés de M2 y M3 sí incluyen el fingerprint del cast (`cache.py:97`, `cache.py:155`).

Efecto de congelar: la asimetría deja de producir variación (bueno — el gate se vuelve determinista), pero queda cristalizada una respuesta generada con un registro de entidades concreto. No lo arregla este plan. **Registrar como deuda en Task 7**, no cambiar la clave aquí: cambiarla invalidaría toda la caché de las novelas y obligaría a re-medir M1 pagando, que es una decisión aparte.

## File Structure

**Nuevos:**
- `eval/strict.py` — decide `skip` vs `fail`. Vive en `eval/` (el paquete del harness, importable: los gates ya hacen `from eval.attributes.runner import run_eval`), no en `tests/`, porque `tests/eval/` no es paquete.
- `eval/seed.py` — sembrador determinista: ingiere las 4 obras y ejecuta M1/M2/M3 sobre ellas.
- `eval/fixtures/llm-cache/{extraction,relations,attributes}/` — las respuestas congeladas, versionadas.
- `tests/unit/test_cache_dir_config.py` — que la raíz de caché sea configurable.
- `tests/unit/test_eval_strict.py` — que el modo estricto convierta skip en fallo.
- `Makefile` — un solo comando de verificación, reutilizable por el CI.
- `.github/workflows/ci.yml` — Task 6, aprobable por separado.

**Modificados:**
- `backend/llm/cache.py:19,73,131` — los tres directorios por defecto pasan a derivarse de `LOOM_CACHE_DIR`.
- `tests/eval/test_characters_gate.py`, `test_relations_gate.py`, `test_attributes_gate.py` — sus `pytest.skip` pasan por el helper.
- `README.md` §13, `docs/known-issues.md`, `docs/superpowers/specs/*/quickstart.md` — Task 7.

---

### Task 1: Raíz de caché configurable por entorno

Sin esto, el sembrador no puede escribir en el directorio versionado sin tocar los tres CLIs. Un solo punto de cambio en `backend/llm/cache.py`.

**Files:**
- Modify: `backend/llm/cache.py:19` (`_CACHE_DIR`), `:73` (`_RELATIONS_CACHE_DIR`), `:131` (`_ATTRIBUTES_CACHE_DIR`), y los tres `__init__`
- Test: `tests/unit/test_cache_dir_config.py`

**Interfaces:**
- Consumes: nada.
- Produces: `LOOM_CACHE_DIR` (variable de entorno, default `.cache`). `ExtractionCache`, `RelationsCache` y `AttributesCache` conservan su firma actual — `(prompt_version: int, schema_version: int, model: str, cache_dir: Path | None = None)`; el parámetro explícito `cache_dir` sigue teniendo prioridad sobre la variable de entorno.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cache_dir_config.py
"""La raíz de las cachés LLM es configurable por entorno (LOOM_CACHE_DIR).

Necesario para que el sembrador del eval escriba/lea en el directorio versionado
(eval/fixtures/llm-cache) sin tocar los tres CLIs de extracción.
"""

from __future__ import annotations

from pathlib import Path

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_cache_dir_config.py -v`

Expected: FAIL. Todos con `AttributeError: 'ExtractionCache' object has no attribute 'dir'` — hoy el directorio es el privado `self._dir`. El test exige exponerlo como `dir` (solo lectura) porque el sembrador y el CI necesitan poder afirmar dónde está escribiendo.

- [ ] **Step 3: Write minimal implementation**

En `backend/llm/cache.py`, sustituir las tres constantes de módulo por una función y añadir la propiedad pública. Reemplazar la línea 19 (`_CACHE_DIR = Path(".cache") / "extraction"`) por:

```python
_CACHE_ROOT_ENV = "LOOM_CACHE_DIR"
_DEFAULT_CACHE_ROOT = Path(".cache")


def _cache_root() -> Path:
    """Raíz de las cachés LLM, configurable por entorno.

    Se lee en cada instanciación (no al importar) para que el sembrador del eval
    pueda apuntar a `eval/fixtures/llm-cache` sin tocar los CLIs de extracción.
    """
    import os

    raw = os.environ.get(_CACHE_ROOT_ENV)
    return Path(raw) if raw else _DEFAULT_CACHE_ROOT
```

En los tres `__init__`, cambiar la línea que resuelve el directorio. En `ExtractionCache.__init__` (hoy `self._dir = (cache_dir or _CACHE_DIR).resolve()`):

```python
        self._dir = (cache_dir or _cache_root() / "extraction").resolve()
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def dir(self) -> Path:
        """Directorio donde esta caché lee y escribe (solo lectura)."""
        return self._dir
```

En `RelationsCache.__init__`, idéntico con `"relations"`; en `AttributesCache.__init__`, con `"attributes"`. Añadir la misma propiedad `dir` a las tres clases. Borrar `_RELATIONS_CACHE_DIR` (línea 73) y `_ATTRIBUTES_CACHE_DIR` (línea 131): quedan sin uso, y dejarlas invita a que alguien las use y se salte la variable de entorno.

Actualizar el docstring del módulo (línea 4, `Store: JSON en .cache/extraction/<hex>.json (gitignored)`):

```
Store: JSON en <LOOM_CACHE_DIR o .cache>/{extraction,relations,attributes}/<hex>.json
       Por defecto gitignored; el eval apunta LOOM_CACHE_DIR a un directorio
       versionado (eval/fixtures/llm-cache) para que sus gates no dependan de
       llamadas de pago.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_cache_dir_config.py -v`
Expected: PASS (10 tests).

Comprobar que no se rompió nada que usara las constantes borradas:

Run: `grep -rn "_RELATIONS_CACHE_DIR\|_ATTRIBUTES_CACHE_DIR\|_CACHE_DIR" backend/ tests/ eval/`
Expected: solo `_CACHE_ROOT_ENV` y `_DEFAULT_CACHE_ROOT` en `backend/llm/cache.py`.

Run: `.venv/bin/python -m pytest tests/unit tests/extraction -q`
Expected: PASS, sin regresiones.

- [ ] **Step 5: Commit**

```bash
git add backend/llm/cache.py tests/unit/test_cache_dir_config.py
git commit -m "feat(llm): configurable cache root via LOOM_CACHE_DIR

Los gates de eval necesitan leer respuestas LLM congeladas desde un
directorio versionado sin que los CLIs de extracción sepan nada de ello."
```

---

### Task 2: Modo estricto — que el skip pueda ser un fallo

**Files:**
- Create: `eval/strict.py`
- Test: `tests/unit/test_eval_strict.py`
- Modify: `tests/eval/test_characters_gate.py:91,95,99,104`, `tests/eval/test_relations_gate.py:56,58,62,64`, `tests/eval/test_attributes_gate.py:63,67,70,72`

**Interfaces:**
- Consumes: nada.
- Produces: `eval.strict.skip_or_fail(reason: str) -> NoReturn` — lanza `pytest.fail` si `LOOM_EVAL_STRICT` está a `"1"`, y `pytest.skip` en cualquier otro caso. También `eval.strict.is_strict() -> bool` para mensajes.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_eval_strict.py
"""El modo estricto convierte los skips de los gates en fallos.

En local un gate se omite si no hay extracción sembrada (extraer cuesta cuota
LLM). En CI eso es inaceptable: la suite pasaría en verde sin haber medido nada.
LOOM_EVAL_STRICT=1 invierte la política.
"""

from __future__ import annotations

import pytest

from eval.strict import is_strict, skip_or_fail


def test_default_is_lenient_and_skips(monkeypatch):
    monkeypatch.delenv("LOOM_EVAL_STRICT", raising=False)
    assert is_strict() is False
    with pytest.raises(pytest.skip.Exception) as exc:
        skip_or_fail("M1 sin ejecutar")
    assert "M1 sin ejecutar" in str(exc.value)


def test_strict_mode_fails_instead_of_skipping(monkeypatch):
    monkeypatch.setenv("LOOM_EVAL_STRICT", "1")
    assert is_strict() is True
    with pytest.raises(pytest.fail.Exception) as exc:
        skip_or_fail("M1 sin ejecutar")
    msg = str(exc.value)
    assert "M1 sin ejecutar" in msg
    assert "LOOM_EVAL_STRICT" in msg, "el fallo debe decir por qué no se omitió"


@pytest.mark.parametrize("value", ["0", "", "false", "no", "true", "yes"])
def test_only_the_exact_string_1_enables_strict(monkeypatch, value):
    """Sin adivinar booleanos: solo "1" activa. Un typo no debe apagar el gate
    en silencio ni activarlo por accidente."""
    monkeypatch.setenv("LOOM_EVAL_STRICT", value)
    assert is_strict() is False
    with pytest.raises(pytest.skip.Exception):
        skip_or_fail("cualquier motivo")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_eval_strict.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'eval.strict'`.

- [ ] **Step 3: Write minimal implementation**

```python
# eval/strict.py
"""Política de omisión de los gates de eval.

En local, un gate se omite si el grafo no tiene la extracción sembrada: extraer
cuesta cuota LLM y no queremos pagarla en cada corrida de tests. En CI esa misma
política es un agujero — la suite pasaría en verde sin haber medido nada.

`LOOM_EVAL_STRICT=1` invierte la política: cada motivo de omisión pasa a ser un
fallo. El CI lo activa; el sembrador (`eval/seed.py`) deja el grafo en el estado
que hace innecesaria la omisión.

Ver docs/known-issues.md → "M3 · Follow-ups", punto 4.
"""

from __future__ import annotations

import os
from typing import NoReturn

STRICT_ENV = "LOOM_EVAL_STRICT"


def is_strict() -> bool:
    """True si el modo estricto está activo (exactamente `LOOM_EVAL_STRICT=1`)."""
    return os.environ.get(STRICT_ENV) == "1"


def skip_or_fail(reason: str) -> NoReturn:
    """Omite el gate, o lo hace fallar si el modo estricto está activo."""
    import pytest

    if is_strict():
        pytest.fail(
            f"{reason}\n"
            f"[{STRICT_ENV}=1] En modo estricto un gate no puede omitirse: "
            f"siembra el grafo con `python -m eval.seed` y vuelve a ejecutar."
        )
    pytest.skip(reason)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_eval_strict.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Cablear los tres gates**

En los tres archivos, añadir el import y sustituir cada `pytest.skip(...)` por `skip_or_fail(...)`. Los `pytest.skip` a sustituir son:

- `tests/eval/test_characters_gate.py`: línea 91 (Neo4j no disponible), 95 (gold no encontrado), 99-102 (extracción no ejecutada), 104 (capa cruda destruida).
- `tests/eval/test_relations_gate.py`: línea 56 (Neo4j), 58 (gold), 62 (M1 sin ejecutar), 64-66 (M2 sin ejecutar).
- `tests/eval/test_attributes_gate.py`: línea 63 (Neo4j), 67 (gold), 70 (M1 sin ejecutar), 71-74 (M3 sin ejecutar).

En cada archivo, junto a los imports de nivel de módulo:

```python
from eval.strict import skip_or_fail
```

Y cada llamada pasa de `pytest.skip("...")` a `skip_or_fail("...")`, conservando el mensaje literal. Ejemplo, en `test_attributes_gate.py`:

```python
    if not _neo4j_available():
        skip_or_fail("Neo4j no disponible — docker compose up para el gate")
```

No tocar los `@pytest.mark.eval` ni los `@pytest.mark.parametrize`. `pytest` sigue importándose en los tres archivos porque los markers lo usan.

- [ ] **Step 6: Verify — el modo estricto falla cuando debe y pasa cuando debe**

Con Neo4j **apagado** (`docker compose down`), en modo estricto los tres gates deben fallar, no omitirse:

Run: `LOOM_EVAL_STRICT=1 .venv/bin/python -m pytest tests/eval -q --tb=line`
Expected: FAIL. Al menos 4 fallos con "Neo4j no disponible" y el aviso de `LOOM_EVAL_STRICT=1`. **Cero omitidos** entre los gates.

Sin modo estricto, mismo estado, debe omitir como siempre:

Run: `.venv/bin/python -m pytest tests/eval -q -rs`
Expected: PASS con omitidos.

Con Neo4j **levantado** (`docker compose up -d`, esperar conectividad) y sin sembrar todavía, el modo estricto debe seguir fallando pero ahora por falta de extracción:

Run: `LOOM_EVAL_STRICT=1 .venv/bin/python -m pytest tests/eval -q --tb=line`
Expected: FAIL mencionando "M1 sin ejecutar" para las obras no sembradas. Esto es la prueba de que el agujero existía: es exactamente lo que hoy pasa desapercibido.

- [ ] **Step 7: Commit**

```bash
git add eval/strict.py tests/unit/test_eval_strict.py tests/eval/test_characters_gate.py tests/eval/test_relations_gate.py tests/eval/test_attributes_gate.py
git commit -m "feat(eval): LOOM_EVAL_STRICT turns gate skips into failures

Los tres gates se omitían si el grafo no tenía extracción sembrada, así que
una base limpia daba suite verde sin haber medido nada."
```

---

### Task 3: Sembrador determinista del grafo

Un comando que deja el grafo en el estado exacto que los tres gates necesitan. Idempotente y sin Cypher propio: reutiliza `write_raw_layer` y los pipelines de M1/M2/M3.

**Files:**
- Create: `eval/seed.py`
- Test: `tests/integration/test_eval_seed.py`

**Interfaces:**
- Consumes: `LOOM_CACHE_DIR` (Task 1). `backend.ingest.pipeline.parse_manuscript(path: Path, source_format: str) -> Manuscript`; `backend.graph.raw_layer.write_raw_layer(sess, m) -> None` y `manuscript_exists(sess, manuscript_id) -> bool`; `backend.graph.schema.apply_schema(sess) -> None`; `backend.extraction.pipeline.run_pipeline`, `backend.extraction.relations.pipeline.run_relations_pipeline`, `backend.extraction.attributes.pipeline.run_attributes_pipeline`.
- Produces: `eval.seed.GATE_WORKS: tuple[SeedWork, ...]` y `eval.seed.seed_all(force: bool = False) -> dict[str, str]` (obra → `manuscript_id`). `SeedWork` es un dataclass con `filename: str`, `source_format: str`, `layers: tuple[str, ...]` (subconjunto de `("m1", "m2", "m3")`).

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_eval_seed.py
"""El sembrador deja el grafo en el estado que los gates necesitan.

Requiere Neo4j. NO requiere cuota LLM si las respuestas congeladas están
presentes (eval/fixtures/llm-cache) — que es justamente lo que se verifica.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_gate_works_cover_the_three_milestones():
    """El catálogo declara qué capa necesita cada obra. Puro, sin base."""
    from eval.seed import GATE_WORKS

    by_name = {w.filename: w for w in GATE_WORKS}
    assert set(by_name) == {
        "crafted-three-chapters.txt",
        "crafted-two-chapters.epub",
        "crafted-relations.txt",
        "crafted-attributes.txt",
    }
    # M1 en las cuatro; M2 solo en la obra de relaciones; M3 solo en la de atributos.
    assert all("m1" in w.layers for w in GATE_WORKS)
    assert by_name["crafted-relations.txt"].layers == ("m1", "m2")
    assert by_name["crafted-attributes.txt"].layers == ("m1", "m3")
    assert by_name["crafted-three-chapters.txt"].layers == ("m1",)


def test_seed_all_leaves_every_gate_layer_present(neo4j_session):
    """Tras sembrar, los checkers que usan los gates dicen que hay datos."""
    from backend.graph import attributes as attr_graph
    from backend.graph import characters as char_graph
    from backend.graph import relations as rel_graph
    from eval.seed import seed_all

    ids = seed_all()
    assert len(ids) == 4

    with neo4j_session as sess:  # la fixture ya entrega una sesión abierta
        for name, mid in ids.items():
            assert char_graph.has_extraction(sess, mid), f"M1 ausente en {name}"
        assert rel_graph.has_relations(sess, ids["crafted-relations.txt"])
        assert attr_graph.has_attributes(sess, ids["crafted-attributes.txt"])


def test_seed_is_idempotent_and_spends_no_llm_calls_on_rerun(neo4j_session):
    """Segunda corrida: todo sale de la caché, cero llamadas nuevas."""
    from eval.seed import seed_all

    first = seed_all()
    second = seed_all()
    assert first == second, "los manuscript_id son hashes de contenido: estables"


def test_seed_does_not_touch_manuscripts_outside_the_gate(neo4j_session):
    """Guard de aislamiento: sembrar no borra ni altera obras reales.

    Ver docs/known-issues.md → follow-up 1 de M1: un borrado sin scope destruyó
    la capa cruda de todos los libros tres veces en una sesión.
    """
    from backend.graph import raw_layer
    from eval.seed import seed_all

    sess = neo4j_session
    sess.run(
        "CREATE (m:Manuscript {manuscript_id: $mid, title: $t})",
        mid="test-seed-bystander",
        t="No me toques",
    )
    seed_all()
    assert raw_layer.manuscript_exists(sess, "test-seed-bystander")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/integration/test_eval_seed.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'eval.seed'`.

- [ ] **Step 3: Write minimal implementation**

```python
# eval/seed.py
"""Siembra el grafo con lo que los gates de eval necesitan medir.

python -m eval.seed [--force]

Determinista y sin coste: apunta LOOM_CACHE_DIR a las respuestas LLM congeladas
(eval/fixtures/llm-cache), así que las 21 escenas de las 4 obras crafted salen de
disco en vez de la API. Si falta una entrada — porque cambió PROMPT_VERSION, el
esquema o el modelo — el pipeline llamará al LLM de verdad y hará falta
LOOM_LLM_API_KEY. Eso es deliberado: cambiar el prompt obliga a re-medir.

Idempotente: los manuscript_id son hashes de contenido y los pipelines cachean,
así que re-ejecutar no duplica nodos ni gasta cuota.

NUNCA borra nada. Solo escribe las obras del gate; cualquier otro manuscrito del
grafo queda intacto (ver docs/known-issues.md → follow-up 1 de M1).
"""

from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
FROZEN_CACHE_DIR = FIXTURES_DIR / "llm-cache"

log = logging.getLogger("eval.seed")


@dataclass(frozen=True)
class SeedWork:
    """Una obra del gate y las capas de extracción que sus gates exigen."""

    filename: str
    source_format: str
    layers: tuple[str, ...]


# Qué mide cada gate (verificado 2026-07-30):
#   test_characters_gate  → crafted-three-chapters.txt, crafted-two-chapters.epub
#   test_relations_gate   → crafted-relations.txt   (necesita M1 antes)
#   test_attributes_gate  → crafted-attributes.txt  (necesita M1 antes)
GATE_WORKS: tuple[SeedWork, ...] = (
    SeedWork("crafted-three-chapters.txt", "txt", ("m1",)),
    SeedWork("crafted-two-chapters.epub", "epub", ("m1",)),
    SeedWork("crafted-relations.txt", "txt", ("m1", "m2")),
    SeedWork("crafted-attributes.txt", "txt", ("m1", "m3")),
)


def _use_frozen_cache() -> None:
    """Apunta las cachés LLM al directorio versionado, si no se fijó otra raíz."""
    os.environ.setdefault("LOOM_CACHE_DIR", str(FROZEN_CACHE_DIR))


def _ingest(work: SeedWork) -> str:
    """Escribe la capa cruda de la obra y devuelve su manuscript_id."""
    from backend.graph import raw_layer
    from backend.graph import schema
    from backend.graph.client import session as db_session
    from backend.ingest.pipeline import parse_manuscript

    manuscript = parse_manuscript(FIXTURES_DIR / work.filename, work.source_format)
    with db_session() as sess:
        schema.apply_schema(sess)
        # write_raw_layer hace MERGE por manuscript_id: idempotente, no borra.
        raw_layer.write_raw_layer(sess, manuscript)
    return manuscript.manuscript_id


def _extract(work: SeedWork, manuscript_id: str, force: bool) -> None:
    """Ejecuta las capas M1/M2/M3 que esta obra necesita, en orden."""
    from backend.extraction.attributes.prompts import (
        PROMPT_VERSION as ATTR_PROMPT_VERSION,
    )
    from backend.extraction.attributes.schemas import (
        SCHEMA_VERSION as ATTR_SCHEMA_VERSION,
    )
    from backend.extraction.prompts import PROMPT_VERSION as M1_PROMPT_VERSION
    from backend.extraction.relations.prompts import (
        PROMPT_VERSION as REL_PROMPT_VERSION,
    )
    from backend.extraction.relations.schemas import (
        SCHEMA_VERSION as REL_SCHEMA_VERSION,
    )
    from backend.extraction.schemas import SCHEMA_VERSION as M1_SCHEMA_VERSION
    from backend.llm.cache import AttributesCache, ExtractionCache, RelationsCache
    from backend.llm.litellm_client import LiteLLMClient

    model = os.environ.get("LOOM_LLM_MODEL", "unknown")
    llm = LiteLLMClient()

    if "m1" in work.layers:
        from backend.extraction.pipeline import run_pipeline

        cache = ExtractionCache(
            prompt_version=M1_PROMPT_VERSION,
            schema_version=M1_SCHEMA_VERSION,
            model=model,
        )
        res = run_pipeline(
            manuscript_id=manuscript_id, llm_client=llm, cache=cache, force=force
        )
        log.info(
            "%s · M1: %d escenas, %d cache hits", work.filename,
            res.scenes_processed, res.cache_hits,
        )

    if "m2" in work.layers:
        from backend.extraction.relations.pipeline import run_relations_pipeline

        cache = RelationsCache(
            prompt_version=REL_PROMPT_VERSION,
            schema_version=REL_SCHEMA_VERSION,
            model=model,
        )
        res = run_relations_pipeline(
            manuscript_id=manuscript_id, llm_client=llm, cache=cache, force=force
        )
        log.info(
            "%s · M2: %d escenas, %d cache hits", work.filename,
            res.scenes_processed, res.cache_hits,
        )

    if "m3" in work.layers:
        from backend.extraction.attributes.pipeline import run_attributes_pipeline

        cache = AttributesCache(
            prompt_version=ATTR_PROMPT_VERSION,
            schema_version=ATTR_SCHEMA_VERSION,
            model=model,
        )
        res = run_attributes_pipeline(
            manuscript_id=manuscript_id, llm_client=llm, cache=cache, force=force
        )
        log.info(
            "%s · M3: %d escenas, %d cache hits", work.filename,
            res.scenes_processed, res.cache_hits,
        )


def seed_all(force: bool = False) -> dict[str, str]:
    """Siembra las 4 obras del gate. Devuelve {filename: manuscript_id}."""
    from dotenv import load_dotenv

    load_dotenv()
    _use_frozen_cache()

    ids: dict[str, str] = {}
    for work in GATE_WORKS:
        mid = _ingest(work)
        _extract(work, mid, force)
        ids[work.filename] = mid
    return ids


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    p = argparse.ArgumentParser(description="Siembra el grafo para los gates de eval.")
    p.add_argument(
        "--force",
        action="store_true",
        help="Ignora la caché y re-extrae (CUESTA CUOTA LLM: 21 llamadas).",
    )
    args = p.parse_args()

    ids = seed_all(force=args.force)
    print(f"\n{'─' * 60}")
    for name, mid in ids.items():
        print(f"  {name:32s} {mid[:16]}…")
    print(f"  Caché LLM: {os.environ.get('LOOM_CACHE_DIR')}")
    print(f"{'─' * 60}\n")


if __name__ == "__main__":
    main()
```

**Nota para el implementador:** las firmas de `run_relations_pipeline` y `run_attributes_pipeline` deben confirmarse antes de escribir esto. Comprobar con `grep -n "def run_relations_pipeline" -A 10 backend/extraction/relations/pipeline.py` y el equivalente de atributos, y ajustar los nombres de parámetros y los campos del resultado (`scenes_processed`, `cache_hits`) a lo que realmente exponen. El CLI de atributos (`backend/extraction/attributes/run.py:71-74`) los llama con `manuscript_id=`, `llm_client=`, `cache=`, `force=` — usar eso como referencia y verificar el de relaciones en `backend/extraction/relations/run.py`.

- [ ] **Step 4: Run test to verify it passes**

Levantar Neo4j primero: `docker compose up -d` y esperar conectividad.

Run: `.venv/bin/python -m pytest tests/integration/test_eval_seed.py -v`
Expected: PASS (4 tests). En esta primera corrida **sí habrá llamadas al LLM** (la caché congelada aún no existe: se genera en Task 4), así que hace falta `LOOM_LLM_API_KEY` en `.env` y tardará. Si el objetivo es solo validar el código sin gastar, ejecutar primero `test_gate_works_cover_the_three_milestones`, que es puro.

- [ ] **Step 5: Commit**

```bash
git add eval/seed.py tests/integration/test_eval_seed.py
git commit -m "feat(eval): deterministic graph seeder for the three gates

Reutiliza write_raw_layer y los pipelines M1/M2/M3; nunca borra nada y no
incrusta Cypher propio. Apunta la caché LLM al directorio congelado."
```

---

### Task 4: Generar y congelar las respuestas del LLM

Única task con coste de API: 21 llamadas sobre 5 459 bytes de texto. A partir de aquí, sembrar es gratis en cualquier máquina.

**Files:**
- Create: `eval/fixtures/llm-cache/{extraction,relations,attributes}/*.json` (generados)
- Create: `eval/fixtures/llm-cache/README.md`
- Modify: `.gitignore` (excepción para el directorio congelado)
- Test: `tests/eval/test_frozen_cache.py`

**Interfaces:**
- Consumes: `eval.seed.seed_all` y `GATE_WORKS` (Task 3), `LOOM_CACHE_DIR` (Task 1).
- Produces: el directorio `eval/fixtures/llm-cache/` versionado.

- [ ] **Step 1: Comprobar que .gitignore no excluye el directorio congelado**

Run: `git check-ignore -v eval/fixtures/llm-cache`
Expected: sin salida (no ignorado). Verificado el 2026-07-30: `.gitignore` solo excluye `.cache/` (línea 21) y `eval/.cache/` (línea 66), ninguna afecta a esta ruta. **Si esta comprobación diera salida**, añadir `!eval/fixtures/llm-cache/` al final de `.gitignore` y volver a comprobar.

- [ ] **Step 2: Write the failing test**

```python
# tests/eval/test_frozen_cache.py
"""Las respuestas LLM congeladas están completas y son las que los gates usarán.

Este test es la red que evita el peor fallo silencioso del enfoque: que falte una
entrada, el pipeline llame al LLM sin que nadie se dé cuenta, y el gate deje de
ser determinista (o falle en CI, donde no hay clave de API).

Puro: no necesita Neo4j ni cuota LLM. Solo calcula claves y mira el disco.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "eval" / "fixtures"
FROZEN = FIXTURES_DIR / "llm-cache"
MODEL = "openai/kimi-k2.5"  # el modelo del gate; la clave de caché lo incluye


def _m1_key(scene_text: str) -> str:
    from backend.extraction.prompts import PROMPT_VERSION
    from backend.extraction.schemas import SCHEMA_VERSION

    raw = scene_text + str(PROMPT_VERSION) + MODEL + str(SCHEMA_VERSION)
    return hashlib.sha256(raw.encode()).hexdigest()


def test_frozen_cache_directory_exists():
    assert FROZEN.is_dir(), (
        f"Falta {FROZEN}. Genéralo con: LOOM_CACHE_DIR={FROZEN} python -m eval.seed"
    )
    for sub in ("extraction", "relations", "attributes"):
        assert (FROZEN / sub).is_dir(), f"Falta el subdirectorio {sub}"


def test_every_m1_scene_of_every_gate_work_is_frozen():
    """Las 15 escenas de M1 (las 4 obras) tienen su respuesta congelada.

    Si este test falla tras cambiar PROMPT_VERSION o el modelo, es correcto que
    falle: hay que re-generar pagando y re-medir. No lo silencies.
    """
    from backend.ingest.pipeline import parse_manuscript

    from eval.seed import GATE_WORKS

    missing: list[str] = []
    total = 0
    for work in GATE_WORKS:
        m = parse_manuscript(FIXTURES_DIR / work.filename, work.source_format)
        for chapter in m.chapters:
            for scene in chapter.scenes:
                total += 1
                path = FROZEN / "extraction" / f"{_m1_key(scene.text)}.json"
                if not path.exists():
                    missing.append(f"{work.filename} · {scene.scene_id}")

    assert total == 15, f"Se esperaban 15 escenas en las 4 obras del gate, hay {total}"
    assert not missing, (
        "Respuestas M1 sin congelar:\n  " + "\n  ".join(missing) +
        f"\nRe-genera con: LOOM_CACHE_DIR={FROZEN} python -m eval.seed"
    )


@pytest.mark.parametrize("sub", ["extraction", "relations", "attributes"])
def test_frozen_entries_are_valid_json_with_content(sub):
    """Ninguna entrada vacía o corrupta: la caché las ignoraría en silencio
    (backend/llm/cache.py captura el error y devuelve None → llamada al LLM)."""
    entries = sorted((FROZEN / sub).glob("*.json"))
    assert entries, f"El subdirectorio {sub} está vacío"
    for path in entries:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict) and data, f"{path.name} vacío o no es objeto"


def test_frozen_cache_stays_small():
    """Guard de tamaño: aquí van solo las 4 obras crafted (5,4 KB de texto), nunca
    las novelas completas — esas son diagnóstico manual, no material del gate."""
    total = sum(p.stat().st_size for p in FROZEN.rglob("*.json"))
    assert total < 2_000_000, (
        f"La caché congelada pesa {total / 1e6:.1f} MB. ¿Se colaron las novelas?"
    )
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/eval/test_frozen_cache.py -v`
Expected: FAIL — `test_frozen_cache_directory_exists` con "Falta …/llm-cache".

- [ ] **Step 4: Generar la caché (paga aquí)**

Requisitos: Neo4j levantado y `LOOM_LLM_API_KEY` + `LOOM_LLM_MODEL=openai/kimi-k2.5` en `.env`.

```bash
docker compose up -d
mkdir -p eval/fixtures/llm-cache/{extraction,relations,attributes}
LOOM_CACHE_DIR=eval/fixtures/llm-cache .venv/bin/python -m eval.seed
```

Expected: 21 llamadas al LLM en total (15 M1 + 4 M2 + 2 M3), `cache hits` a 0 en esta primera corrida. Coste: 5 459 bytes de texto de entrada.

Comprobar que se escribió lo esperado:

```bash
find eval/fixtures/llm-cache -name '*.json' | wc -l   # esperado: 21
du -sh eval/fixtures/llm-cache                        # esperado: decenas de KB
```

Repetir el sembrado para confirmar que ahora es gratis:

```bash
LOOM_CACHE_DIR=eval/fixtures/llm-cache .venv/bin/python -m eval.seed
```

Expected: `cache hits` igual al número de escenas de cada capa, cero llamadas nuevas.

- [ ] **Step 5: Escribir el README del directorio**

```markdown
<!-- eval/fixtures/llm-cache/README.md -->
# Respuestas LLM congeladas (material del gate)

Estas son las respuestas del modelo a "¿qué ves en esta escena?" para las **4
obras crafted** de los gates de eval — 21 escenas, 5 459 bytes de texto. Están
versionadas a propósito, al contrario que `.cache/`.

## Por qué

Sin ellas, sembrar el grafo cuesta llamadas de pago, y por eso los tres gates se
omitían solos en cualquier base limpia: la suite pasaba en verde sin haber medido
nada (`docs/known-issues.md` → "M3 · Follow-ups", punto 4).

## Qué congelan y qué NO

Congelan **solo** la salida del LLM. En cada corrida siguen ejecutándose de verdad
la resolución de entidades, la agregación, la escritura al grafo y el cálculo de
métricas — que es donde han estado casi todos los bugs reales (p. ej. la cascada
que fusionaba `Mrs. Bennet` dentro de `Mr. Bennet`: el modelo devolvía las dos
bien, el fallo era nuestro).

Lo que **no** detectan: que el proveedor cambie el modelo por debajo. Para eso
está la corrida diagnóstica manual sobre novela real.

## Cómo se regeneran

La clave de cada entrada es `SHA-256(texto_escena + PROMPT_VERSION + modelo +
SCHEMA_VERSION)`. Si cambias el prompt, el esquema o el modelo, estas entradas
dejan de acertar y el pipeline volverá a llamar al LLM — deliberado: cambiar el
prompt obliga a re-medir.

```bash
docker compose up -d
LOOM_CACHE_DIR=eval/fixtures/llm-cache python -m eval.seed
```

Modelo con el que se generaron: `openai/kimi-k2.5`. `PROMPT_VERSION` de M1 = 4,
`SCHEMA_VERSION` de M1 = 3 (2026-07-30).

## Qué NO va aquí

Las novelas completas (Orgullo y Prejuicio, Harry Potter 1). Son diagnóstico
manual, no material del gate, y su caché vive en `.cache/` sin versionar.
`tests/eval/test_frozen_cache.py::test_frozen_cache_stays_small` lo vigila.
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/eval/test_frozen_cache.py -v`
Expected: PASS (6 tests).

Prueba de fuego — el sembrado funciona **sin clave de API**. Ese es el objetivo de toda la task:

```bash
docker compose down && docker compose up -d   # base recreada
LOOM_LLM_API_KEY= LOOM_CACHE_DIR=eval/fixtures/llm-cache .venv/bin/python -m eval.seed
```

Expected: termina bien, todo cache hits, cero llamadas. Si falla pidiendo credenciales, falta congelar alguna entrada: `test_every_m1_scene_of_every_gate_work_is_frozen` debería haberlo dicho — revisar por qué no.

Y ahora los tres gates en modo estricto deben pasar:

Run: `LOOM_EVAL_STRICT=1 .venv/bin/python -m pytest tests/eval -q -rs`
Expected: PASS, **cero omitidos**.

- [ ] **Step 7: Commit**

```bash
git add eval/fixtures/llm-cache .gitignore tests/eval/test_frozen_cache.py
git commit -m "feat(eval): freeze LLM responses for the four crafted gate works

21 escenas (5,4 KB de texto). Sembrar el grafo pasa a ser determinista y
gratuito, que es lo que permite exigir los gates sin clave de API."
```

---

### Task 5: Un solo comando de verificación

**Files:**
- Create: `Makefile`
- Test: manual (el Makefile es el propio punto de entrada; probarlo es ejecutarlo)

**Interfaces:**
- Consumes: `eval.seed` (Task 3), `LOOM_EVAL_STRICT` (Task 2), caché congelada (Task 4).
- Produces: `make verify` — ciclo completo que el CI reutiliza tal cual.

- [ ] **Step 1: Write the Makefile**

```makefile
# Makefile — entradas de verificación del proyecto.
# El CI (.github/workflows/ci.yml) llama a estos mismos targets: un solo sitio
# donde vive la definición de "verificado".

PY := .venv/bin/python
FROZEN_CACHE := eval/fixtures/llm-cache

.PHONY: help lint test seed gates verify up down

help:
	@echo "make lint    — ruff sobre backend/ eval/ tests/"
	@echo "make test    — suite completa (integración se omite sin Neo4j)"
	@echo "make seed    — siembra el grafo desde la caché congelada (gratis)"
	@echo "make gates   — los tres gates de eval en modo estricto (fallan si se omitirían)"
	@echo "make verify  — lint + test + seed + gates. Lo que el CI ejecuta."
	@echo "make up/down — arranca/para Neo4j"

up:
	docker compose up -d
	@echo "Esperando a Neo4j…"
	@for i in $$(seq 1 40); do \
		$(PY) -c "from backend.graph import client; client.get_driver().verify_connectivity()" \
			2>/dev/null && echo "Neo4j listo" && exit 0; \
		sleep 3; \
	done; \
	echo "Neo4j no respondió a tiempo" && exit 1

down:
	docker compose down

lint:
	.venv/bin/ruff check backend/ eval/ tests/

test:
	$(PY) -m pytest tests/ -q

seed:
	LOOM_CACHE_DIR=$(FROZEN_CACHE) $(PY) -m eval.seed

gates:
	LOOM_EVAL_STRICT=1 LOOM_CACHE_DIR=$(FROZEN_CACHE) $(PY) -m pytest tests/eval -v -rs

verify: lint test seed gates
	@echo ""
	@echo "verificado: lint, suite, siembra y los tres gates medidos de verdad."
```

- [ ] **Step 2: Ejecutarlo de punta a punta**

```bash
make down && make up && make verify
```

Expected: los cuatro pasos en verde y el mensaje final. `make gates` debe mostrar los tres gates ejecutándose, **cero omitidos**.

Comprobar que `lint` está limpio. Hay 7 errores de ruff pre-existentes (verificados el 2026-07-30, ajenos a este plan): `eval/relations/runner.py:70` (E501), `tests/eval/test_attributes_metrics.py:7,8,17,25` (E501) y `tests/integration/test_relations_flow.py:18,19` (F401, auto-corregibles). `make verify` fallará por ellos. Arreglarlos aquí es parte de la task — son líneas largas e imports sin usar:

```bash
.venv/bin/ruff check --fix tests/integration/test_relations_flow.py
```

Y partir manualmente las 5 líneas largas de `eval/relations/runner.py:70` y `tests/eval/test_attributes_metrics.py`, sin cambiar comportamiento. Volver a ejecutar `make lint` hasta que esté limpio.

- [ ] **Step 3: Verificar que el modo estricto muerde**

Prueba de que `make gates` no es decorativo: vaciar la base y comprobar que falla.

```bash
make down && make up
LOOM_EVAL_STRICT=1 .venv/bin/python -m pytest tests/eval -q --tb=line   # sin sembrar
```

Expected: FAIL con "M1 sin ejecutar" y el aviso de `LOOM_EVAL_STRICT=1`. Después `make seed && make gates` debe pasar.

- [ ] **Step 4: Commit**

```bash
git add Makefile eval/relations/runner.py tests/eval/test_attributes_metrics.py tests/integration/test_relations_flow.py
git commit -m "feat(dev): make verify as the single definition of verified

lint + suite + siembra + los tres gates en modo estricto. Arregla de paso los
7 hallazgos de ruff pre-existentes que impedían que lint estuviera limpio."
```

---

### Task 6: CI en GitHub Actions

**Fase separada: aprobable o descartable sin afectar a las Tasks 1-5.** Sin ella, todo lo anterior sigue siendo útil (`make verify` es un solo comando), pero seguirá dependiendo de que alguien lo ejecute.

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md` §13 (Task 7 lo cierra)

**Interfaces:**
- Consumes: `make lint`, `make test`, `make seed`, `make gates` (Task 5); caché congelada (Task 4).
- Produces: comprobación automática en cada push y pull request a `main`. **Sin secretos**: no hace falta clave de API porque las respuestas están congeladas.

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  verify:
    runs-on: ubuntu-latest

    services:
      neo4j:
        image: neo4j:5.26
        env:
          NEO4J_AUTH: neo4j/loom-dev-password
        ports:
          - 7687:7687
        options: >-
          --health-cmd "cypher-shell -u neo4j -p loom-dev-password 'RETURN 1'"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 20

    env:
      NEO4J_URI: bolt://localhost:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: loom-dev-password
      LOOM_LLM_MODEL: openai/kimi-k2.5
      LOOM_CACHE_DIR: eval/fixtures/llm-cache
      LOOM_EVAL_STRICT: "1"

    steps:
      - uses: actions/checkout@v4

      - name: Instalar uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Instalar dependencias
        run: uv sync --all-groups

      - name: Lint
        run: uv run ruff check backend/ eval/ tests/

      - name: Suite de tests
        run: uv run pytest tests/ -q

      - name: Sembrar el grafo (sin clave de API — respuestas congeladas)
        run: uv run python -m eval.seed

      - name: Gates de eval en modo estricto
        run: uv run pytest tests/eval -v -rs
```

**Nota para el implementador:** los nombres de las variables de conexión (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`) deben confirmarse contra `backend/graph/client.py` y `.env.example` antes de dar esto por bueno — `grep -n "environ" backend/graph/client.py`. Si difieren, ajustar el bloque `env`. La contraseña `loom-dev-password` sale de `tests/conftest.py:118`, que la usa como default.

Este workflow no usa `make` a propósito: bajo `uv` los comandos van con `uv run`, y duplicar la lista aquí es preferible a que el Makefile tenga que saber si está dentro o fuera de un entorno gestionado por uv. Si esa duplicación molesta, la alternativa es un target `make ci` que use `uv run`; decidirlo al implementar.

- [ ] **Step 2: Verificar el workflow sin subirlo a main**

El repo es `e2tovar/mvp-loom`. Crear una rama y abrir un PR de prueba para que Actions lo ejecute:

```bash
git checkout -b ci/verify-workflow
git add .github/workflows/ci.yml
git commit -m "ci: verify gates on every push with frozen LLM responses"
```

**PARAR AQUÍ.** El push lo decide el usuario (regla dura del proyecto: nunca `git push` sin que lo pida explícitamente). Cuando lo autorice, comprobar en la pestaña Actions que:

- El servicio Neo4j arranca y pasa su health check.
- `pytest tests/` no omite los tests de integración (Neo4j está disponible).
- El paso de sembrado termina **sin** clave de API.
- Los tres gates se ejecutan, cero omitidos.

Si el paso de sembrado pide credenciales, falta congelar entradas: revisar `test_frozen_cache.py`.

- [ ] **Step 3: Commit (ya hecho en el paso 2)**

---

### Task 7: Documentación y cierre de deuda

**Files:**
- Modify: `README.md` §13 (la línea "Eval antes de merge"), `docs/known-issues.md` (puntos 3 y 4 de M3), `docs/superpowers/specs/004-m3-attributes/quickstart.md`
- Modify: `.env.example` (las dos variables nuevas)

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: documentación que no miente.

- [ ] **Step 1: Documentar las variables nuevas en .env.example**

Añadir tras la línea 15 (`# LOOM_LLM_API_KEY=…`):

```bash
# ── Eval harness ──────────────────────────────────────────────────────────────
# Raíz de las cachés de respuestas LLM. Por defecto .cache/ (sin versionar).
# El eval apunta aquí para usar las respuestas congeladas del repo:
# LOOM_CACHE_DIR=eval/fixtures/llm-cache
#
# Con LOOM_EVAL_STRICT=1 los gates de eval FALLAN en vez de omitirse cuando el
# grafo no está sembrado. El CI lo activa; en local déjalo apagado y usa
# `make seed` antes de `make gates`.
# LOOM_EVAL_STRICT=1
```

- [ ] **Step 2: Corregir el README**

En §13, la línea actual dice: `**Eval antes de merge.** Un milestone no está "hecho" sin su eval verde; la regresión es gate de CI.` Era falsa hasta hoy (no existía CI). Sustituir por:

```markdown
- **Eval antes de merge.** Un milestone no está "hecho" sin su eval verde. Los tres gates (M1 personajes, M2 relaciones, M3 atributos) corren en CI sobre las obras crafted, con las respuestas del LLM congeladas en `eval/fixtures/llm-cache/` — así el gate mide el código, es determinista y no gasta cuota. `LOOM_EVAL_STRICT=1` impide que un gate se omita en silencio. En local: `make verify`. Las novelas completas siguen siendo diagnóstico manual, no gate.
```

- [ ] **Step 3: Cerrar los puntos de known-issues y anotar la deuda nueva**

En `docs/known-issues.md`, dentro de "M3 · Follow-ups", marcar el punto 4 como resuelto añadiendo al final de su párrafo:

```markdown
   **Resolución 2026-07-30:** las respuestas del LLM de las 4 obras crafted están
   congeladas en `eval/fixtures/llm-cache/` (21 escenas), `python -m eval.seed`
   siembra el grafo de forma determinista y gratuita, y `LOOM_EVAL_STRICT=1`
   convierte cualquier omisión en fallo. El CI (`.github/workflows/ci.yml`) lo
   ejecuta en cada push sin necesidad de clave de API. Verificado: los tres gates
   corren con cero omitidos.
```

Y añadir una entrada nueva al final de la sección M3:

```markdown
9. **[Eval] La clave de caché de M1 ignora el registro de entidades.**
   `ExtractionCache._key` (`backend/llm/cache.py:38-45`) es
   `SHA-256(scene_text + prompt_version + model + schema_version)` — no incluye
   `known_entities`, aunque el prompt sí lo recibe y la respuesta del modelo
   depende de él (`backend/extraction/pipeline.py:173-177`). Las cachés de M2 y M3
   sí incluyen el fingerprint del cast (`cache.py:97`, `cache.py:155`): es una
   asimetría, no una decisión documentada. Congelar las respuestas (2026-07-30)
   la vuelve inofensiva en el gate — deja de producir variación — pero cristaliza
   una respuesta generada con un registro de entidades concreto. Arreglar la clave
   invalidaría toda la caché de las novelas y obligaría a re-medir M1 pagando, así
   que es una decisión aparte. Hoy la deuda es que ni siquiera está declarada en
   el docstring de la clase.
```

- [ ] **Step 4: Actualizar el quickstart de M3**

En `docs/superpowers/specs/004-m3-attributes/quickstart.md`, localizar la sección donde se explica cómo correr el eval y añadir, antes de las instrucciones manuales:

```markdown
## La vía corta

```bash
make up      # Neo4j
make seed    # siembra el grafo desde las respuestas congeladas (gratis)
make gates   # los tres gates en modo estricto
```

`make seed` no gasta cuota LLM: las respuestas de las obras crafted están
versionadas en `eval/fixtures/llm-cache/`. Si cambias el prompt o el modelo, esas
respuestas dejan de acertar y el sembrado volverá a llamar al LLM — es lo
correcto: cambiar el prompt obliga a re-medir.
```

- [ ] **Step 5: Verificar que la documentación dice la verdad**

Ejecutar literalmente lo que el quickstart promete, en una base recreada:

```bash
make down && make up && make seed && make gates
```

Expected: pasa, cero omitidos, cero llamadas al LLM.

Comprobar que no queda ninguna referencia a la política antigua:

```bash
grep -rn "gate de CI" README.md docs/ | head
```

Expected: solo menciones coherentes con lo implementado.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/known-issues.md docs/superpowers/specs/004-m3-attributes/quickstart.md .env.example
git commit -m "docs: eval gates now really run in CI; declare cache-key debt

El README afirmaba que la regresión era gate de CI cuando no existía CI.
Registra además la asimetría de la clave de caché de M1 (ignora known_entities)."
```

---

## Self-Review

**1. Cobertura del objetivo:**

| Objetivo | Task |
|---|---|
| Congelar respuestas LLM de las 4 obras | 4 |
| Que la caché sea redirigible sin tocar los CLIs | 1 |
| Sembrador determinista del grafo | 3 |
| Que el skip pueda ser fallo | 2 |
| Un solo comando de verificación | 5 |
| Que alguien lo ejecute sin depender de disciplina | 6 |
| Que el README deje de mentir | 7 |
| Detectar si falta una entrada congelada | 4 (`test_frozen_cache.py`) |
| No romper el aislamiento de la base | 3 (`test_seed_does_not_touch_manuscripts_outside_the_gate`) |
| Declarar el riesgo que se cristaliza | 7 (punto 9 de known-issues) |

Sin huecos.

**2. Placeholders:** cero "TBD"/"TODO". Dos notas explícitas al implementador (firmas de los pipelines de M2/M3 en Task 3, nombres de variables de conexión en Task 6) porque no las verifiqué durante el research: están marcadas como comprobación obligatoria con el `grep` exacto, no como suposición.

**3. Consistencia de tipos y nombres:**
- `LOOM_CACHE_DIR` (Task 1) → usado igual en 3, 4, 5, 6, 7.
- `LOOM_EVAL_STRICT` (Task 2) → igual en 5, 6, 7. Solo el valor `"1"` activa, fijado por test.
- `skip_or_fail(reason: str)` (Task 2) → los tres gates lo llaman con la misma firma.
- `SeedWork(filename, source_format, layers)` y `seed_all(force) -> dict[str, str]` (Task 3) → consumidos con esos nombres en 4 (`test_frozen_cache.py` importa `GATE_WORKS` y usa `.filename`/`.source_format`).
- Propiedad `dir` de las tres cachés (Task 1) → usada en los mensajes de Task 4.
- `eval/fixtures/llm-cache` como ruta única: idéntica en 3 (`FROZEN_CACHE_DIR`), 4, 5 (`FROZEN_CACHE`), 6 (`LOOM_CACHE_DIR`), 7.

**4. Orden y dependencias:** 1 y 2 son independientes entre sí. 3 necesita 1. 4 necesita 3. 5 necesita 2+3+4. 6 necesita 5. 7 al final. Tasks 1-5 dejan el proyecto en un estado útil aunque 6 se descarte.

## Coste declarado

- **Task 4, paso 4:** 21 llamadas al LLM (`openai/kimi-k2.5`) sobre 5 459 bytes de texto. Única vez.
- **Todo lo demás:** cero coste de API.
- **Task 6:** requiere que el usuario autorice el push para que Actions ejecute el workflow.

## Lo que este plan NO hace

- **No amplía el gold de atributos.** El gate de M3 seguirá midiendo 8 tripletas y sacando F1 = 1.0 sobre una obra sintética (punto 3 de "M3 · Follow-ups"). Determinista y siempre ejecutado, pero midiendo poco. Es el siguiente paso natural, y es trabajo de anotación manual.
- **No corre M3 sobre novela real** (punto 5).
- **No arregla la clave de caché de M1** (la declara, punto 9).
- **No investiga el test flaky** `test_get_structure.py::test_structure_can_omit_snippets` (punto 7). Puede aparecer en CI; si lo hace, ese será el momento.
- **No detecta que el proveedor cambie el modelo por debajo.** Límite estructural de congelar; se cubre con la corrida diagnóstica manual.
