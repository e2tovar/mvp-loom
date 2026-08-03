# El norte del grafo

**Fecha**: 2026-07-18 · **Revisado**: 2026-08-02 tras contraste con la literatura
de NLP narrativo y KG-RAG · **Propósito**: mapa de la ontología objetivo y de sus
consumidores futuros, para que cada capa nueva se modele pensando en quién
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
| `Passage` (`text`,`embedding`) | **unidad de recuperación y fuente de toda cita** | ⬜ pendiente | **M4** (adelantado) |
| `Utterance` (`speaker`,`addressee`,`quote_type`) | separa lo narrado de lo dicho por un personaje | ⬜ pendiente | **M5** (nuevo) |
| `Manuscript.tech_sheet` | convenciones tipográficas de la obra; **parámetro de corrida**, firmado por humano | ⬜ pendiente | **M4** (nuevo) |
| `Scene.summary` jerárquico / `place` / `time_marker` | señal por escena, con cita | ⬜ pendiente | M6 |
| `Scene.narrative_plane` | marco vs relato enmarcado; hace tratable la cronología de M7 | ⬜ pendiente | **M6** (nuevo) |
| `Event` (+`INVOLVES`) a nivel escena | qué ocurre, con posición cronológica **inferida** | ⬜ pendiente | M7 |
| `Location` como nodo (+`SET_IN`) | — | ❌ descartado → `Scene.place` | — |
| `PlotThread`/`Theme`/`Motif` | — | ❌ fuera del grafo → análisis (M9) | — |
| `CommunitySummary` | — | ❌ descartado → jerarquía de resúmenes (M6) | — |
| `Scene.sentiment` | — | ❌ descartado, no medible por escena | — |
| `Scene.tension_score` (0–1) | — | ❌ descartado como escalar → delta ordinal en M9 | — |

