# Design: M2 — Relaciones y atributos de personajes

**Fecha**: 2026-06-15  
**Milestone**: M2 — Relaciones  
**Branch objetivo**: `003-relations-attributes` (por crear)  
**Depende de**: M1 (`002-char-extraction-eval`) — requiere `Character` nodes poblados

---

## Contexto

M1 extrajo personajes, alias y apariciones por escena. M2 añade la siguiente capa de
conocimiento: **qué relaciones existen entre personajes** y **qué sabemos de cada uno**
(apariencia física y motivación central). Es la primera vez que el grafo conecta
personajes entre sí.

Queda fuera de M2: continuidad (qué sabe/ignora cada personaje en cada punto de la
historia) — se difiere a M3+.

---

## Modelo de datos

### Nuevas estructuras en Neo4j

```cypher
// Relación entre personajes
(Character)-[:RELATES_TO {
    kind:           String,       // enum: ver abajo
    description:    String,       // texto libre: "amor no correspondido en los primeros capítulos"
    source_scene_id: String,      // escena donde el hecho está mejor evidenciado
    confidence:     Float         // 0.0–1.0
}]->(Character)

// Atributo de personaje
(Character)-[:HAS_ATTRIBUTE]->(Attribute {
    attribute_id:   String,       // "{character_id}:attr:{dimension}" — determinista
    dimension:      String,       // "appearance" | "motivation"
    value:          String,       // texto libre
    source_scene_id: String,
    confidence:     Float
})
```

### Enum de tipos de relación

| Valor | Significado |
|-------|-------------|
| `FAMILY` | Parentesco (padre/hijo, hermanos, cónyuges, primos) |
| `ROMANTIC` | Relación amorosa, atracción, cortejo |
| `FRIENDLY` | Amistad, alianza, confianza mutua |
| `ANTAGONIST` | Enemistad, rivalidad, conflicto activo |
| `PROFESSIONAL` | Vínculo laboral o de servicio (empleador/empleado, cliente/proveedor) |
| `SOCIAL` | Conocidos, vecinos, relación de estatus sin otro tipo aplicable |

### Unicidad e idempotencia

- **Relaciones**: `MERGE` sobre `(from_id, to_id, kind)`. Un solo registro por par
  ordenado y tipo. Varios tipos distintos entre el mismo par son válidos
  (Darcy-Elizabeth: ROMANTIC; Mrs. Bennet-Mr. Bennet: FAMILY + ROMANTIC).
- **Atributos**: `MERGE` sobre `(character_id, dimension)`. Un valor por dimensión
  por personaje. Re-ejecución sin cambios no crea duplicados.
- **Dirección**: las relaciones son dirigidas tal como las extrae el LLM. En el eval,
  el matching es sobre el par no ordenado.

---

## Pipeline de extracción

M2 corre como un **segundo pase** sobre las escenas, después de que M1 ha poblado el
elenco completo. Esta separación es intencional: el segundo pase tiene acceso al elenco
resuelto, por lo que el LLM puede enlazar aliases tardíos ("el señor de Netherfield")
a la entidad ya conocida en lugar de inferir sobre información parcial.

```
CLI: python -m backend.relations.run <manuscript_id>
```

**Flujo por escena:**

1. Consulta Neo4j: personajes conocidos del manuscrito (nombre canónico + aliases)
2. Llama al LLM con: texto de escena + lista de personajes + prompt M2 versionado
3. LLM devuelve `SceneRelations` (Pydantic): lista de `RelationOut` + lista de `AttributeOut`
4. Resolución: descarta items con `confidence < umbral`; actualiza confianza si el
   registro ya existe y la nueva es mayor
5. Escribe con `MERGE` idempotente

**Caché**: SHA-256(texto_escena + PROMPT_VERSION_M2 + modelo + SCHEMA_VERSION_M2) —
independiente de la cache de M1. Re-ejecución sin cambios no llama al LLM.

**Fallo explícito**: si no existen `Character` nodes para el `manuscript_id`, el CLI
falla con error claro antes de procesar ninguna escena.

### Estructura de módulos nuevos

```
backend/relations/
├── __init__.py
├── schemas.py      # SceneRelations, RelationOut, AttributeOut (Pydantic)
├── prompts.py      # prompt M2 versionado (PROMPT_VERSION_M2)
├── pipeline.py     # orquesta: escenas → LLM → graph
└── run.py          # CLI: python -m backend.relations.run <manuscript_id>

backend/graph/
├── relations.py    # MERGE RELATES_TO, lecturas por manuscrito/personaje
└── attributes.py   # MERGE HAS_ATTRIBUTE, lecturas por personaje

backend/api/
└── routes_relations.py   # tres endpoints nuevos (ver sección API)
```

