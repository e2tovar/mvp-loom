# M1 — Precisión de extracción (animales, paratexto, descriptores relacionales) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Subir la precisión de la extracción de personajes eliminando tres fuentes de falsos positivos —paratexto del libro, descriptores relacionales y animales con nombre— resolviéndolas principalmente en el prompt y conservando redes deterministas mínimas.

**Architecture:** El LLM marca cada personaje como `person`/`animal` y omite el paratexto; el eval excluye animales del cómputo sin borrarlos del grafo. La capa cruda (M0, sin LLM) aparta paratexto inequívoco del epub usando las señales que el propio archivo declara (`guide`). El filtro determinista `is_unnamed` gana detección de genitivos como red de seguridad del auto-merge por alias. Un único bump de `PROMPT_VERSION` agrupa las tres reglas nuevas y dispara un solo reproceso de verificación.

**Tech Stack:** Python 3.12 + uv, pytest, Pydantic, Neo4j (driver `neo4j`), ebooklib + BeautifulSoup (ingest), LiteLLM (solo en `backend/llm/`).

## Global Constraints

- Cypher SOLO en `backend/graph/`; LiteLLM SOLO en `backend/llm/` (constitución).
- Ids deterministas e idempotencia (INV-M1-1): M0 no incorpora no determinismo; ningún `MERGE` crea duplicados en re-ejecución.
- Umbrales del eval sin cambios (`eval/characters/thresholds.py`): `DETECTION_F1 = 0.90`, `RESOLUTION_B3_F1 = 0.85`, `SILENT_BAD_MERGES = 0`.
- Métrica no medida = `null` + warning, jamás un valor inventado (quality-boundaries). Los animales no se anotan en el gold: se **excluyen** del cómputo, no se cuentan como aciertos.
- Docstrings/comentarios en español; commits conventional en inglés; NUNCA `git push`.
- Tests: `uv run pytest …`; lint: `uv run ruff check backend eval tests`.
- Cambiar `SCHEMA_VERSION` o `PROMPT_VERSION` invalida toda la cache de extracción (`backend/llm/cache.py`).

## Contexto para el implementador (leer antes de empezar)

- Spec: `docs/superpowers/specs/2026-07-15-m1-extraction-precision-design.md`.
- Deuda que salda: `docs/known-issues.md`, follow-ups 2 (paratexto), 3 (descriptores), 4 (animales).
- `backend/extraction/schemas.py:13` — `SCHEMA_VERSION = 2`; `CharacterCandidateOut` (líneas 48-54).
- `backend/extraction/prompts.py:12` — `PROMPT_VERSION = 3`; `SYSTEM_PROMPT` (14-49), reglas numeradas 1-7.
- `backend/extraction/registry.py:49-62` — `is_unnamed`; `_GENERIC_HEAD` (27-35); `_ascii_fold` (65-67).
- `backend/extraction/resolution.py:85` — call site de `is_unnamed` sobre `canonical_name`.
- `backend/extraction/pipeline.py:206-253` — loop de `new_characters`; `upsert_character` en línea 239.
- `backend/graph/characters.py:45` — `upsert_character` (sin `entity_kind` hoy); `get_characters_list` (221), `get_character_detail` (282).
- `backend/ingest/parsers/base.py` — `Block` dataclass (kind/text/level/style); `SPECIAL_HEADING_RE`.
- `backend/ingest/parsers/epub_parser.py:36` — recorre `book.spine` descartando el flag `linear`; ignora `book.guide`.
- `backend/ingest/segmentation/chapters.py:47` — `segment_chapters(blocks) -> (chapters, frontmatter)`.
- `backend/ingest/non_narrative.py:24-52` — `_detect(text)` y `classify(blocks)`; enum `NonNarrativeKind` en `backend/ingest/models.py:17` (ya incluye `cover`/`backmatter`, hoy sin emitir).
- `backend/ingest/pipeline.py:64-65` — `segment_chapters` + `non_narrative.classify`.
- `eval/characters/runner.py` — `_load_system_output` carga entidades del grafo (ver plan de cierre M1).
- Tests puros: `tests/unit/test_extraction_pipeline.py` (schemas, prompts, registry). Resolución: `tests/unit/test_resolution.py` (`_candidate`, `_registry`, parametrize `is_unnamed`). Runner: `tests/unit/test_eval_runner.py` (`_patch`, `PRED_ENTITIES`). Parsers: `tests/unit/test_parsers.py`. Integración con Neo4j: `tests/integration/test_characters_flow.py` (fixture `neo4j_session`).

---

### Task 1: `entity_kind` en el contrato de extracción

**Files:**
- Modify: `backend/extraction/schemas.py:13,48-54`
- Test: `tests/unit/test_extraction_pipeline.py`

**Interfaces:**
- Produces: `CharacterCandidateOut.entity_kind: Literal["person", "animal"] = "person"`; `SCHEMA_VERSION = 3`. Consumido por pipeline (Task 8), runner (Task 9), prompt (Task 10).

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/unit/test_extraction_pipeline.py` (junto a los tests de schema existentes, tras `test_schema_version_bumped_for_presence_field`):

```python
def test_character_candidate_entity_kind_defaults_person():
    from backend.extraction.schemas import CharacterCandidateOut

    cand = CharacterCandidateOut(canonical_name="Elena", is_present_in_scene=True)
    assert cand.entity_kind == "person"


