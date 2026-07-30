# Quickstart — M3 Atributos

## La vía corta (gate de CI, sin coste)

```bash
make up      # Neo4j
make seed    # siembra el grafo desde las respuestas congeladas (gratis)
make gates   # los tres gates en modo estricto
```

`make seed` no gasta cuota LLM: las respuestas de las obras crafted están
versionadas en `eval/fixtures/llm-cache/`. Si cambias el prompt o el modelo, esas
respuestas dejan de acertar y el sembrado volverá a llamar al LLM — es lo
correcto: cambiar el prompt obliga a re-medir.

## Manual, sobre un manuscrito propio

Requiere: Neo4j arriba (`docker compose up -d`), obra ingerida (M0) y
personajes extraídos (M1: `python -m backend.extraction.run <mid>`).

```bash
# 1. Extraer atributos (tercera pasada, cache en .cache/attributes/)
uv run python -m backend.extraction.attributes.run <manuscript_id>

# 2. Inspeccionar
curl localhost:8000/manuscripts/<manuscript_id>/attributes | jq .

# 3. Evaluar contra el gold (y gate)
uv run python -m eval.attributes.runner --work crafted-attributes.txt --manuscript-id <mid>
```

Umbral del gate: F1 de tripletas `(personaje, key, value_norm)` ≥ 0.90
(`eval/attributes/thresholds.py`). La cita literal no se evalúa en el gate.
