# El norte del grafo

**Fecha**: 2026-07-18 · **Propósito**: mapa de la ontología objetivo y de sus
consumidores futuros, para que cada capa nueva (M3+) se modele pensando en quién
la va a leer — no solo en qué extrae. No es una spec: es el criterio contra el
que se contrastan las specs.

**Idea central**: el grafo no es el producto final; es el **substrato** que
agentes posteriores (detector de continuidad, timeline, GraphRAG, generador de
wiki, editores/analistas) explorarán para hacer su trabajo. La wiki (patrón
LLM-Wiki de Karpathy, README §8) es su complemento navegable: se **deriva del
grafo**, nunca del texto. Todo lo que no esté bien anclado en el grafo no
existirá para ninguno de ellos.

---

## 1. Ontología objetivo vs estado actual

Fuente: README §5. Estado verificado contra `backend/graph/schema.py` y specs.

| Pieza | Rol en la ontología | Estado | Milestone |
|---|---|---|---|
| `Manuscript`/`Chapter`/`Scene` (+`NEXT_*`) | estructura y orden de lectura | ✅ en grafo | M0 |
| `Character`/`Mention`/`APPEARS_IN`/`MergeCandidate` | reparto resuelto + evidencia | ✅ en grafo | M1 |
| `RELATES_TO`/`RelationEvidence` | red de vínculos + evidencia | ✅ en grafo | M2 |
| `Attribute` | hechos por personaje (`key`,`value_norm`,`AttributeEvidence`) | ✅ en grafo | M3 |
| `Event` (+`BEFORE`,`INVOLVES`) | orden narrativo vs cronológico | ⬜ pendiente | bloque M3 |
| `Location` (+`SET_IN`) | dónde ocurre cada escena | ⬜ sin milestone asignado |  |
| `PlotThread`/`Theme`/`Motif` (+`PLANTED_IN`/`PAID_OFF_IN`) | tramas, temas, foreshadowing | ⬜ sin milestone asignado |  |
| `Passage` (`text`,`embedding`) | **unidad de recuperación y fuente de toda cita** | ⬜ pendiente | M4 |
| `CommunitySummary` | resúmenes jerárquicos GraphRAG | ⬜ pendiente | M4 |
| `Scene.summary`/`tension_score`/`sentiment`/`time_marker` | señal por escena para arcos/timeline | ⬜ pendiente | bloque M3/M4 |

**Módulos backend aún inexistentes**: `analysis/`, `retrieval/`, `wiki/`,
`orchestration/` — toda la mitad "consumidora" del sistema es terreno virgen;
sus contratos hoy son solo prosa del README (§7, §8, §10).

---

## 2. Consumidores del grafo y qué exigen de él

Cada fila es un consumidor futuro; la última columna es lo que la capa
correspondiente del grafo debe garantizar **hoy** para no bloquearlo mañana.

| Consumidor | Qué hace | Qué exige del grafo |
|---|---|---|
| **Detector de continuidad** (`analysis/`) | mismo `key`, `value` incompatible → alerta | `Attribute` con `asserted_in_scene`, cita literal y orden narrativo; valores comparables (no prosa libre); distinción atributo estático vs con estado (`status`) |
| **Timeline / flashbacks** (`analysis/`) | orden narrativo vs cronológico, tau de Kendall | `Event.order_narrative` y `order_chronological` separados; `Scene.time_marker`; `BEFORE` entre eventos |
| **Retrieval + GraphRAG** (`retrieval/`, M4) | Q&A local/global con citas obligatorias | `Passage` enlazado a `Scene`; toda entidad alcanzable desde sus evidencias (la cadena entidad→evidencia→escena→cita ya existe en M1/M2 y debe mantenerse en cada capa nueva) |
| **Story Wiki** (`wiki/`, M5) | páginas markdown por entidad, diff-aware | IDs estables (slugs deterministas → nombres de página); descriptores legibles por humanos (p. ej. `RELATES_TO.descriptor`); saber qué escenas sustentan cada página para regenerar solo lo afectado |
| **Agentes editores/analistas** (futuros) | insights, revisiones, informes | procedencia total (ningún hecho sin cita), marca `extracted`/`inferred` para no presentar deducciones como hechos, evidencia cruda persistida (re-agregable sin re-extraer) |

---

## 3. Principios que hacen el grafo a prueba de futuro

Ya operativos en M0–M2; **toda capa nueva los hereda como obligación**:

1. **Aditividad** — cada milestone solo añade nodos/aristas; nunca modifica
   capas previas (INV-M2-3 generaliza a INV-Mn).
2. **Procedencia constitucional** — todo hecho rastrea a escena + cita literal.
   Es lo que mata la alucinación y lo que la wiki y el Q&A citarán.
3. **IDs deterministas + MERGE** — re-ejecutar converge al mismo grafo; los IDs
   son estables entre corridas (la wiki y los agentes pueden referenciarlos).