def test_character_candidate_accepts_animal():
    from backend.extraction.schemas import CharacterCandidateOut

    cand = CharacterCandidateOut(
        canonical_name="Hedwig", is_present_in_scene=True, entity_kind="animal"
    )
    assert cand.entity_kind == "animal"


def test_character_candidate_rejects_unknown_entity_kind():
    import pytest as _pytest
    from pydantic import ValidationError

    from backend.extraction.schemas import CharacterCandidateOut

    with _pytest.raises(ValidationError):
        CharacterCandidateOut(
            canonical_name="X", is_present_in_scene=True, entity_kind="plant"
        )


def test_schema_version_bumped_for_entity_kind():
    from backend.extraction.schemas import SCHEMA_VERSION

    assert SCHEMA_VERSION == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_extraction_pipeline.py -k "entity_kind or schema_version_bumped_for_entity" -q`
Expected: FAIL — `entity_kind` no existe y `SCHEMA_VERSION == 2`.

- [ ] **Step 3: Implement**

En `backend/extraction/schemas.py`, cambiar `SCHEMA_VERSION`:

```python
SCHEMA_VERSION: int = 3
```

Y añadir el campo a `CharacterCandidateOut` (tras `role`):

```python
class CharacterCandidateOut(BaseModel):
    """Entidad nueva propuesta (no presente en el registro)."""

    canonical_name: str
    aliases: list[str] = []
    role: Literal["protagonist", "antagonist", "secondary", "minor", "unknown"] = "unknown"
    entity_kind: Literal["person", "animal"] = "person"
    is_present_in_scene: bool
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_extraction_pipeline.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/extraction/schemas.py tests/unit/test_extraction_pipeline.py
git commit -m "feat(extraction): add entity_kind (person/animal) to character schema"
```

---

### Task 2: `is_unnamed` detecta descriptores relacionales (red del auto-merge)

**Files:**
- Modify: `backend/extraction/registry.py:27-35,49-62`
- Test: `tests/unit/test_resolution.py`

**Interfaces:**
- Produces: `is_unnamed(name)` devuelve `True` también para descriptores genitivos con parentesco ("Abuelo de Harry Potter", "Mr. Darcy's father"). Sin cambio de firma. Ya consumido en `resolution.py:85` y `registry.py:86`.

- [ ] **Step 1: Write the failing tests**

En `tests/unit/test_resolution.py`, añadir junto a `test_unnamed_descriptor_detected`/`test_named_character_not_unnamed`:

```python
@pytest.mark.parametrize(
    "name",
    [
        "Abuelo de Harry Potter",
        "Mr. Darcy's father",
        "la madre de Elena",
        "the father of Harry",
        "Abuela de Ron",
    ],
)
def test_relational_descriptor_is_unnamed(name):
    """Un descriptor por parentesco con nombre propio de OTRO personaje embebido
    sigue siendo un descriptor sin nombre propio (no es entidad propia)."""
    assert is_unnamed(name) is True


@pytest.mark.parametrize(
    "name",
    ["Juan de Dios", "Harry Potter", "Elena", "Fitzwilliam Darcy"],
)
def test_names_with_embedded_preposition_not_unnamed(name):
    """Nombres propios legítimos que contienen 'de' no se filtran."""
    assert is_unnamed(name) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_resolution.py -k "relational_descriptor or embedded_preposition" -q`
Expected: FAIL — "Abuelo de Harry Potter" hoy pasa `is_unnamed` (tiene tokens en mayúscula) → `False`.

- [ ] **Step 3: Implement**

En `backend/extraction/registry.py`, ampliar `_GENERIC_HEAD` con los parentescos de abuelos (añadir al `frozenset` existente):

```python
    "grandfather", "grandmother", "grandson", "granddaughter", "grandparent",
    "abuelo", "abuela", "nieto", "nieta",
```

Añadir, tras la definición de `_LEADING_ARTICLE` (línea 43-46), los patrones genitivos y el helper:

```python
# Descriptor relacional: "<parentesco> de/of <Nombre>" o "<Nombre>'s <parentesco>".
# El nombre propio embebido pertenece a OTRO personaje, no al descrito.
_RELATIONAL_GENITIVE = re.compile(r"^(?P<head>\S+)\s+(?:de|of)\s+\S+", re.IGNORECASE)
_RELATIONAL_POSSESSIVE = re.compile(r"^.+['’]s\s+(?P<head>\S+)\s*$", re.IGNORECASE)


def _is_relational_descriptor(stripped: str) -> bool:
    """True si es un descriptor por parentesco con nombre propio ajeno embebido."""
    for pattern in (_RELATIONAL_GENITIVE, _RELATIONAL_POSSESSIVE):
        match = pattern.match(stripped)
        if match and _ascii_fold(match.group("head")) in _GENERIC_HEAD:
            return True
    return False
```

Reemplazar el cuerpo de `is_unnamed` (líneas 59-62) por:

```python
    stripped = _LEADING_ARTICLE.sub("", name.strip())
    if not stripped:
        return True
    if _is_relational_descriptor(stripped):
        return True
    return not any(tok[:1].isupper() for tok in stripped.split())
```

Nota: `_is_relational_descriptor` usa `_ascii_fold`, definido más abajo en el módulo (línea 65). Como Python resuelve nombres en tiempo de llamada, no de definición, no hace falta reordenar; ambos son funciones de módulo.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_resolution.py -q`
Expected: PASS (los tests de honoríficos y colectivos existentes siguen verdes).