Los descartes de agosto de 2026 y su evidencia están en README §5 (tabla "Descartados
del modelo, con motivo") y §12 ("Por qué este orden y no el anterior"). Resumen del
criterio: **cada tipo nuevo en el catálogo tiene un coste medible en la calidad de
extracción de todo lo demás** — al ampliar el catálogo de tipos permitidos, el F1 de
tripletas cae de forma sustancial. Un nodo solo entra si su beneficio está medido.

**Módulos backend aún inexistentes**: `analysis/`, `retrieval/`, `wiki/`,
`orchestration/` — toda la mitad "consumidora" del sistema es terreno virgen;
sus contratos hoy son solo prosa del README (§7, §8, §10).

**Lo que la literatura NO resuelve**: no existe una ontología de consenso para
ficción. Los proyectos serios del campo (GOLEM, Drammar, y otros) modelan cosas
distintas y son mutuamente incompatibles; el propio grupo de GOLEM describe su
modelado del personaje como preliminar. No hay esquema que adoptar: el catálogo
propio hay que justificarlo internamente, con medición. Lo que sí es consenso es
el núcleo — estructura, personajes, vínculos, rasgos — y en eso M0–M3 coinciden.

---

## 2. Consumidores del grafo y qué exigen de él

Cada fila es un consumidor futuro; la última columna es lo que la capa
correspondiente del grafo debe garantizar **hoy** para no bloquearlo mañana.

| Consumidor | Qué hace | Qué exige del grafo |
|---|---|---|
| **Detector de continuidad** (`analysis/`) | mismo `key`, `value` incompatible → alerta | `Attribute` + su `AttributeEvidence` por escena (cita literal `value_quote` y orden narrativo); valores normalizados comparables (no prosa libre); distinción atributo estático vs con estado (`status`) |
| **Timeline / flashbacks** (`analysis/`, M9) | orden narrativo vs cronológico | `Event.order_narrative` y `order_chronological` separados, el segundo **relativo y marcado `inferred`**; `Scene.time_marker` literal con cita; `BEFORE` **derivado** de la posición, no extraído |
| **Retrieval + GraphRAG** (`retrieval/`, M4) | Q&A local/global con citas obligatorias | `Passage` enlazado a `Scene`; toda entidad alcanzable desde sus evidencias (la cadena entidad→evidencia→escena→cita ya existe en M1/M2/M3 y debe mantenerse en cada capa nueva) |
| **Story Wiki** (`wiki/`, M8) | páginas markdown por entidad, diff-aware | IDs estables (slugs deterministas → nombres de página); descriptores legibles por humanos (p. ej. `RELATES_TO.descriptor`); saber qué escenas sustentan cada página para regenerar solo lo afectado |
| **Agente que lee diálogo** (M5 en adelante) | distinguir lo narrado de lo dicho | `Utterance` con hablante y destinatario; sin esa marca, una afirmación de un personaje que miente entra al grafo como hecho |
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
7. **Frontera de admisión: recomputable y auditable, nunca veredicto**
   (añadido 2026-08-02). Va al grafo lo que cumple las tres condiciones: (a) es
   recomputable de forma determinista desde evidencia cruda ya persistida, **sin
   volver a llamar al LLM**; (b) está anclado a escena y cita, o es función
   explícita de cosas que lo están; (c) va versionado con el `prompt_version` que
   lo produjo. **No va el veredicto**: "esto es un error de continuidad", "aquí
   decae el ritmo", "el tema es la venganza", "este objeto se paga en el cap. 20".
   Eso es una consulta sobre el grafo.

   *Por qué la frontera no es "extraído vs derivado"*: esa formulación prohibiría
   también los resúmenes jerárquicos, que son derivados precomputados y de lo poco
   con beneficio medido en preguntas globales. Y sería incoherente con lo ya
   construido: `RELATES_TO.confidence` y `AttributeEvidence.confidence` ya son
   juicios del modelo materializados. La línea correcta es reversible/auditable.

   *Corolario que afecta a M7*: `order_chronological` es un **derivado**, no un
   hecho extraído. Cae del lado admisible —se recomputa y se ancla a
   `time_marker`— pero lleva marca `inferred` y sus consumidores lo tratan como
   pista, no como dato.

8. **Cada tipo nuevo se paga en calidad** (añadido 2026-08-02). Ampliar el
   catálogo de tipos permitidos degrada de forma medible la extracción de todo lo
   demás. Un nodo o una propiedad solo entra si su beneficio está medido contra un
   baseline; "podría ser útil algún día" no basta.
9. **El contexto que una escena recibe es texto del autor, no salida del modelo**
   (añadido 2026-08-03). Cuando una capa necesita contexto de fuera de la escena, se
   le dan los párrafos literales de la escena vecina — nunca el resumen ni los hechos
   que otra capa interpretó de ella. Tres consecuencias que lo hacen no negociable:
   la huella de caché sigue siendo determinista; **desaparece el efecto dominó**
   (corregir la escena 3 no invalida las 297 siguientes, porque el texto crudo no
   cambia); y el resultado deja de depender del orden de procesamiento, con lo que
   las escenas se pueden paralelizar. Además es lo que impide arrastrar
   interpretaciones del modelo capa sobre capa. Excepción única: la cronología (M7)
   sí consume lo extraído, pero corre **después** de que todas las escenas estén
   procesadas, sobre el conjunto completo — no escena a escena, así que no hay
   dependencia hacia delante. Corolario operativo: **todo lo que el prompt recibe
   entra en la clave de caché** (la deuda §9 de `known-issues.md` es exactamente esto
   incumplido en M1).
10. **Lo que se puede decidir con una regla sale del prompt** (añadido 2026-08-03).
    Si una decisión es mecánica dada la ficha técnica o el estado del grafo, se aplica
    en código y no se le pide al modelo. Ejemplos: resolver el "yo" narrativo a un
    `character_id` cuando la ficha declara quién narra ese tramo; rechazar la
    aparición de un personaje del plano marco en una escena del plano narrado.
    **Cada cosa que se mueve del prompt al código es una cosa que ya no puede
    alucinar** — y deja de depender de que el modelo obedezca una instrucción.

**Consecuencia práctica**: el riesgo de "construir el grafo con la ontología
equivocada" está amortiguado por (4): mientras la evidencia cruda con cita
persista, cambiar reglas de agregación, añadir propiedades derivadas o montar
consumidores nuevos es barato. Lo único caro de arreglar a posteriori es una
evidencia **no capturada** o capturada **sin procedencia**.

---

## 4. Implicaciones inmediatas para M4–M7 (revisado 2026-08-02)

M3 quedó cerrado; sus decisiones de modelado (valores normalizados comparables,
evidencia por escena con `value_quote`, catálogo cerrado, y **no colapsar valores
contradictorios**) se mantienen. Lo que cambia es lo que viene detrás.

- **M4 · `Passage` primero, y con eval propio.** Es la unidad de recuperación y la
  fuente de toda cita, y es lo único con ganancia medida sobre novelas. Hasta que
  exista, **no hay forma de saber si M2 y M3 aportan algo**: todo lo que se sabe de
  ellos es F1 contra un gold incompleto, que no mide utilidad. Regla que hereda cada
  capa posterior: *si no bate a un baseline de recuperación por pasajes, no entra.*
- **M5 · `Utterance`.** Sin saber quién habla, el grafo no distingue un hecho narrado
  de un hecho **dicho por un personaje que miente**. En novela contemporánea eso es la
  mitad del texto. Es además la capa más fiable del campo, así que es barata en riesgo.
- **M6 · La escena es la unidad, y el resumen es jerárquico.** Escena→bloque→obra
  top-down, no agrupación bottom-up por comunidades. El lugar baja a propiedad de
  escena con cita; el sentimiento no se modela.
- **M7 · La cronología es interpretación, no dato.** Posición relativa con empates y
  con "no sé" admitido; `BEFORE` derivado, nunca extraído. Los proyectos de referencia
  del campo colocan las unidades en una línea de precedencia relativa, sin marcas
  absolutas, y definen el hecho narrativo como unidad *inferida*.
- **La detección de continuidad sigue siendo consumidor** (`analysis/`, M9), no capa
  de extracción — y ahora con respaldo: los detectores de incoherencias aciertan en
  torno a tres cuartos en el mejor caso y bajan mucho en texto largo. Materializar ese
  veredicto congelaría falsos positivos que después el Q&A citaría como hecho.
- **Los atributos con estado** (`status` vivo/muerto) siguen necesitando semántica de
  transición, no de igualdad. Y el detector no podrá distinguir un error real de un
  cambio legítimo hasta que exista M7: sin cronología, en una novela no lineal todo
  cambio parece contradicción.

## 4b. Decisión de arquitectura: la wiki es híbrida (grafo + prosa)

Respaldada por deep-research (2026-07-18, 26 fuentes, 21 claims confirmados con
voto adversario; ver `docs/research/2026-07-18-wiki-grafo.md` si se archiva).

**Decisión**: la Story Wiki (M6) **NO se deriva solo del grafo**. Se construye
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

**Consecuencia para el roadmap**: la wiki (M8) **depende del nodo `Passage`
(M4)** como co-fuente — no es derivable solo del grafo. Ya estaba implícito
(`Passage` = "fuente de toda cita"); ahora es decisión respaldada. Tras la revisión
de agosto de 2026 `Passage` se adelanta a M4, con lo que deja de ser un riesgo de
planificación para la wiki.

**Guardrails opcionales**: round-trip check (verbalizar → reconstruir grafo →
conservar lo que reconstruye bien) como *filtro*, no como prueba de equivalencia;
regeneración diff-aware disparada por triple **o** pasaje cambiado.

**Pendiente de validar en dominio**: la evidencia mide en finanzas/construcción,
no en narrativa literaria. Re-medir tasas de alucinación/cobertura en la novela
real con el eval-harness antes de fijar umbrales de M5.

---

## 5. Huecos conocidos (sin dueño hoy)

- **No se ha medido si el grafo aporta.** El hueco de fondo, y el que motivó
  reordenar el roadmap: no existe ninguna medición de si M1–M3 mejoran una
  respuesta frente a buscar en el texto. Se cierra con el eval de M4.
- **Esquema de la wiki sin contrato**: qué tipos de página, frontmatter y
  enlaces — solo visión (README §8). Se contrata en M8; no bloquea M4–M7.
- **M3 sin diagnóstico en novela real**: solo hay corridas sobre obra sintética
  (12 tripletas). Ver README §12, "Precondición antes de M4".
- **El transporte de idioma no está validado.** Las cifras del campo son de
  literatura en inglés de los siglos XVIII-XIX. El español omite el sujeto de
  forma rutinaria, y ninguna medición de resolución de personajes cruza lengua
  ni siglo. Si el corpus objetivo es novela contemporánea en español, los
  umbrales del campo son orientativos, no predictivos.
- ~~**`Location`, `PlotThread`, `Theme`, `Motif` sin milestone**~~: resuelto
  2026-08-02 — descartados del grafo con motivo (README §5). `Location` baja a
  `Scene.place`; trama, tema y motivo pasan a análisis (M9).
- ~~**`Passage` inexistente**~~: sigue sin existir, pero ya no es hueco sin
  dueño — es M4, el siguiente milestone.
- ~~**`docs/ABOUT.md` desactualizado**~~: resuelto al cerrar M3 — la tabla de
  estado ya separa M2 (solo relaciones) de M3 (atributos) y documenta la capa
  de atributos. La detección de continuidad sigue pendiente de spec propia
  (consumidor de esta capa, fuera del grafo por ahora).