4. **Evidencia cruda separada del agregado** — el par `Mention→Character` y
   `RelationEvidence→RELATES_TO` se replica en cada capa (`AttributeEvidence→
   Attribute` en M3). El agregado es recomputable; **añadir una señal derivada
   nueva no exige re-extraer el libro**. Este es el colchón que abarata los
   errores de ontología.
5. **`extracted` vs `inferred`** — las deducciones se admiten pero jamás sin
   marca; los gates de eval bloquean solo sobre `extracted`.
6. **Universo cerrado por escena** — el LLM solo referencia entidades del cast
   entregado; entidades nuevas no nacen en capas derivadas.

**Consecuencia práctica**: el riesgo de "construir el grafo con la ontología
equivocada" está amortiguado por (4): mientras la evidencia cruda con cita
persista, cambiar reglas de agregación, añadir propiedades derivadas o montar
consumidores nuevos es barato. Lo único caro de arreglar a posteriori es una
evidencia **no capturada** o capturada **sin procedencia**.

---

## 4. Implicaciones inmediatas para M3 (atributos)

- `Attribute` se modela para sus consumidores: valores normalizados y
  comparables (el detector de continuidad compara igualdad/transición, no
  prosa), `asserted_in_scene` + cita (retrieval y wiki), keys de catálogo
  cerrado (eval medible) — mismo patrón enum+descriptor que M2.
- La **detección** de continuidad es un consumidor (`analysis/`), no parte de
  la extracción: spec propia sobre el grafo ya poblado.
- Los atributos con estado (`status` vivo/muerto) necesitan semántica de
  transición, no de igualdad — el modelo debe distinguir ambas clases desde el
  contrato.

## 4b. Decisión de arquitectura: la wiki es híbrida (grafo + prosa)

Respaldada por deep-research (2026-07-18, 26 fuentes, 21 claims confirmados con
voto adversario; ver `docs/research/2026-07-18-wiki-grafo.md` si se archiva).

**Decisión**: la Story Wiki (M5) **NO se deriva solo del grafo**. Se construye
híbrida: el grafo aporta estructura y navegación; la prosa original —re-anclada
vía la procedencia escena+cita— aporta el matiz. Regla mnemónica: *el grafo dice
QUÉ contar y CÓMO enlazarlo; los pasajes originales dicen CON QUÉ PALABRAS.*

**Por qué** (evidencia, no intuición):
- Generar prosa solo desde triples es una tarea *graph-to-text* con su propio
  riesgo de faithfulness (alucina relaciones, omite hechos). El grafo **no** es
  automáticamente más seguro que resumir texto — solo mueve dónde ocurre el error.
- Todas las arquitecturas competitivas (KG2RAG, SemRAG, HybridRAG, BifrostRAG,
  GraphRAG) son híbridas: el grafo **organiza la recuperación sobre la prosa**,
  no la reemplaza; el híbrido bate a grafo-solo y a texto-solo.
- El grafo gana en preguntas de entidad/multi-hop; la **prosa cruda gana en
  preguntas abstractivas** donde la información no está enunciada (subtexto,
  ironía, tono) — ahí re-anclar en el pasaje recupera lo que el grafo tira.
- La procedencia fina escena+cita que el proyecto ya tiene es justo lo que hace
  la faithfulness **verificable**, no solo menor.

**Matiz honesto**: la versión fuerte "el grafo pierde *hechos* que el texto sí
tiene" fue **refutada** en la investigación. El grafo es fiable como registro de
hechos; lo que pierde es lo **no-enunciado**. Por eso el híbrido, no por
desconfiar del grafo como fuente de hechos.

**Consecuencia para el roadmap**: la wiki (M5) **depende del nodo `Passage`
(M4)** como co-fuente — no es derivable solo del grafo. Ya estaba implícito
(`Passage` = "fuente de toda cita"); ahora es decisión respaldada.

**Guardrails opcionales**: round-trip check (verbalizar → reconstruir grafo →
conservar lo que reconstruye bien) como *filtro*, no como prueba de equivalencia;
regeneración diff-aware disparada por triple **o** pasaje cambiado.

**Pendiente de validar en dominio**: la evidencia mide en finanzas/construcción,
no en narrativa literaria. Re-medir tasas de alucinación/cobertura en la novela
real con el eval-harness antes de fijar umbrales de M5.

---

## 5. Huecos conocidos (sin dueño hoy)

- **Esquema de la wiki sin contrato**: qué tipos de página, frontmatter y
  enlaces — solo visión (README §8). Se contrata en M5; no bloquea M3/M4.
- **`Passage` inexistente**: hasta M4 no hay unidad de recuperación; la wiki y
  el Q&A dependen de él.
- **`Location`, `PlotThread`, `Theme`, `Motif`**: en la ontología objetivo pero
  sin milestone asignado en el roadmap actual.
- ~~**`docs/ABOUT.md` desactualizado**~~: resuelto al cerrar M3 — la tabla de
  estado ya separa M2 (solo relaciones) de M3 (atributos) y documenta la capa
  de atributos. La detección de continuidad sigue pendiente de spec propia
  (consumidor de esta capa, fuera del grafo por ahora).
