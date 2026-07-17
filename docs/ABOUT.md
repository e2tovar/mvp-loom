# Entendiendo Loom

Loom lee una novela completa y la convierte en un grafo de conocimiento: una base de datos
donde los personajes, las escenas y los hechos de la historia son nodos conectados entre sí,
en lugar de texto plano que hay que volver a leer en cada consulta.

Imagina a una lectora meticulosa que lee el libro tomando fichas —una por personaje, una por
escena— y las clava en un corcho uniéndolas con hilos. Ese corcho con fichas e hilos es el
grafo. Loom lo construye automáticamente.

Este documento describe qué hace Loom y cómo modela la información. El setup y los comandos
viven en los `quickstart.md` de cada spec.

---

## El grafo es la fuente de verdad

La mayoría de los proyectos de IA sobre texto parten el documento en trozos y, en cada
consulta, vuelven a preguntarle al modelo sobre esos trozos. Es caro, lento y propenso a
alucinaciones.

Loom hace lo contrario: extrae el conocimiento una sola vez y lo guarda estructurado en un
grafo Neo4j. A partir de ahí, las preguntas se responden consultando el grafo, no releyendo
el libro. Todo lo que se construye después —relaciones entre personajes, línea temporal,
detección de errores de continuidad, el wiki— deriva de ese grafo, nunca del texto original.

---

## La ontología

La ontología es el catálogo de qué tipos de entidades existen y cómo se conectan. En Neo4j se
expresa con **nodos** (las entidades), **relaciones** (los vínculos dirigidos entre ellas) y
**propiedades** (los datos que cuelgan de unos y otras). El grafo crece en capas, una por
milestone.

### Capa cruda: la estructura del libro

Al ingerir un manuscrito, Loom lo descompone en su estructura física:

```
(Manuscript)-[:HAS_CHAPTER]->(Chapter)-[:HAS_SCENE]->(Scene)
```

- **`Manuscript`** — el libro completo: título, formato de origen, recuento de palabras.
- **`Chapter`** — un capítulo, con su orden narrativo y su título.
- **`Scene`** — la unidad mínima de texto. Contiene el texto real (`text`) y sus offsets de
  inicio y fin dentro del libro.

Escenas y capítulos se encadenan mediante `NEXT_SCENE` y `NEXT_CHAPTER`, de modo que el grafo
preserva el orden de lectura. Esta capa es inmutable: una vez ingerido el libro, ningún proceso
posterior modifica estos nodos. Es el cimiento sobre el que se levanta todo lo demás.

### Capa de personajes: quién aparece y dónde

Sobre la estructura cruda se añade el reparto:

```
(Manuscript)-[:HAS_CHARACTER]->(Character)
(Character)-[:HAS_MENTION]->(Mention)-[:IN_SCENE]->(Scene)
(Character)-[:APPEARS_IN {kind, mention_count}]->(Scene)
```

- **`Character`** — un personaje con identidad consolidada. Agrupa todas sus designaciones bajo
  un `canonical_name` y una lista de `aliases` (Elizabeth Bennet reúne `"Lizzy"`, `"Eliza"`,
  `"Miss Bennet"`). Es una entidad de conocimiento, no un fragmento de texto.
- **`Mention`** — una ocurrencia literal en el texto: la palabra exacta (`surface`), su tipo y
  los offsets que la anclan a la escena. Es la evidencia que sostiene al personaje.
- **`HAS_MENTION`** vincula al personaje con cada una de sus menciones; **`APPEARS_IN`** resume
  en qué escenas aparece y si está físicamente presente o solo es nombrado (`kind`).

Un `Character` existe únicamente si lo sustenta al menos una `Mention`. Nada se inventa: todo
hecho es trazable hasta un fragmento exacto del texto original. Esta es la regla que garantiza
cero alucinaciones por diseño.

### La cola de revisión

Cuando el sistema no puede decidir con certeza si dos menciones corresponden al mismo personaje
—¿son "Elena" y "la doctora" la misma persona?— no adivina: registra un caso de revisión humana.

```
(MergeCandidate)-[:PROPOSES_MERGE]->(Character)   // apunta a las dos entidades en duda
```