- [ ] **Step 5: Commit**

```bash
git add backend/extraction/registry.py tests/unit/test_resolution.py
git commit -m "feat(extraction): is_unnamed rejects relational descriptors with embedded proper names"
```

---

### Task 3: `Block.source_role` y `partition_paratext`

**Files:**
- Modify: `backend/ingest/parsers/base.py` (`Block` dataclass)
- Create: `backend/ingest/segmentation/paratext.py`
- Test: `tests/unit/test_paratext_partition.py`

**Interfaces:**
- Produces:
  - `Block.source_role: str | None = None` — rol declarado por el formato de origen (solo epub lo rellena; txt/docx lo dejan `None`).
  - `partition_paratext(blocks: list[Block]) -> tuple[list[Block], list[Block]]` — devuelve `(narrative, paratext)`. Un bloque va a `paratext` solo si su `source_role` está en el conjunto de roles inequívocamente no narrativos. Prólogo/prefacio/introducción NO se apartan aquí (los decide el LLM).
- Consumed by: pipeline de ingest (Task 6), non_narrative (Task 4).

- [ ] **Step 1: Write the failing test**

Crear `tests/unit/test_paratext_partition.py`:

```python
"""Partición de paratexto inequívoco antes de la segmentación de capítulos."""

from __future__ import annotations

from backend.ingest.parsers.base import Block
from backend.ingest.segmentation.paratext import partition_paratext


def _blk(kind: str, text: str, role: str | None = None) -> Block:
    return Block(kind=kind, text=text, source_role=role)


def test_paratext_role_goes_to_paratext_even_with_heading():
    blocks = [
        _blk("heading", "Título del libro", role="cover"),
        _blk("paragraph", "J. K. Rowling", role="cover"),
        _blk("heading", "Capítulo 1"),
        _blk("paragraph", "Elena abrió la puerta."),
    ]
    narrative, paratext = partition_paratext(blocks)
    assert [b.text for b in paratext] == ["Título del libro", "J. K. Rowling"]
    assert [b.text for b in narrative] == ["Capítulo 1", "Elena abrió la puerta."]


def test_prologue_role_stays_narrative():
    """Prólogo/prefacio son ambiguos: no se apartan estructuralmente."""
    blocks = [
        _blk("heading", "Prólogo", role="preface"),
        _blk("paragraph", "Aquella noche todo cambió."),
    ]
    narrative, paratext = partition_paratext(blocks)
    assert paratext == []
    assert len(narrative) == 2


def test_no_role_all_narrative():
    blocks = [_blk("heading", "Capítulo 1"), _blk("paragraph", "Texto.")]
    narrative, paratext = partition_paratext(blocks)
    assert paratext == []
    assert len(narrative) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_paratext_partition.py -q`
Expected: FAIL — `Block` no acepta `source_role` y el módulo `paratext` no existe.

- [ ] **Step 3: Implement**

En `backend/ingest/parsers/base.py`, añadir el campo a `Block`:

```python
@dataclass
class Block:
    """Unidad estructural cruda emitida por un parser."""

    kind: BlockKind
    text: str
    level: int | None = None
    style: str | None = None
    source_role: str | None = None
```

Crear `backend/ingest/segmentation/paratext.py`:

```python
"""Partición de paratexto inequívoco (portada, índice, créditos…) antes de segmentar.

Solo actúa sobre bloques cuyo formato de origen declaró un rol no narrativo explícito
(hoy: epub vía `guide`). Prólogo/prefacio/introducción son ambiguos y NO se apartan
aquí: pueden ser narrativa y los decide el LLM de extracción por su contenido.
"""

from __future__ import annotations

from backend.ingest.parsers.base import Block

# Roles del `guide` de EPUB inequívocamente no narrativos. Se excluye deliberadamente
# "text", "foreword", "preface", "epigraph": los tres últimos pueden ser narrativa.
_PARATEXT_ROLES = frozenset(
    {
        "cover", "title-page", "titlepage", "copyright-page", "copyright",
        "toc", "loi", "lot", "index", "bibliography", "glossary",
        "dedication", "acknowledgements", "colophon", "notes",
    }
)


def partition_paratext(blocks: list[Block]) -> tuple[list[Block], list[Block]]:
    """Separa (narrativa, paratexto) según el `source_role` declarado por el formato."""
    narrative: list[Block] = []
    paratext: list[Block] = []
    for block in blocks:
        role = (block.source_role or "").lower()
        if role in _PARATEXT_ROLES:
            paratext.append(block)
        else:
            narrative.append(block)
    return narrative, paratext
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_paratext_partition.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/ingest/parsers/base.py backend/ingest/segmentation/paratext.py tests/unit/test_paratext_partition.py
git commit -m "feat(ingest): partition unambiguous paratext by declared source_role"
```

---

### Task 4: `non_narrative` clasifica por `source_role`

**Files:**
- Modify: `backend/ingest/non_narrative.py:24-52`
- Test: `tests/unit/test_non_narrative.py` (crear si no existe; si existe, añadir)

**Interfaces:**
- Consumes: `Block.source_role` (Task 3).
- Produces: `classify(blocks)` emite `NonNarrativeKind` `"cover"`/`"backmatter"`/`"toc"`/`"license"`/`"frontmatter"` a partir del `source_role` cuando está presente, cayendo a `_detect(text)` cuando no. `detected_by` pasa a `"source_role"` en esos casos.

