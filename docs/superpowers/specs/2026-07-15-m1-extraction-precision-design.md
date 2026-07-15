# Design: M1 — Precisión de extracción (animales, paratexto y descriptores relacionales)

**Fecha**: 2026-07-15
**Milestone**: M1 — Extracción y resolución de personajes (`002-char-extraction-eval`)
**Branch objetivo**: `004-m1-extraction-precision` (por crear)
**Depende de**: M1 ya cerrado (T038/T039); resuelve tres follow-ups abiertos en `docs/known-issues.md`

## Change Log

- **2026-07-15 (inicial):** diseño de los tres follow-ups (animales, paratexto, descriptores).
- **2026-07-15 (rev. 1):** Parte 2 ampliada a tratamiento multi-formato (epub/docx/txt) y
  al caso del prólogo (no se aparta a ciegas; lo decide el LLM por contenido). A petición
  del usuario tras revisar la spec.

---

## Contexto

La demo de Harry Potter 1 (español) y la re-medición de P&P dejaron tres fuentes de
falsos positivos en la extracción de personajes, registradas como follow-ups 2, 3 y 4
en `docs/known-issues.md` (sección "M1 · Follow-ups tras bugfixes + demo HP1"):

1. **Paratexto extraído como personajes** — el extractor sacó a la autora, traductores,
   ilustradores y nombres de la dedicatoria como si fueran personajes de la novela.
2. **Descriptores relacionales que cuelan el filtro** — "Abuelo de Harry Potter",
   "Mr. Darcy's father" pasan `is_unnamed` porque el nombre propio embebido pertenece a
   *otro* personaje, no al descrito.
3. **Mascotas/animales con nombre** — Hedwig, Fluffy, Scabbers, etc. se extraen como
   personajes; el gold de M1 los excluye (~10 falsos positivos en HP1).

Los tres bajan la **precisión** de detección sin ser fallos de resolución. El recall ya
es alto y no hay merges silenciosos; el problema es que entra ruido que no debería.

**Principio de diseño transversal (decidido en brainstorming):** los tres se resuelven
principalmente en el **prompt** —explotando el LLM que ya lee cada escena— y no con
parches deterministas. Como el fix de animales ya obliga a subir `PROMPT_VERSION` y
reprocesar, incorporar los otros dos en el mismo cambio de prompt es coste incremental
cero. Las heurísticas deterministas se conservan solo como **red de seguridad mínima**
donde protegen un mecanismo automático aguas abajo (la fusión por alias del nivel 1).

Queda fuera de esta spec: el umbral de detección 0.90 para novela completa (follow-up 5),
el no determinismo de la cola larga (6), la fuga de nombres canónicos del LLM (7) y la
anotación de menciones para B³ en novelas completas (8).

---

## Los tres arreglos

### Parte 1 — Animales con nombre marcados, no descartados

**Qué:** el LLM etiqueta cada personaje nuevo como persona o animal. El animal se
conserva en el grafo con toda su información (menciones, apariciones, rol), pero queda
**fuera del cómputo del eval** por defecto, de modo que el gold M1 (que no anota
animales) sigue siendo coherente sin tocarlo.

**Por qué así (no un tipo de nodo aparte):** crear una label `:Pet` o un subtipo formal
obligaría a decidir ya la ontología completa de entidades (lugares, organizaciones,
objetos) — decisión de producto fuera del scope de un arreglo de precisión. Un campo en
la ficha del personaje mantiene la puerta cerrada y es reversible: si en el futuro se
quiere que las mascotas relevantes sean ciudadanos de primera, el dato ya está marcado.

**Por qué lo marca el LLM (no una regla determinista):** distinguir "Hedwig es una
lechuza" de una persona es juicio semántico; una lista de nombres de animales no escala
a libros no vistos. El LLM ya lee cada escena, así que es coste cero salvo el reproceso.

**Cambios:**
- `backend/extraction/schemas.py` — `CharacterCandidateOut` gana
  `entity_kind: Literal["person", "animal"] = "person"`. Sube `SCHEMA_VERSION` (2 → 3).
- `backend/extraction/prompts.py` — nueva regla: los animales con nombre se anotan como
  personajes con `entity_kind="animal"`, no se omiten. Sube `PROMPT_VERSION` (3 → 4).
- `backend/graph/characters.py` — persiste `entity_kind` como propiedad del nodo
  `Character` (default `"person"` para nodos existentes; Cypher vive aquí por
  constitución). Lectura (`get_characters_list`, `get_character_detail`) devuelve el campo.
