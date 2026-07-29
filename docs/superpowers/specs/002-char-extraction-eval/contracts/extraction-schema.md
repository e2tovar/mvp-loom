# Contrato de extracción LLM — M1

**Feature**: `002-char-extraction-eval` · **Fecha**: 2026-06-10

El contrato Pydantic entre el LLM y el sistema (Principio III). El modelo recibe el
texto de **una escena** + el registro de entidades acumulado, y devuelve exactamente
este esquema vía tool-use forzado. Ninguna otra forma de salida es aceptable.

Versionado: `SCHEMA_VERSION` (entero) en `backend/extraction/schemas.py`; cambiarlo
invalida la cache (junto con `PROMPT_VERSION` de `prompts.py`).

## Entrada (contexto que construye el pipeline, no el LLM)

```python
class RegistryEntry(BaseModel):
    """Entidad ya conocida, pasada como contexto al LLM (README §6)."""
    canonical_name: str
    aliases: list[str]
    role: str                      # protagonist | antagonist | secondary | minor | unknown


class SceneContext(BaseModel):
    scene_id: str
    chapter_title: str | None
    scene_text: str                # texto NO confiable — siempre delimitado en el prompt de usuario
    known_entities: list[RegistryEntry]
```

## Salida (lo que el LLM devuelve, validado)

```python
class MentionOut(BaseModel):
    """Una mención de personaje detectada en la escena."""
    surface: str                   # texto literal de la mención, debe existir en scene_text
    kind: Literal["name", "alias", "title", "description", "pronoun_resolved"]
    links_to: str | None           # canonical_name de una entidad del registro, o None si es nueva
    quote: str                     # la frase completa que contiene la mención (procedencia)


class CharacterCandidateOut(BaseModel):
    """Entidad nueva propuesta (no presente en el registro)."""
    canonical_name: str
    aliases: list[str] = []
    role: Literal["protagonist", "antagonist", "secondary", "minor", "unknown"] = "unknown"
    is_present_in_scene: bool      # aparece físicamente vs solo se habla de él (FR-003)


class SceneExtraction(BaseModel):
    """Salida completa de la extracción de una escena."""
    mentions: list[MentionOut]
    new_characters: list[CharacterCandidateOut]
    present_entities: list[str] = []  # nombres/alias de personajes físicamente
                                       # presentes en la escena, nuevos o conocidos
                                       # (SCHEMA_VERSION 2)
    notes: str | None = None       # ambigüedades que el modelo quiera señalar
```

> **Cambio de contrato (SCHEMA_VERSION 1→2, PROMPT_VERSION 1→2)**: se añadió
> `present_entities` para poder registrar presencia física on-stage de personajes
> *ya conocidos* que reaparecen en escenas posteriores sin ser re-emitidos como
> `new_characters`. Antes de este campo, `is_mentioned_only` solo se fijaba en la
> primera extracción del personaje (vía `new_characters[].is_present_in_scene`);
> si esa primera extracción era una mención, el flag quedaba congelado en `true`
> para siempre aunque el personaje apareciera físicamente después (caso real:
> Elizabeth, protagonista con 273 menciones, marcada `is_mentioned_only=true`).
> Con `present_entities`, el pipeline resuelve esos nombres contra el registro y
> los añade a `present_canonicals`, ganando `APPEARS_IN {kind:'present'}` aunque
> ya existieran. `is_mentioned_only` pasa a derivarse en `recompute_counters`:
> `true` sii el personaje no tiene ninguna relación `APPEARS_IN` con
> `kind='present'`. El bump de versión invalida intencionalmente la cache de
> escenas (`backend/llm/cache.py`) para forzar re-extracción con el nuevo campo.

## Confirmación de fusión (resolución, nivel 2 de la cascada)

```python
class MergeJudgement(BaseModel):
    """Veredicto del LLM sobre si dos entidades son el mismo personaje."""
    same_entity: bool
    confidence: float              # 0.0–1.0; la zona gris [0.5, 0.9) va a cola humana
    rationale: str                 # explicación citando la evidencia
```

## Reglas del contrato

1. **`surface` verificable**: el pipeline valida que cada `surface` existe en
   `scene_text` y deriva los offsets (`start_offset`/`end_offset`) por búsqueda; una
   mención no localizable se descarta y se loggea (el LLM no inventa menciones).
2. **`links_to` cerrado**: debe coincidir con un `canonical_name` del registro
   entregado; un valor desconocido se trata como entidad nueva (fail-safe).
3. **Sin colectivos**: el prompt instruye a no emitir menciones de grupos ("los
   soldados"); si aparecen, la resolución las filtra por heurística (plural + sin
   nombre propio).
4. **Texto no confiable**: `scene_text` se delimita en el bloque de usuario; el prompt
   de sistema prohíbe seguir instrucciones embebidas (FR-013, research R8).
5. **Determinismo operativo**: temperatura 0; la cache por
   `SHA-256(scene_text + PROMPT_VERSION + model + SCHEMA_VERSION)` garantiza que la
   re-ejecución no re-llama al LLM (FR-012).
6. **Agnóstico de proveedor**: el contrato se materializa como tool-calling formato
   OpenAI vía LiteLLM con `tool_choice="required"` (proveedores: OpenCode Go, Azure
   OpenAI u otro compatible, por env — research R1). El par (modelo, proveedor) queda
   registrado en la clave de cache y en cada `EvalResult`: las métricas siempre se
   atribuyen al modelo que las produjo.
