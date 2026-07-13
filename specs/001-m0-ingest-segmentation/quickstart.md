# Quickstart — M0: Ingestión y segmentación

**Feature**: `001-m0-ingest-segmentation` · **Fecha**: 2026-06-04

Cómo arrancar el entorno, ingerir un manuscrito y verificar la segmentación. Asume
Python 3.12+, `uv` y Docker disponibles.

## 1. Levantar Neo4j + API

```bash
docker compose up -d            # Neo4j 5.x (bolt://localhost:7687, http://localhost:7474)
uv sync                         # instala dependencias del backend
uv run uvicorn backend.api.app:app --reload
```

Al arrancar, la API aplica el esquema del grafo (constraints/índices de
`contracts/graph-schema.cypher`) de forma idempotente.

## 2. Ingerir un manuscrito

```bash
# EPUB / TXT de dominio público (Project Gutenberg) o DOCX
curl -F "file=@eval/fixtures/pride-and-prejudice.epub" \
     http://localhost:8000/manuscripts
```

Respuesta `201` (o `200` si ya estaba ingerido): incluye `manuscript_id`,
`chapter_count`, `scene_count`. Reenviar el mismo archivo devuelve `created: false` y
no duplica nada (idempotencia).

## 3. Verificar la segmentación (DoD de M0)

```bash
curl http://localhost:8000/manuscripts/<manuscript_id>/structure | jq .
```

Revisa que:
- el número y orden de capítulos coincide con el libro;
- las escenas por capítulo cuadran con los separadores del original;
- los `snippet` corresponden al inicio real de cada escena;
- no aparece boilerplate (licencia/índice) dentro de capítulos/escenas.

Esto es la verificación manual que cierra el DoD (SC-008: < 10 min para un libro).

## 4. Ejecutar el proto-eval (gate de CI)

```bash
uv run pytest tests/eval -q          # exactitud de capítulos (SC-002) y escenas (SC-003)
uv run pytest                        # toda la suite (unidad + integración + eval)
```

El eval compara la segmentación contra la anotación de referencia en `eval/fixtures/`.
Si la exactitud cae bajo umbral (95 % capítulos / 90 % separadores), el test falla y
bloquea el merge.

## 5. Definition of Done (M0)

- [ ] `docker compose up` levanta Neo4j y la API.
- [ ] Ingerir un `.epub`, un `.txt` y un `.docx` produce capa cruda en el grafo.
- [ ] `GET …/structure` permite confirmar visualmente la segmentación de un libro.
- [ ] Re-ingerir el mismo contenido es idéntico y no duplica (SC-005).
- [ ] El proto-eval pasa los umbrales SC-002/SC-003 sobre ≥2 novelas anotadas.
- [ ] El texto narrativo se reconstruye sin pérdida (SC-004) y sin boilerplate (SC-007).

## Mapa de artefactos

| Quiero… | Mirar |
|---------|-------|
| El qué/porqué y criterios | [`spec.md`](./spec.md) |
| Decisiones técnicas | [`research.md`](./research.md) |
| Modelos y esquema de grafo | [`data-model.md`](./data-model.md) |
| Contrato de la API | [`contracts/api.md`](./contracts/api.md) |
| Esquema Neo4j | [`contracts/graph-schema.cypher`](./contracts/graph-schema.cypher) |
| Estrategia de implementación | [`plan.md`](./plan.md) |