- `eval/characters/runner.py` — al cargar la salida del sistema, excluye del cómputo de
  detección los personajes con `entity_kind="animal"` (el gold no los anota). B³ no se ve
  afectado (opera sobre menciones de personas nombradas).

### Parte 2 — Paratexto del epub (portada, índice, créditos, dedicatoria)

Defensa en dos capas, honrando las dos decisiones del brainstorming (capa cruda limpia
**y** LLM como red):

**Capa cruda (determinista, sin LLM — respeta idempotencia INV-M1-1 y coste-cero de M0):**
- **Raíz del bug:** `backend/ingest/segmentation/chapters.py` define "frontmatter" como
  todo lo anterior al *primer heading*. En epubs reales la portada/dedicatoria/créditos
  llevan su propio `<h1>/<h2>`, así que se cuelan como el "Capítulo 1".
- **Fix:** aprovechar las señales que el propio epub ya declara —no listas de palabras
  frágiles—. `backend/ingest/parsers/epub_parser.py` hoy descarta el flag `linear` del
  spine (`for idref, _linear in book.spine`) e ignora `guide`/`landmarks`, donde el epub
  marca `cover`, `toc`, `frontmatter`, etc. El parser pasa esa señal estructural por
  bloque; la segmentación desvía esos bloques a `NonNarrativeBlock` en vez de a un
  `Chapter`, aunque tengan heading propio.
- `backend/ingest/non_narrative.py` — el enum `NonNarrativeKind` ya incluye `"cover"` y
  `"backmatter"` (hoy nunca asignados). `_detect`/`classify` los emiten a partir de la
  señal estructural del epub, además de la heurística de keywords existente.

**Red semántica (LLM):**
- `backend/extraction/prompts.py` — regla nueva: si la escena es paratexto (portada,
  créditos, índice, dedicatoria, "sobre la autora/el autor"), no extraer personajes.
  Caza lo que la señal estructural no marcara. Incluida en el mismo bump de `PROMPT_VERSION`.

**Multi-formato y el caso del prólogo (refinamiento 2026-07-15):**

La riqueza de la señal estructural degrada por formato, así que el peso relativo de cada
capa cambia:

| Formato | Señal estructural (capa cruda) | Peso de la red LLM |
|---------|--------------------------------|--------------------|
| epub    | Fuerte: `guide`/`landmarks`/spine `linear` declaran cover/toc/frontmatter | Complementaria |
| docx    | Media: estilos de heading de Word, sin roles semánticos | Alta |
| txt (Gutenberg) | Débil: solo marcadores de licencia (ya detectados) + heurística de heading | Principal |

Cuanto más pobre es la estructura, más recae la decisión en el LLM. Por eso la red
semántica es **format-agnostic** y no un extra: para txt/docx es la defensa principal.

**El prólogo NO se excluye a ciegas.** Un prólogo/prefacio/introducción puede ser:
- *paratexto* (nota del autor, agradecimientos) → sin personajes narrativos, o
- *narrativa* (parte de la ficción, con personajes reales que deben extraerse).

Regla de diseño: la **capa cruda es conservadora** — solo desvía a `NonNarrativeBlock`
lo inequívocamente paratextual (cover, toc, copyright, dedicatoria, "sobre el autor").
Secciones ambiguas por naturaleza (prólogo, prefacio, introducción) **no** se apartan
estructuralmente; se dejan pasar y es el **LLM** quien decide por su contenido: si es
narrativa con personajes, los extrae; si es una nota del autor, devuelve vacío. Esto
evita el falso negativo de tirar un prólogo narrativo con personajes de peso.

### Parte 3 — Descriptores relacionales ("Abuelo de Harry Potter")

**LLM primero:**
- **Raíz del bug:** el LLM propone "Abuelo de Harry Potter" como `canonical_name` de un
  personaje nuevo, cuando es una descripción relacional que debería anotarse como mención
  con `kind="description"` enlazada al descrito, no como entidad propia.
- `backend/extraction/prompts.py` — refuerza la regla 7 existente: un descriptor por
  parentesco/relación ("el abuelo de X", "la madre de Y", "X's father") **no** es un
  personaje nuevo, aunque contenga un nombre propio; ese nombre pertenece a *otro*.
  Incluido en el mismo bump de `PROMPT_VERSION`.