- [ ] **Step 1: Write the failing test**

Crear/añadir en `tests/unit/test_non_narrative.py`:

```python
"""Clasificación de bloques no narrativos por rol estructural o heurística de texto."""

from __future__ import annotations

from backend.ingest.non_narrative import classify
from backend.ingest.parsers.base import Block


def test_classify_uses_source_role_over_text():
    drafts = classify([Block(kind="heading", text="Cualquier cosa", source_role="cover")])
    assert len(drafts) == 1
    assert drafts[0].kind == "cover"
    assert drafts[0].detected_by == "source_role"


def test_classify_maps_index_role_to_backmatter():
    drafts = classify([Block(kind="paragraph", text="…", source_role="index")])
    assert drafts[0].kind == "backmatter"


def test_classify_falls_back_to_text_detection():
    drafts = classify([Block(kind="paragraph", text="Copyright 2020 Acme")])
    assert drafts[0].kind == "license"
    assert drafts[0].detected_by == "copyright_keyword"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_non_narrative.py -q`
Expected: FAIL — hoy `classify` ignora `source_role`.

- [ ] **Step 3: Implement**

En `backend/ingest/non_narrative.py`, añadir el mapa de rol tras `_detect` (antes de `classify`):

```python
_ROLE_TO_KIND: dict[str, NonNarrativeKind] = {
    "cover": "cover",
    "title-page": "cover",
    "titlepage": "cover",
    "copyright-page": "license",
    "copyright": "license",
    "toc": "toc",
    "loi": "toc",
    "lot": "toc",
    "dedication": "frontmatter",
    "acknowledgements": "frontmatter",
    "notes": "backmatter",
    "colophon": "backmatter",
    "index": "backmatter",
    "bibliography": "backmatter",
    "glossary": "backmatter",
}


def _kind_from_role(role: str | None) -> NonNarrativeKind | None:
    if not role:
        return None
    return _ROLE_TO_KIND.get(role.lower())
```

Reemplazar el cuerpo del bucle en `classify` (líneas 44-51) por:

```python
    for block in frontmatter_blocks:
        if block.kind == "separator":
            continue
        role_kind = _kind_from_role(block.source_role)
        if role_kind is not None:
            kind, detected_by = role_kind, "source_role"
        else:
            kind, detected_by = _detect(block.text)
        if drafts and drafts[-1].kind == kind and drafts[-1].detected_by == detected_by:
            drafts[-1].text += "\n\n" + block.text
        else:
            drafts.append(NonNarrativeDraft(kind=kind, text=block.text, detected_by=detected_by))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_non_narrative.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/ingest/non_narrative.py tests/unit/test_non_narrative.py
git commit -m "feat(ingest): classify non-narrative blocks by declared source_role"
```

---

### Task 5: `epub_parser` rellena `source_role` desde el `guide`

**Files:**
- Modify: `backend/ingest/parsers/epub_parser.py:35-53`
- Test: `tests/unit/test_parsers.py`

**Interfaces:**
- Produces: los `Block` emitidos por `EpubParser` llevan `source_role` con el `type` del `guide` del epub para los documentos referenciados ahí; `None` para el resto. txt/docx no cambian.

- [ ] **Step 1: Write the failing test**

Añadir a `tests/unit/test_parsers.py` (incluye el import de ebooklib arriba si no está: `from ebooklib import epub`):

```python
def test_epub_parser_tags_guide_paratext_with_source_role(tmp_path):
    from ebooklib import epub

    from backend.ingest.parsers.epub_parser import EpubParser

    book = epub.EpubBook()
    book.set_identifier("id-test")
    book.set_title("Libro de prueba")
    book.set_language("es")

    cover = epub.EpubHtml(title="Cover", file_name="cover.xhtml", lang="es")
    cover.content = "<html><body><h1>Libro de prueba</h1><p>J. K. Rowling</p></body></html>"
    chap = epub.EpubHtml(title="Cap 1", file_name="chap1.xhtml", lang="es")
    chap.content = "<html><body><h1>Capítulo 1</h1><p>Elena abrió la puerta.</p></body></html>"
    book.add_item(cover)
    book.add_item(chap)
    book.spine = [cover, chap]
    book.guide = [{"type": "cover", "href": "cover.xhtml", "title": "Cover"}]

    path = tmp_path / "with-guide.epub"
    epub.write_epub(str(path), book)

    doc = EpubParser().parse(path)
    cover_blocks = [b for b in doc.blocks if b.text in ("Libro de prueba", "J. K. Rowling")]
    chap_blocks = [b for b in doc.blocks if b.text in ("Capítulo 1", "Elena abrió la puerta.")]

    assert cover_blocks and all(b.source_role == "cover" for b in cover_blocks)
    assert chap_blocks and all(b.source_role is None for b in chap_blocks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_parsers.py -k guide_paratext -q`
Expected: FAIL — hoy `source_role` es siempre `None`.

- [ ] **Step 3: Implement**

En `backend/ingest/parsers/epub_parser.py`, reemplazar el método `parse` (bloque del bucle del spine, líneas 35-53) por:

