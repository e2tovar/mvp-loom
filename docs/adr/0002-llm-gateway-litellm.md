# ADR-0002 — LLM Gateway: LiteLLM multi-proveedor

**Estado**: Aceptada · **Fecha**: 2026-06-10 · **Milestone**: M1 (`002-char-extraction-eval`)

## Contexto

M1 necesita llamar a un LLM para la extracción de personajes y para juzgar fusiones
dudosas. El sistema debe ser agnóstico de proveedor (Principio IV: una sola puerta),
soportar dos proveedores activos (OpenCode Go en desarrollo, Azure OpenAI para
contraste de calidad) y registrar el coste por llamada.

## Decisión

Se crea `backend/llm/` con:
- `interface.py` — protocolo `LLMClient.complete_structured(system, user, schema)`.
- `litellm_client.py` — implementación usando **LiteLLM**, con tool-calling forzado
  (`tool_choice="required"`), temperatura 0, validación Pydantic y un reintento ante
  `ValidationError`.
- `cache.py` — cache contenido-direccionada (ver ADR implícito en research R6).

**Proveedor seleccionado 100 % por env** (sin código por proveedor):

| Perfil | Variables clave |
|--------|----------------|
| OpenCode Go (default dev) | `LOOM_LLM_MODEL`, `LOOM_LLM_API_BASE`, `LOOM_LLM_API_KEY` |
| Azure OpenAI | `LOOM_LLM_MODEL=azure/<deployment>`, `AZURE_API_KEY/BASE/VERSION` |

**El modelo lo decide la eval**: se empieza con `openai/kimi-k2.5`; si no alcanza los
umbrales (F1 ≥ 0.90, B³ ≥ 0.85), cambiar de modelo es un cambio de `.env`.

## Alternativas consideradas

| Opción | Rechazada por |
|--------|--------------|
| **LangChain** (`init_chat_model` + `with_structured_output`) | Más dependencias; magia entre prompt y modelo complica la cache por versión; duplicaría la puerta que la constitución ya exige propia |
| **SDK `openai` directo** (`OpenAI(base_url=…)`) | Requeriría reimplementar a mano normalización de tool-calling entre perfiles, reintentos y conteo de coste que LiteLLM ya da |
| **`instructor`** | Capa de reintentos acoplada a la firma del proveedor; oculta el mecanismo de tool-calling |
| **SDK `anthropic`** | El usuario no dispone de API de Anthropic en M1 |
| **Salida JSON en texto libre** | Prohibido por la constitución (Principio III) |

## Consecuencias

- LiteLLM solo se importa en `backend/llm/`; el código de aplicación nunca sabe qué
  proveedor responde.
- `response_cost` se loguea en DEBUG; permite auditar el coste por extracción.
- El par (modelo, proveedor) queda registrado en la clave de cache y en cada
  `EvalResult`, asegurando que las métricas se atribuyen al modelo que las produjo.
- **Riesgo**: la calidad de structured outputs varía entre modelos abiertos. El gate
  de eval es el árbitro; ningún modelo se adopta sin pasar los umbrales.
- **M4**: OpenCode Go no ofrece embeddings; cuando lleguen los `Passage` (M4), Azure
  OpenAI (`text-embedding-3-*`) u Ollama local los cubrirán via LiteLLM sin cambio de
  interfaz.