- **`MergeCandidate`** — una fusión candidata pendiente. Almacena la `confidence` del sistema,
  el `rationale` que justifica la sospecha y la evidencia necesaria para decidir.
- La resolución es manual: `accept` fusiona las entidades, `reject` las mantiene separadas de
  forma permanente.
- Las decisiones humanas son inmutables ante el pipeline: una re-extracción nunca vuelve a
  proponer un par rechazado ni deshace una fusión aceptada.

---

## Identificadores deterministas

Cada nodo recibe un identificador derivado de su contenido, no un autoincremental. Un
`Character` es `{manuscript_id}:ch:{slug-del-nombre}`; una `Mention`, `{scene_id}:m{offset}`.

Gracias a esto, el pipeline se re-ejecuta sin crear duplicados. Toda escritura usa `MERGE` —el
upsert de Cypher: crea si no existe, actualiza si existe— de modo que dos extracciones del mismo
libro convergen al mismo grafo. De ahí que el proceso sea reanudable y barato: una interrupción
a mitad se retoma sin repetir trabajo.

---

## Organización del código

| Capa | Responsabilidad | Frontera |
|------|-----------------|----------|
| `backend/graph/` | Todo el Cypher, lectura y escritura | Ningún Cypher fuera de aquí |
| `backend/llm/` | Única puerta al modelo de IA, vía LiteLLM | Ningún otro módulo importa `litellm` |
| `backend/extraction/` | El pipeline: escena → IA → resolución → grafo | Orquesta; no accede a la DB ni al LLM directamente |
| `backend/api/` | Endpoints FastAPI de inspección | Solo accede al grafo vía `backend/graph/` |
| `eval/` | Harness de evaluación y datasets de oro | Mide la calidad y bloquea regresiones |

El pipeline carga las escenas en orden narrativo, entrega cada una a la IA junto con el registro
de personajes ya conocidos, valida la respuesta, resuelve identidades —entidad nueva o ya
existente— y persiste el resultado en el grafo. Una escena ya procesada se sirve desde la cache,
sin coste adicional.

---

## Estado del proyecto

| Milestone | Aporte al grafo | Estado |
|-----------|-----------------|--------|
| M0 — Ingesta | `Manuscript` / `Chapter` / `Scene` | ✅ Completo |
| M1 — Personajes | `Character` / `Mention` / `MergeCandidate` + eval | ✅ Completo |
| M2 — Relaciones | `RELATES_TO` entre personajes, atributos, continuidad | 🔜 Planificado |
| M3 — Eventos | Nodos de evento y orden cronológico real | 🔜 Planificado |
| M4 — Retrieval | `Passage` y búsqueda híbrida (GraphRAG) | 🔜 Planificado |
| M5 — Wiki | Páginas markdown generadas desde el grafo | 🔜 Planificado |

Cada milestone solo añade nodos y relaciones; nunca altera las capas previas.

---

## Eval-first

Ninguna funcionalidad se valida por inspección visual. Cada milestone incluye un dataset de oro
anotado a mano y métricas automáticas —precisión, recall, F1— que se ejecutan en CI y bloquean
el merge si la calidad cae. Un cambio de prompt o de modelo solo entra si supera los umbrales
vigentes: detección F1 ≥ 0.90, resolución B³ ≥ 0.85 (B³ se mide sobre las obras con
gold anotado a nivel de mención; sin esa anotación el eval reporta "no medido").

---

## Por dónde empezar

- `CLAUDE.md` — convenciones del proyecto y feature activa.
- `specs/` — cada milestone reúne su `spec.md` (qué y por qué), `data-model.md` (la ontología)
  y `quickstart.md` (el flujo ejecutable de principio a fin).
- `specs/002-char-extraction-eval/data-model.md` — referencia completa del modelo de M1.
- Stack: Python 3.12 · FastAPI · Neo4j 5.x · LiteLLM · pytest (markers `unit`, `integration`, `eval`).

El camino más corto para interiorizar la ontología es levantar Neo4j, ejecutar el quickstart de
M1 contra una obra de `eval/fixtures/` y explorar el resultado en el Neo4j Browser: ver el grafo
poblarse es la mejor forma de entenderlo.