```python
        blocks: list[Block] = []
        guide_roles = {
            str(g.get("href", "")).split("#")[0]: str(g.get("type", "")).strip()
            for g in getattr(book, "guide", []) or []
            if g.get("href")
        }
        for idref, _linear in book.spine:
            item = book.get_item_with_id(idref)
            if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue
            role = guide_roles.get(item.get_name()) or None
            soup = BeautifulSoup(item.get_content(), "lxml")
            for el in soup.find_all(_BLOCK_TAGS):
                if el.name == "hr":
                    blocks.append(Block(kind="separator", text="***", source_role=role))
                    continue
                text = el.get_text(" ", strip=True)
                if not text:
                    continue
                if el.name in _HEADING_TAGS:
                    blocks.append(
                        Block(kind="heading", text=text, level=_HEADING_TAGS[el.name], source_role=role)
                    )
                elif is_separator_line(text):
                    blocks.append(Block(kind="separator", text=text, source_role=role))
                else:
                    blocks.append(Block(kind="paragraph", text=text, source_role=role))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_parsers.py -q`
Expected: PASS (incluido `test_epub_parser_reads_spine_in_order`, que no depende de `source_role`).

- [ ] **Step 5: Commit**

```bash
git add backend/ingest/parsers/epub_parser.py tests/unit/test_parsers.py
git commit -m "feat(ingest): tag epub blocks with guide-declared source_role"
```

---

### Task 6: Cablear la partición de paratexto en el pipeline de ingest

**Files:**
- Modify: `backend/ingest/pipeline.py:27,64-65`
- Test: `tests/unit/test_paratext_partition.py` (test de composición)

**Interfaces:**
- Consumes: `partition_paratext` (Task 3), `segment_chapters` (existente), `non_narrative.classify` (Task 4).
- Produces: el paratexto inequívoco termina en `nn_drafts` (no narrativo), no en `chapter_drafts`, aunque tenga heading propio.

- [ ] **Step 1: Write the failing composition test**

Añadir a `tests/unit/test_paratext_partition.py`:

```python
def test_cover_with_heading_ends_non_narrative_not_chapter():
    """Composición partition → segment → classify: la portada no crea un capítulo."""
    from backend.ingest.non_narrative import classify
    from backend.ingest.segmentation.chapters import segment_chapters

    blocks = [
        _blk("heading", "Libro de prueba", role="cover"),
        _blk("paragraph", "J. K. Rowling", role="cover"),
        _blk("heading", "Capítulo 1"),
        _blk("paragraph", "Elena abrió la puerta."),
    ]
    narrative, paratext = partition_paratext(blocks)
    chapters, frontmatter = segment_chapters(narrative)
    nn_drafts = classify(paratext + frontmatter)

    assert [c.title for c in chapters] == ["Capítulo 1"]
    assert any(d.kind == "cover" for d in nn_drafts)
    assert all("Rowling" not in b.text for c in chapters for b in c.blocks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_paratext_partition.py -k cover_with_heading -q`
Expected: FAIL — sin la partición, "Libro de prueba" (heading con rol cover) crea un capítulo.

- [ ] **Step 3: Implement**

En `backend/ingest/pipeline.py`, añadir el import (junto a la línea 27):

```python
from backend.ingest.segmentation.paratext import partition_paratext
```

Reemplazar las líneas 64-65:

```python
    narrative_blocks, paratext_blocks = partition_paratext(doc.blocks)
    chapter_drafts, frontmatter = segment_chapters(narrative_blocks)
    nn_drafts = non_narrative.classify(paratext_blocks + frontmatter)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_paratext_partition.py tests/unit/test_parsers.py -q`
Expected: PASS. Verificar sin regresión: `uv run pytest tests/unit -q`.

- [ ] **Step 5: Commit**

```bash
git add backend/ingest/pipeline.py tests/unit/test_paratext_partition.py
git commit -m "feat(ingest): route declared paratext to non-narrative before chapter segmentation"
```

---

### Task 7: `upsert_character` persiste `entity_kind`

**Files:**
- Modify: `backend/graph/characters.py:45-90,221-260,282+`
- Test: `tests/integration/test_characters_flow.py` (requiere Neo4j; hace SKIP sin él)

**Interfaces:**
- Consumes: nada nuevo.
- Produces: `upsert_character(sess, manuscript_id, canonical_name, aliases, role, is_mentioned_only, first_scene_id, entity_kind="person") -> str`. Lecturas (`get_characters_list`, `get_character_detail`) incluyen `entity_kind` (coalesce a `"person"` para nodos antiguos).

- [ ] **Step 1: Write the failing integration test**

Añadir a `tests/integration/test_characters_flow.py`:

```python
def test_entity_kind_persisted_and_defaulted(neo4j_session):
    from backend.graph import characters as char_graph
    from backend.graph.client import session as db_session

    with db_session() as sess:
        cid_person = char_graph.upsert_character(
            sess, MANUSCRIPT_ID, "Elena", [], "protagonist", False, "sc-1"
        )
        cid_animal = char_graph.upsert_character(
            sess, MANUSCRIPT_ID, "Hedwig", [], "minor", False, "sc-1", entity_kind="animal"
        )
        chars = {c["character_id"]: c for c in char_graph.get_characters_list(sess, MANUSCRIPT_ID)}

    assert chars[cid_person]["entity_kind"] == "person"
    assert chars[cid_animal]["entity_kind"] == "animal"
```