**Red mínima determinista (protege la fusión automática por alias del nivel 1):**
- `backend/extraction/registry.py` — `is_unnamed` gana detección de construcciones
  genitivas/posesivas: "\<head relacional\> de/of \<Nombre\>" y "\<Nombre\>'s \<head
  relacional\>". Reutiliza `_GENERIC_HEAD` (lista de parentescos ya existente). Si el head
  es relacional y el único nombre propio aparece tras un genitivo, se trata como sin
  nombre (descriptor) igual que "el anciano".
- **Por qué se conserva la red:** el comentario en `registry.py:70-77` lo justifica —un
  error del LLM aquí "envenena el nivel 1 de la cascada para siempre" (auto-merge
  determinista por alias). La red evita que un fallo del modelo se propague en silencio.
  Aplica en ambos call-sites: `resolution.py:85` (canonical_name) y `registry.py:86` (alias).

---

## Modelo de datos

Único cambio de esquema: propiedad nueva en `Character`.

```cypher
(Character {
    // … campos existentes …
    entity_kind: String   // "person" (default) | "animal"
})
```

- **Idempotencia:** el `MERGE` de `upsert_character` fija `entity_kind` de forma
  determinista según la salida del LLM cacheada. Nodos previos sin la propiedad se leen
  como `"person"` (coalesce en la query de lectura), sin migración destructiva.
- **NonNarrativeBlock:** sin cambios de forma; solo se empiezan a emitir los `kind`
  `"cover"`/`"backmatter"` ya presentes en el enum.

---

## Eval harness

- **Detección:** el runner filtra `entity_kind="animal"` de la salida del sistema antes
  de comparar con el gold. Efecto para el gate: idéntico a excluir animales, pero sin
  perder el dato en el grafo.
- **Golds:** sin cambios. Las obras crafted del gate no contienen animales ni paratexto,
  así que su F1/B³ no cambia. La verificación real ocurre reprocesando HP1/P&P.
- **Regla de honestidad (quality-boundaries):** ninguna métrica se inventa; los animales
  no se anotan en el gold, por eso se excluyen del cómputo en vez de contarse como aciertos.

**Verificación (una sola pasada de reproceso, ya obligada por el bump de prompt):**
- HP1: desaparecen autora/traductores/ilustradores y "Abuelo de…"; las mascotas aparecen
  marcadas `entity_kind="animal"` y fuera de la métrica.
- Gate crafted: sigue en PASS (1.0 / 1.0 / 0), sin regresión.
- P&P: precisión de detección sube al quitar paratexto y descriptores; se anota el delta.

---

## Alcance explícito

**Dentro:**
- `entity_kind` person/animal marcado por el LLM, persistido en `Character`, excluido del eval.
- Paratexto apartado en la capa cruda (señal estructural, más fuerte en epub) + red LLM
  como defensa principal para docx/txt; prólogos ambiguos los decide el LLM por contenido.
- Descriptores relacionales tratados como descripción por el LLM + red determinista en `is_unnamed`.
- Reproceso de verificación de HP1/P&P y actualización de `docs/known-issues.md`.

**Fuera (diferido):**
- Umbral de detección propio para novela completa (follow-up 5) — decisión de política aparte.
- No determinismo de la cola larga (6) — inherente al LLM.
- Anclaje anti-alucinación de nombres canónicos (7) — vigilancia, no fix aquí.
- Anotación de menciones para B³ en novelas completas (8).
- Cualquier categoría de entidad más allá de person/animal (lugares, organizaciones…).

---

## Decision Log

1. **Marcar animales en vez de descartarlos.** Rationale: perder el dato es más caro que
   ignorarlo; Hedwig/Crookshanks tienen peso narrativo real. Trade-off aceptado: hay que
   tocar el esquema del `Character`. (Usuario, brainstorming.)
2. **Campo en `Character`, no un tipo de nodo nuevo.** Rationale: un subtipo formal
   obliga a definir la ontología completa de entidades ahora. Trade-off: la marca es un
   atributo, no una categoría de primera clase — suficiente para M1.
3. **El LLM marca el animal, no una regla determinista.** Rationale: juicio semántico que
   escala a libros no vistos; una lista de nombres no. Trade-off: invalida la cache de
   extracción → reproceso puntual de HP1/P&P con cuota LLM real.
4. **Paratexto: capa cruda determinista + red LLM.** Rationale: M0 debe ser idempotente y
   sin coste (INV-M1-1), así que no usa LLM; pero en vez de hardcodear keywords frágiles,
   lee las señales que el propio epub declara (spine `linear`, `guide`/`landmarks`). El
   LLM de extracción caza lo que se escape. Trade-off: dos capas que mantener.
