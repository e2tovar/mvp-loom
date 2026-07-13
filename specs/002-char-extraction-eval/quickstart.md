# Quickstart — M1: Extracción y resolución de personajes

**Feature**: `002-char-extraction-eval` · **Fecha**: 2026-06-10

Cómo extraer los personajes de un manuscrito, revisar fusiones dudosas y correr la
eval. Asume el entorno de M0 funcionando (Neo4j + API, ver quickstart de
`001-m0-ingest-segmentation`).

## 0. Requisitos nuevos de M1

```bash
uv sync                                  # instala litellm + deps nuevas
# .env: configurar el proveedor LLM (factory por entorno, ver research R1)

# Perfil OpenCode Go (default desarrollo)
#   LOOM_LLM_MODEL=openai/kimi-k2.5
#   LOOM_LLM_API_BASE=https://opencode.ai/zen/go/v1
#   LOOM_LLM_API_KEY=sk-…                # API key de opencode.ai/auth

# Perfil Azure OpenAI (ocasional, empresa)
#   LOOM_LLM_MODEL=azure/<deployment>
#   AZURE_API_KEY=…
#   AZURE_API_BASE=https://<recurso>.openai.azure.com
#   AZURE_API_VERSION=2024-10-21
```

Cambiar de proveedor es solo cambiar estas variables; el código no se toca. El modelo
usado queda registrado en la cache y en cada resultado de eval.

## 1. Ingerir un libro (M0) y extraer personajes (M1)

```bash
# Si no está ingerido aún (usa 127.0.0.1, no localhost, si Docker ocupa el puerto en IPv6)
curl -F "file=@eval/fixtures/pride-and-prejudice.txt" http://127.0.0.1:8000/manuscripts
# → manuscript_id

# Extracción (proceso largo: una llamada LLM por escena, con cache y progreso)
uv run python -m backend.extraction.run <manuscript_id>
```

Re-lanzar el comando tras un fallo continúa desde la cache (no re-paga escenas ya
extraídas). `--force` ignora la cache.

## 2. Inspeccionar el reparto (DoD: cotejar contra el libro)

```bash
curl "http://127.0.0.1:8000/manuscripts/<id>/characters" | python -m json.tool
```

Revisa que: los personajes principales están, los alias quedaron consolidados en una
sola entidad (Lizzy/Eliza/Miss Bennet → Elizabeth Bennet), los homónimos siguen
separados, y cada entidad trae su primera aparición con cita (SC-008: < 15 min).

## 3. Revisar fusiones dudosas (human-in-the-loop)

```bash
curl "http://127.0.0.1:8000/manuscripts/<id>/merge-candidates"
curl -X POST "http://127.0.0.1:8000/merge-candidates/<candidate_id>/resolve" \
     -H "Content-Type: application/json" -d '{"decision": "accept"}'
```

Las decisiones son finales y sobreviven re-extracciones.

## 4. Ejecutar la eval (gate de CI)

```bash
uv run python -m eval.characters.runner --work pride-and-prejudice   # métricas + JSON en eval/results/
uv run pytest tests/eval -q                                          # gate: falla bajo umbral
uv run pytest                                                        # suite completa
```

Umbrales vigentes (`eval/characters/thresholds.py`): detección **F1 ≥ 0.90**,
resolución **B³ F1 ≥ 0.85**, fusiones erróneas silenciosas **= 0**.

## 5. Definition of Done (M1)

- [ ] Extraer personajes de las ≥2 obras del golden dataset de principio a fin.
- [ ] Detección F1 ≥ 0.90 y resolución B³ ≥ 0.85 sobre el golden dataset (SC-001/002).
- [ ] Cero fusiones erróneas silenciosas; los casos grises están en la cola (SC-003).
- [ ] Toda entidad/aparición rastreable a escena + cita (SC-004).
- [ ] Re-ejecución sin cambios < 10 % del coste (cache) (SC-005).
- [ ] La eval corre con un comando, < 10 min, y bloquea el merge si cae (SC-006/007).

## Mapa de artefactos

| Quiero… | Mirar |
|---------|-------|
| El qué/porqué y criterios | [`spec.md`](./spec.md) |
| Decisiones técnicas | [`research.md`](./research.md) |
| Modelos y esquema de grafo | [`data-model.md`](./data-model.md) |
| Contrato REST + CLI | [`contracts/api.md`](./contracts/api.md) |
| Contrato de salida del LLM | [`contracts/extraction-schema.md`](./contracts/extraction-schema.md) |
| Esquema Neo4j (delta M1) | [`contracts/graph-schema.cypher`](./contracts/graph-schema.cypher) |
| Estrategia de implementación | [`plan.md`](./plan.md) |
