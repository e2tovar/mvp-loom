# Quickstart — M2 Relaciones

Requiere: Neo4j arriba (`docker compose up -d`), obra ingerida (M0) y
personajes extraídos (M1: `python -m backend.extraction.run <mid>`).

```bash
# 1. Extraer relaciones (segunda pasada, cache en .cache/relations/)
uv run python -m backend.extraction.relations.run <manuscript_id>

# 2. Inspeccionar
curl localhost:8000/manuscripts/<manuscript_id>/relations | jq .

# 3. Evaluar contra el gold (y gate)
uv run python -m eval.relations.runner --work crafted-three-chapters.txt --manuscript-id <mid>
uv run pytest -m eval tests/eval/test_relations_gate.py
```

Umbrales del gate (solo relaciones `extracted`): pares F1 ≥ 0.90, tipo ≥ 0.90
(`eval/relations/thresholds.py`).