5. **Descriptores: LLM primero + red mínima.** Rationale: la raíz es que el modelo los
   propone como personaje; se corrige en el prompt. La red determinista se conserva porque
   protege el auto-merge por alias aguas abajo (código lo advierte explícitamente).
   Trade-off: el filtro `is_unnamed` gana complejidad (genitivos multi-idioma).
6. **Los tres en el mismo bump de `PROMPT_VERSION` y un solo reproceso.** Rationale: el
   reproceso ya es obligado por la Parte 1; agrupar es coste incremental cero.

---

## Alternatives Considered

- **Excluir animales del todo (descartar en extracción).** Descartada: pierde info
  irrecuperable sin re-procesar; el usuario quiere conservar mascotas con peso.
- **Tipo de nodo `:Pet` / ontología de entidades tipada.** Descartada por scope: abre
  una decisión de producto grande dentro de un arreglo de precisión.
- **Regla determinista post-LLM para animales (lista de nombres).** Descartada: no escala
  a libros no vistos; el LLM es la única fuente que generaliza.
- **Meter el LLM en la capa de troceado (M0) para clasificar paratexto.** Descartada:
  rompería la idempotencia de M0 (el LLM no es determinista) y añadiría coste por ingesta.
- **Solo prompt, sin red determinista en descriptores.** Descartada: un fallo del LLM
  envenenaría el auto-merge por alias en silencio (riesgo confirmado en el código).
- **Solo capa cruda para paratexto, sin red LLM.** Descartada: la señal estructural del
  epub no siempre está completa; el LLM cubre el hueco a coste cero.
- **Specs separadas por follow-up.** Descartada: comparten el mismo bump de prompt y el
  mismo reproceso; separarlas multiplicaría el coste de verificación (usuario aprobó una).

---

## Open Questions

- **Formato exacto de la señal estructural del epub.** `ebooklib` expone el spine
  `linear` y `book.guide`; la disponibilidad de `landmarks` (EPUB3 nav) varía por libro.
  La implementación decidirá la precedencia (guide > linear > heurística de keywords) y el
  fallback cuando el epub no declare roles. No bloquea el diseño.
- **Señal estructural en docx y txt.** Para docx (estilos de heading de Word) y txt
  (Gutenberg, sin estructura rica) la capa cruda tiene menos con qué trabajar; el diseño
  ya delega en la red LLM como defensa principal para esos formatos (ver tabla arriba),
  pero la lista exacta de heurísticas de heading conservadoras se afina en implementación.
- **Frontera prólogo narrativo vs nota del autor.** Definida a nivel de diseño (la capa
  cruda no aparta prólogos; decide el LLM por contenido). La formulación exacta de la
  regla del prompt para no confundir un prólogo narrativo con paratexto se valida en el
  reproceso de verificación. Si aparece una obra con prólogo ambiguo que el LLM clasifique
  mal, se ajusta el prompt (no la capa cruda).
- **Cobertura multi-idioma de los genitivos.** El patrón "de \<Nombre\>" (es) y "\<Nombre\>'s"
  (en) cubre HP1/P&P; otros idiomas quedan para cuando aparezca una obra que los necesite.

---

## Constitution check

| # | Principio | Estado | Cómo lo cumple |
|---|-----------|--------|----------------|
| I | Eval-first | ✅ | La verificación reprocesa HP1/P&P y confirma que el gate crafted no regresiona antes de dar por buenos los fixes |
| II | Grafo como columna vertebral | ✅ | `entity_kind` es propiedad del `Character`; el paratexto se conserva como `NonNarrativeBlock`, no se borra |
| III | Contratos tipados (Pydantic) | ✅ | `entity_kind` es `Literal["person","animal"]` en `CharacterCandidateOut` |
| IV | Una sola puerta al LLM | ✅ | Solo cambia el prompt y el schema de extracción; M0 no llama al LLM (idempotencia) |
| V | Citas obligatorias | ✅ | Sin cambios: las menciones siguen llevando `quote`/`source_scene_id` |
| VI | Idempotencia | ✅ | `MERGE` fija `entity_kind` de forma determinista; M0 no incorpora no determinismo; nodos previos → `"person"` por coalesce |
| VII | Profundidad antes que amplitud | ✅ | Solo person/animal; ninguna otra categoría de entidad; umbral de novela completa diferido |
