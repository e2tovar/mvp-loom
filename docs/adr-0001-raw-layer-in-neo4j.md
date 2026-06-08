# ADR-0001 — La capa cruda vive en Neo4j desde M0

**Estado**: Aceptada · **Fecha**: 2026-06-05 · **Milestone**: M0

## Contexto

M0 produce la capa cruda inmutable (capítulos y escenas). Había que decidir dónde
persistirla: en el grafo Neo4j desde el inicio, o en un almacén intermedio (JSON/SQLite)
hasta que un milestone posterior la necesitara en el grafo.

## Decisión

Persistir la capa cruda directamente como nodos del grafo (`Manuscript`, `Chapter`,
`Scene`, `NonNarrativeBlock`) en Neo4j 5.x desde M0, con escritura idempotente por
`MERGE` sobre ids derivados del hash del contenido.

## Consecuencias

**A favor**
- Cumple el Principio II de la constitución (el grafo es la única fuente de verdad).
- M1 (personajes) lee directamente de `Scene`/`Chapter` sin migración.
- Levanta `docker-compose` con Neo4j desde M0 (parte del DoD del milestone).
- La identidad por hash + `MERGE` da idempotencia y re-ingestión idéntica (SC-005).

**En contra / costes**
- Los tests de integración requieren Neo4j en ejecución (mitigado: se marcan
  `integration` y se *saltan* si la base no está disponible; el resto del suite corre
  sin DB).

**Alternativas descartadas**
- *JSON/Parquet en disco*: crea un segundo origen de verdad que habría que migrar al
  grafo en M1; contradice el Principio II.
- *SQLite*: mismo problema de doble store; no aporta sobre un requisito ya existente.

## Notas

- El driver `neo4j` 6.x es compatible con el servidor Neo4j 5.x.
- El esquema (constraints/índices) se define en
  `specs/001-m0-ingest-segmentation/contracts/graph-schema.cypher` y se aplica de forma
  idempotente al arrancar la API.