---

## Eval harness

### Principio
Eval-first es no negociable. El gate de CI bloquea la integración si la F1 de
detección de relaciones cae bajo umbral. Los atributos (texto libre) no entran en el
gate de M2 — se inspeccionan manualmente.

### Formato del gold dataset

`eval/fixtures/<obra>.relations.gold.json`:

```json
{
  "work": "pride-and-prejudice.txt",
  "relations": [
    {"from": "Elizabeth Bennet", "to": "Fitzwilliam Darcy", "kind": "ROMANTIC"},
    {"from": "Elizabeth Bennet", "to": "Jane Bennet",        "kind": "FAMILY"},
    {"from": "Fitzwilliam Darcy", "to": "George Wickham",    "kind": "ANTAGONIST"}
  ]
}
```

### Métrica

**Detección de relaciones — F1**: matching greedy sobre pares no ordenados + `kind`.
Clave de emparejamiento: `frozenset({from_alias, to_alias}) × kind`. La `description`
es texto libre y no entra en el cómputo.

**Umbral inicial**: `relation_detection_f1 ≥ 0.80`. Más bajo que el F1 de personajes
(0.90) porque las relaciones implícitas son genuinamente ambiguas entre categorías
adyacentes (FRIENDLY vs SOCIAL, ROMANTIC vs FAMILY para cónyuges).

### Estructura de módulos nuevos

```
eval/fixtures/
└── <obra>.relations.gold.json    # anotación manual por obra (≥2 obras)

eval/relations/
├── __init__.py
├── metrics.py          # precision/recall/F1 sobre pares (from, to, kind)
├── runner.py           # carga gold + consulta Neo4j → EvalResult + JSON en eval/results/
└── thresholds.py       # RELATION_DETECTION_F1_THRESHOLD = 0.80

tests/eval/
└── test_relations_gate.py    # SKIP si no hay extracción M2; FAIL si bajo umbral
```

---

## API

Tres endpoints nuevos en `backend/api/routes_relations.py`:

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/manuscripts/{id}/relations` | Lista de relaciones. Filtrable por `?character_id=` y `?kind=`. |
| `GET` | `/manuscripts/{id}/characters/{char_id}/profile` | Perfil completo: aliases + apariciones (M1) + atributos (M2). Vista unificada sin múltiples llamadas. |
| `GET` | `/manuscripts/{id}/relations/graph` | Estructura para visualización: nodos `{character_id, name}` + arcos `{from, to, kind, description}`. |

No hay endpoints de escritura: las relaciones con confianza baja se descartan en el
pipeline, no se encolan para revisión humana.

---

## Alcance explícito

**Dentro de M2:**
- Relaciones tipadas (enum + descripción libre) con procedencia de escena
- Atributos: apariencia física y motivación central, texto libre con escena
- Eval harness: F1 de relaciones, gate de CI, gold para ≥2 obras
- API de lectura: relaciones, perfil de personaje, grafo de relaciones

**Fuera de M2 (diferido):**
- Continuidad: qué sabe/ignora cada personaje por escena → M3+
- Atributos adicionales (personalidad, ocupación, estatus) → M3+
- Evolución temporal de relaciones → M3 (eventos y cronología)
- UI de visualización → M7
- Revisión humana de relaciones dudosas → no existe en M2; el umbral filtra

---

## Constitution check

| # | Principio | Estado | Cómo lo cumple M2 |
|---|-----------|--------|-------------------|
| I | Eval-first | ✅ | Gate de CI sobre F1 de relaciones; gold annotado ≥2 obras antes de considerar completo |
| II | Grafo como columna vertebral | ✅ | `RELATES_TO` y `Attribute` en Neo4j; cache de extracción en disco, no en el grafo |
| III | Contratos tipados (Pydantic) | ✅ | `SceneRelations`, `RelationOut`, `AttributeOut` — ninguna salida de texto libre sin estructura |
| IV | Una sola puerta al LLM | ✅ | M2 usa `backend/llm/` igual que M1; `backend/relations/` nunca importa litellm directamente |
| V | Citas obligatorias | ✅ | Toda relación y atributo lleva `source_scene_id` |
| VI | Idempotencia | ✅ | Cache por hash; MERGE idempotente; re-ejecución sin cambios no llama al LLM |
| VII | Profundidad antes que amplitud | ✅ | Solo relaciones y dos dimensiones de atributo; continuidad, personalidad y ocupación diferidas |