(`MANUSCRIPT_ID` y `neo4j_session` ya existen en el módulo.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_characters_flow.py -k entity_kind -q`
Expected: FAIL si Neo4j está arriba (`entity_kind` ausente); SKIP si no hay Neo4j.

> ⚠️ **Aviso (follow-up #1 de known-issues, sin resolver):** `tests/conftest.py` borra `Manuscript/Chapter/Scene` sin filtrar por `manuscript_id`. Correr integración contra la base real destruye la capa cruda de otros libros. Levantar una base Neo4j desechable para esta task (`docker compose` con base separada o `NEO4J_DATABASE` de test) antes de ejecutar.

- [ ] **Step 3: Implement**

En `backend/graph/characters.py`, cambiar la firma de `upsert_character` (añadir parámetro al final):

```python
def upsert_character(
    sess: Session,
    manuscript_id: str,
    canonical_name: str,
    aliases: list[str],
    role: str,
    is_mentioned_only: bool,
    first_scene_id: str,
    entity_kind: str = "person",
) -> str:
```

En el `ON CREATE SET` del MERGE, añadir la propiedad:

```python
            c.appearance_count   = 0,
            c.mention_count      = 0,
            c.entity_kind        = $entity_kind
```

Y pasar el parámetro en la llamada `sess.run(...)` (junto a los demás kwargs):

```python
        first_scene_id=first_scene_id,
        entity_kind=entity_kind,
```

En `get_characters_list`, en el bloque `RETURN c { … }`, añadir el campo con coalesce (para nodos previos sin la propiedad):

```python
            .character_id, .canonical_name, .aliases, .role,
            entity_kind: coalesce(c.entity_kind, 'person'),
```

Hacer el mismo añadido de `entity_kind: coalesce(c.entity_kind, 'person')` en el `RETURN` de `get_character_detail`.

- [ ] **Step 4: Run test to verify it passes**

Run (con Neo4j de test arriba): `uv run pytest tests/integration/test_characters_flow.py -q`
Expected: PASS. `uv run ruff check backend` limpio.

- [ ] **Step 5: Commit**

```bash
git add backend/graph/characters.py tests/integration/test_characters_flow.py
git commit -m "feat(graph): persist and read Character.entity_kind (default person)"
```

---

### Task 8: El pipeline propaga `entity_kind` del candidato al grafo

**Files:**
- Modify: `backend/extraction/pipeline.py:206-253`
- Test: `tests/integration/test_characters_flow.py`

**Interfaces:**
- Consumes: `CharacterCandidateOut.entity_kind` (Task 1), `upsert_character(..., entity_kind=…)` (Task 7).
- Produces: cada `Character` escrito lleva el `entity_kind` que el LLM asignó al candidato.

- [ ] **Step 1: Write the failing test**

Añadir a `tests/integration/test_characters_flow.py` un test que corra el pipeline con un LLM falso que emita un animal. Reutilizar el patrón de `fake_llm`/`manuscript_in_graph` ya presente en el módulo (ver `test_pipeline_writes_characters_and_mentions`). El fake debe devolver un `SceneExtraction` con un `new_characters=[CharacterCandidateOut(canonical_name="Hedwig", is_present_in_scene=True, entity_kind="animal")]`:

```python
def test_pipeline_persists_animal_entity_kind(neo4j_session, manuscript_in_graph):
    from backend.extraction.pipeline import run_extraction  # ajustar al nombre real del entrypoint
    from backend.extraction.schemas import CharacterCandidateOut, MentionOut, SceneExtraction
    from backend.graph import characters as char_graph
    from backend.graph.client import session as db_session

    fake = MagicMock()
    fake.extract.return_value = SceneExtraction(
        mentions=[MentionOut(surface="Hedwig", kind="name", links_to=None, quote="Hedwig voló.")],
        new_characters=[
            CharacterCandidateOut(canonical_name="Hedwig", is_present_in_scene=True, entity_kind="animal")
        ],
    )
    run_extraction(MANUSCRIPT_ID, llm=fake)  # ajustar firma real

    with db_session() as sess:
        chars = {c["canonical_name"]: c for c in char_graph.get_characters_list(sess, MANUSCRIPT_ID)}
    assert chars["Hedwig"]["entity_kind"] == "animal"
```

> El implementador debe ajustar el entrypoint (`run_extraction`) y el modo de inyectar el LLM falso a lo que ya use `test_pipeline_writes_characters_and_mentions` en este módulo. No inventar una firma nueva.

- [ ] **Step 2: Run test to verify it fails**

Run (Neo4j de test arriba): `uv run pytest tests/integration/test_characters_flow.py -k animal_entity_kind -q`
Expected: FAIL — el pipeline no pasa `entity_kind` (queda `"person"` por defecto).

- [ ] **Step 3: Implement**

En `backend/extraction/pipeline.py`, dentro del loop `for candidate in extraction.new_characters:` (línea 206), en la llamada a `upsert_character` (línea 239), pasar el `entity_kind` del candidato:

```python
                cid = char_graph.upsert_character(
                    sess,
                    manuscript_id,
                    canonical,
                    ...,  # resto de argumentos existentes sin cambios
                    entity_kind=candidate.entity_kind,
                )
```

> Mantener el orden y nombres de los argumentos existentes; solo se añade `entity_kind=candidate.entity_kind`. `candidate` es el `CharacterCandidateOut` del loop.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_characters_flow.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/extraction/pipeline.py tests/integration/test_characters_flow.py
git commit -m "feat(extraction): propagate candidate entity_kind to the graph"
```

---

### Task 9: El runner del eval excluye animales del cómputo

**Files:**
- Modify: `eval/characters/runner.py` (`_load_system_output`)
- Test: `tests/unit/test_eval_runner.py`

**Interfaces:**
- Consumes: `entity_kind` en la salida de `get_characters_list` (Task 7).
- Produces: `_load_system_output` filtra los personajes con `entity_kind == "animal"` antes de construir entidades y clusters. El gold no anota animales, así que se excluyen (no se cuentan como acierto ni como falso positivo).

- [ ] **Step 1: Write the failing test**

Añadir a `tests/unit/test_eval_runner.py` (usa los helpers `_patch`/`PRED_ENTITIES` existentes; aquí se parchea directamente `get_characters_list` que `_load_system_output` consume — ajustar al modo de patch que ya use el módulo):

```python
def test_animals_excluded_from_detection(monkeypatch):
    gold = {
        "work": "obra-test",
        "characters": [
            {
                "gold_id": "elena", "canonical_name": "Elena", "aliases": [],
                "role": "protagonist", "is_mentioned_only": False, "appearances": ["c1/s0"],
            }
        ],
    }
    pred_with_animal = [
        {"character_id": "m:ch:1", "canonical_name": "Elena", "aliases": [], "entity_kind": "person"},
        {"character_id": "m:ch:2", "canonical_name": "Hedwig", "aliases": [], "entity_kind": "animal"},
    ]
    monkeypatch.setattr(runner, "_load_gold", lambda work: gold)
    monkeypatch.setattr(
        runner, "_load_system_output", lambda mid: (
            [c for c in pred_with_animal if c.get("entity_kind", "person") != "animal"],
            [["c1/s0::elena"]],
            [],
        ),
    )
    result = runner.run_eval("obra-test")
    # Sin el animal: 1 pred vs 1 gold → detección perfecta.
    assert result["detection"]["f1"] == pytest.approx(1.0)
```

> Ajustar el nombre/forma de los símbolos (`_load_gold`, `_load_system_output`, `run_eval`) a los reales del runner tras el cierre de M1. El punto verificable es: un pred marcado `animal` no penaliza la precisión.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_eval_runner.py -k animals_excluded -q`
Expected: FAIL hasta implementar el filtro real dentro de `_load_system_output` (el test de arriba fija el contrato del filtro).

- [ ] **Step 3: Implement**

En `eval/characters/runner.py`, dentro de `_load_system_output`, tras cargar `char_list = char_graph.get_characters_list(...)`, filtrar animales antes de construir entidades y menciones:

```python
        char_list = char_graph.get_characters_list(sess, manuscript_id)
        char_list = [c for c in char_list if c.get("entity_kind", "person") != "animal"]
```

Así tanto las entidades devueltas como los `per_char_mentions` (que iteran sobre `char_list`) excluyen animales de forma consistente.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_eval_runner.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add eval/characters/runner.py tests/unit/test_eval_runner.py
git commit -m "feat(eval): exclude entity_kind=animal from detection and clusters"
```

---

### Task 10: Reglas del prompt (animales, paratexto, descriptores) + bump de versión

**Files:**
- Modify: `backend/extraction/prompts.py:12,14-49`
- Test: `tests/unit/test_extraction_pipeline.py`, `tests/unit/test_prompt_injection.py`

**Interfaces:**
- Produces: `PROMPT_VERSION = 4`; `SYSTEM_PROMPT` con tres reglas nuevas. La defensa anti-inyección existente se mantiene intacta.

- [ ] **Step 1: Write the failing tests**

Añadir a `tests/unit/test_extraction_pipeline.py`:

```python
def test_prompt_version_bumped():
    from backend.extraction.prompts import PROMPT_VERSION

    assert PROMPT_VERSION == 4


def test_system_prompt_mentions_animals():
    from backend.extraction.prompts import SYSTEM_PROMPT

    low = SYSTEM_PROMPT.lower()
    assert "animal" in low and "entity_kind" in low


def test_system_prompt_mentions_paratext_and_relational():
    from backend.extraction.prompts import SYSTEM_PROMPT

    low = SYSTEM_PROMPT.lower()
    assert "paratexto" in low or "créditos" in low or "portada" in low
    assert "parentesco" in low or "abuelo de" in low
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_extraction_pipeline.py -k "prompt_version_bumped or system_prompt_mentions" -q`
Expected: FAIL — `PROMPT_VERSION == 3` y las reglas no existen.

- [ ] **Step 3: Implement**

En `backend/extraction/prompts.py`, cambiar la versión:

```python
PROMPT_VERSION: int = 4
```

Añadir tres reglas al bloque `## Reglas obligatorias` del `SYSTEM_PROMPT` (numeradas 8, 9, 10, tras la regla 7):

```
8. **Animales con nombre**: las mascotas y animales con nombre propio (p. ej. una \
lechuza llamada "Hedwig", un perro "Fluffy") SÍ se anotan como personajes, pero con \
`entity_kind="animal"`. Las personas llevan `entity_kind="person"` (valor por defecto). \
No los omitas: márcalos.
9. **No extraigas paratexto**: si la escena es contenido no narrativo —portada, \
créditos, página de derechos, índice, dedicatoria, "sobre la autora/el autor", \
biografía— NO extraigas personajes: devuelve listas vacías. La autora, traductores e \
ilustradores del libro NO son personajes de la historia. (Un prólogo o prefacio que SÍ \
sea narrativa con personajes se trata con normalidad.)
10. **Descriptores por parentesco no son personajes nuevos**: "el abuelo de Harry", \
"la madre de Elena", "el padre de X" son descripciones, no entidades propias, aunque \
contengan un nombre propio (que pertenece a OTRO personaje). Anótalos como menciones \
con kind="description" enlazadas vía links_to al personaje descrito si es identificable; \
no los declares en new_characters.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_extraction_pipeline.py tests/unit/test_prompt_injection.py -q`
Expected: PASS (la defensa anti-inyección sigue verde: no se tocó el bloque `## Seguridad`).

- [ ] **Step 5: Commit**

```bash
git add backend/extraction/prompts.py tests/unit/test_extraction_pipeline.py
git commit -m "feat(extraction): prompt rules for animals, paratext and relational descriptors (v4)"
```

---

### Task 11: Verificación E2E (reproceso) y cierre documental

**Files:**
- Modify: `docs/known-issues.md` (follow-ups 2, 3, 4)
- Create: resultados frescos en `eval/results/`

**Prerrequisitos (si falta alguno, PARAR y avisar):**
- Docker con Neo4j **de test/desechable** (no la base con datos reales — ver aviso Task 7).
- `.env` con credenciales LLM válidas. Esta task hace llamadas LLM reales (cache invalidada por el bump de versión).

- [ ] **Step 1: Suite completa y lint en verde (sin Neo4j: unit; con Neo4j de test: integración)**

Run: `uv run ruff check backend eval tests && uv run pytest tests/unit -q`
Expected: lint limpio; unit en PASS.

- [ ] **Step 2: Reprocesar HP1 y verificar los tres fixes**

```bash
# Ingesta + extracción de Harry Potter 1 (epub, español)
curl -s -F "file=@<ruta-hp1.epub>" http://127.0.0.1:8000/manuscripts   # anotar manuscript_id
time uv run python -m backend.extraction.run <manuscript_id_hp1>
curl -s "http://127.0.0.1:8000/manuscripts/<id_hp1>/characters" | python -m json.tool
```

Expected, comparado con la demo previa registrada en known-issues:
- NO aparecen la autora, traductores ni ilustradores como personajes (paratexto).
- NO aparecen "Abuelo de Harry Potter" ni descriptores relacionales similares.
- Hedwig/Fluffy/Scabbers aparecen con `entity_kind="animal"`.

- [ ] **Step 3: Reejecutar el eval de las obras del gate (sin regresión)**

```bash
uv run pytest tests/eval -q
```

Expected: gate crafted en PASS (1.0 / 1.0 / 0). Si regresiona, investigar antes de continuar (systematic-debugging), NO ajustar umbrales ni gold.

- [ ] **Step 4: Reejecutar P&P y anotar el delta de precisión**

```bash
time uv run python -m backend.extraction.run <manuscript_id_pp>
uv run python -m eval.characters.runner --work pride-and-prejudice.txt --manuscript-id <id_pp>
```

Expected: la precisión de detección sube respecto a la corrida previa (menos paratexto/descriptores); anotar el número real (no forzarlo).

- [ ] **Step 5: Actualizar known-issues**

En `docs/known-issues.md`, marcar los follow-ups 2, 3 y 4 como resueltos con fecha 2026-07-15 y una línea de resolución cada uno (paratexto vía source_role + regla de prompt; descriptores vía is_unnamed + regla de prompt; animales vía entity_kind marcado por el LLM y excluido del eval). Registrar los números del reproceso (HP1/P&P) como evidencia.

- [ ] **Step 6: Commit**

```bash
git add docs/known-issues.md eval/results/
git commit -m "docs(m1): resolve paratext/relational/animal follow-ups; record re-run metrics"
```

---

## Self-review

- **Cobertura de la spec:** Parte 1 (animales) → Tasks 1, 7, 8, 9, 10. Parte 2 (paratexto) → Tasks 3, 4, 5, 6, 10 (regla de prompt) con el caso del prólogo respetado en Task 3 (`preface` se queda narrativo) y Task 10 (nota explícita). Parte 3 (descriptores) → Tasks 2, 10. Verificación multi-formato y reproceso → Task 11. ✓
- **Tipos consistentes:** `entity_kind: Literal["person","animal"]` idéntico en schema (Task 1), grafo (Task 7, param `str`), pipeline (Task 8), runner (Task 9, lectura con `.get("entity_kind","person")`). `partition_paratext -> (narrative, paratext)` mismo orden en Tasks 3 y 6. `source_role` mismo nombre en Block (Task 3), epub_parser (Task 5) y non_narrative (Task 4). ✓
- **Sin placeholders:** todo el código está escrito; los dos puntos donde el implementador debe ajustar a símbolos reales (entrypoint del pipeline en Task 8, nombres del runner en Task 9) están marcados explícitamente porque dependen del estado post-cierre de M1, no son huecos del plan. ✓
- **Riesgo señalado:** el follow-up #1 (conftest borra sin scope) sigue abierto y afecta a las tasks de integración (7, 8) y al E2E (11); avisado en cada una para usar una base Neo4j desechable. ✓
