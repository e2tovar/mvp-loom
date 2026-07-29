# Feature Specification: M3 — Capa de atributos de personaje + eval harness

**Feature Branch**: `feature/m3-attributes` (spec `004-m3-attributes`)

**Created**: 2026-07-19

**Status**: Draft

**Input**: Brainstorm de M3 (2026-07-19). Decisión de roadmap: el bloque "M2" del
README (relaciones + atributos + continuidad) se descompone; M2 (spec 003) entregó
relaciones; esta spec cubre el segundo tercio — **solo atributos**. La detección de
continuidad es una spec de análisis posterior que consume esta capa. Contexto
arquitectónico en `docs/graph-north.md`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Extraer los atributos fijos de cada personaje (Priority: P1)

Sobre un manuscrito con personajes ya extraídos y resueltos (capa M1), el sistema
identifica los **atributos de identidad y físicos invariantes** de cada personaje
—color de ojos, pelo, altura, cicatrices/marcas, edad, género— y su **estado
vital** (vivo/muerto), y los registra como hechos anclados a escenas concretas con
su cita textual. Cada valor afirmado conserva la escena y la frase que lo sustenta.

**Why this priority**: Es la materia prima de la detección de continuidad (el DoD
del bloque M2 del README: "ojos azules en cap.2 / verdes en cap.18"). Sin los
atributos fichados con procedencia, ningún análisis posterior de continuidad,
ninguna página de personaje de la wiki y ninguna consulta de rasgos es posible.
El grafo pasa de "quién se relaciona con quién" a "quién es cada quién".

**Independent Test**: Se procesa una novela con capa M1 completa y se obtiene, por
personaje, la lista de atributos con su valor, clase, procedencia y evidencias; se
coteja contra los rasgos reales del libro. Entrega valor por sí sola: el autor ve
la ficha física de su reparto.

**Acceptance Scenarios**:

1. **Given** un manuscrito con personajes extraídos (M1), **When** se ejecuta la
   extracción de atributos, **Then** el sistema produce, por personaje, atributos
   con `key` del catálogo cerrado, valor normalizado, clase (estático/con estado),
   conteo de evidencias y cita de sustento.
2. **Given** un rasgo enunciado en el texto ("sus ojos azules"), **When** se
   extrae, **Then** queda registrado como evidencia de atributo con la cita literal
   y la escena de origen.
3. **Given** un personaje cuyo mismo `key` aparece con **valores distintos en
   escenas distintas** (ojos azules en una escena, verdes en otra), **When** se
   agrega, **Then** el grafo conserva **ambos valores** como nodos de atributo
   separados bajo el mismo par (personaje, `key`), cada uno con sus evidencias —
   nunca se elige un valor "ganador" que descarte al otro.
4. **Given** un atributo con estado (`status`), **When** se extrae, **Then** queda
   marcado con su clase para que un consumidor posterior aplique semántica de
   transición; esta spec no implementa esa lógica.
5. **Given** cualquier atributo registrado, **When** el usuario lo consulta,
   **Then** puede rastrearlo hasta las escenas y citas que lo sustentan.
6. **Given** una escena sin atributos afirmados de ningún personaje del cast,
   **When** se procesa, **Then** la salida es vacía válida; no se inventa nada.

---

### User Story 2 - Medir la calidad de los atributos con un dataset de oro (Priority: P2)

El equipo dispone de una anotación de referencia de atributos para las obras de
prueba. Un arnés de evaluación compara la salida del sistema contra esa referencia
y produce métricas comparables entre ejecuciones que actúan como **puerta de
calidad**.

**Why this priority**: Tesis eval-first del proyecto: sin métrica, los atributos
extraídos solo *parecen* correctos. Sin la eval, la US1 no se puede declarar
terminada, y el futuro detector de continuidad heredaría ruido no medido.

**Independent Test**: Con un gold de atributos y una salida cualquiera, el arnés
produce precisión/exhaustividad/F1 de extracción de tripletas `(personaje, key,
valor)`, y falla ruidosamente bajo umbral. Verificable con salidas sintéticas
(perfecta, vacía, con errores conocidos).

**Acceptance Scenarios**:

1. **Given** un gold de atributos de una obra, **When** se ejecuta el arnés,
   **Then** se obtienen precisión/exhaustividad/F1 de detección de tripletas
   `(personaje, key, valor_normalizado)`, con desglose por clase de `key`
   (estático vs con estado).
2. **Given** dos ejecuciones (antes/después de un cambio), **When** se comparan sus
   resultados, **Then** las métricas son directamente comparables y la regresión es
   visible.
3. **Given** una métrica bloqueante bajo umbral en las obras del gate, **When**
   corre la verificación de calidad, **Then** el resultado es un fallo explícito
   que bloquea la integración.

---

### User Story 3 - Inspeccionar las fichas de atributos (Priority: P3)

El usuario consulta los atributos de una obra de forma inspeccionable: por
personaje, cada `key` con su valor (o valores, si hay más de uno), clase,
procedencia, conteo de evidencias y primera evidencia, para cotejarlos con el libro
sin interfaz gráfica.

**Why this priority**: La verificación manual es el complemento del gate automático
y el entregable visible del milestone. Es P3 porque la extracción y la eval
funcionan sin el endpoint, pero el DoD exige salida inspeccionable.

**Acceptance Scenarios**:

1. **Given** una obra con atributos extraídos, **When** el usuario consulta la
   ficha de un personaje, **Then** ve cada `key` con su(s) valor(es), clase,
   conteo de evidencias y primera evidencia; los `key` con más de un valor son
   visibles como tales (señal cruda para el futuro detector de continuidad).

---

### User Story 4 - Re-extracción idempotente y barata (Priority: P4)

Re-ejecutar la extracción de atributos sobre un manuscrito sin cambios reutiliza el
trabajo por escena desde la cache; si cambia una escena, solo se recomputa lo
afectado y la agregación se rehace de forma determinista.

**Acceptance Scenarios**:

1. **Given** un manuscrito ya procesado, **When** se re-ejecuta sin cambios,
   **Then** el resultado converge al mismo grafo y el trabajo LLM no se repite.
2. **Given** un cambio en una escena, **When** se re-ejecuta, **Then** solo esa
   escena pasa por el LLM y la agregación por (personaje, `key`) se recalcula con
   las evidencias vigentes.

---

### Edge Cases

- **Mismo `key`, varios valores** (ojos azules / verdes): válido y **conservado sin
  colapsar** — es la señal que consumirá el detector de continuidad. Esta capa no
  la juzga.
- **Cambio legítimo narrado** (se tiñe el pelo, envejece, cicatriz nueva): esta
  capa lo registra como otro valor con su escena; **decidir si es error o cambio
  legítimo es del detector posterior**, no de M3.
- **Valor vago o de rango** (`age` = "unos cuarenta"): se admite con normalización
  tolerante; ver Open Questions sobre si `age` entra en el set estático inicial.
- **Atributo de un personaje `is_mentioned_only`**: válido si la escena lo enuncia
  ("su difunta madre, de ojos grises"); se ancla a esa escena.
- **Personajes fuera del cast entregado**: cualquier evidencia que los referencie
  se rechaza en validación; el LLM no puede introducir entidades nuevas.
- **Escena sin atributos**: salida vacía válida; no se inventa nada.
- **Atributo no perteneciente al catálogo cerrado**: se rechaza en validación (el
  LLM no puede inventar `key` nuevos).
- **Texto con instrucciones embebidas**: el manuscrito es texto no confiable; jamás
  se interpreta como instrucciones (mismo principio que M1/M2).
- **Obras en español e inglés**: la extracción y la normalización de valores
  funcionan en ambos idiomas de las obras de prueba (el valor normalizado es
  independiente del idioma de la cita).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST extraer, por escena, evidencias de atributo
  únicamente para personajes del **cast entregado** (personajes de la capa M1
  presentes o mencionados en la escena, filtrando `entity_kind = "person"`); toda
  referencia fuera del cast MUST rechazarse en validación.
- **FR-002**: Las salidas del motor MUST validarse contra un esquema tipado; cada
  evidencia MUST usar un `key` del **catálogo cerrado** (`eye_color`, `hair`,
  `height`, `scar`, `age`, `gender`, `status`); un `key` fuera del catálogo MUST
  rechazarse.
- **FR-003**: Cada evidencia de atributo MUST registrar: personaje, `key` del
  catálogo, **valor normalizado** (`value_norm`), cita textual literal de la escena
  (`value_quote`), confianza y escena de origen.
- **FR-004**: El sistema MUST asignar a cada `key` una **clase** — `static`
  (comparable por igualdad) o `stateful` (`status`, comparable por transición). La
  clase MUST persistir en el grafo. La **lógica** de comparación/transición queda
  fuera de esta spec (la aplica el detector de continuidad posterior).
- **FR-005**: El sistema MUST consolidar las evidencias por par `(personaje, key)`
  mediante reglas deterministas (sin LLM) **conservando todos los `value_norm`
  distintos**: cada valor distinto produce un nodo de atributo con sus evidencias.
  El sistema MUST NOT elegir un valor dominante que descarte a los demás.
- **FR-006**: Toda evidencia y todo atributo MUST conservar procedencia rastreable:
  evidencia → escena + cita; nodo de atributo → sus evidencias y su primera
  evidencia en orden narrativo.
- **FR-007**: La extracción MUST ser idempotente y cacheada: el trabajo por escena
  se reutiliza cuando no cambian contenido de escena, cast ni versión de prompt;
  re-ejecutar sin cambios converge al mismo grafo.
- **FR-008**: M3 MUST NOT modificar ninguna propiedad de las capas M0/M1/M2
  (`Manuscript`/`Chapter`/`Scene`/`Character`/`Mention`/`RELATES_TO`/
  `RelationEvidence`/…); solo añade nodos y relaciones nuevos.
- **FR-009**: El sistema MUST mantener un gold de atributos versionado para las
  obras del gate (crafted) y un gold parcial de atributos principales para al menos
  una novela real (diagnóstico).
- **FR-010**: El arnés MUST calcular precisión/exhaustividad/F1 de detección de
  tripletas `(personaje, key, value_norm)`, con desglose por clase de `key`. La
  cita literal no se evalúa en el gate.
- **FR-011**: La eval MUST actuar como puerta bloqueante sobre las obras crafted;
  la novela real se reporta como diagnóstico no bloqueante.
- **FR-012**: Los resultados de eval MUST registrarse de forma comparable entre
  ejecuciones (obra, métricas, umbrales, `git_sha`, versión de prompt, modelo).
- **FR-013**: El sistema MUST exponer los atributos de una obra de forma
  inspeccionable vía API (por personaje: `key`, valor(es), clase, procedencia,
  conteo de evidencias, primera evidencia).
- **FR-014**: El contenido del manuscrito MUST tratarse como texto no confiable.
- **FR-015**: Ejecutar M3 sobre un manuscrito sin capa M1 MUST producir un error
  explícito, nunca una salida vacía silenciosa.
- **FR-016**: El fallo de una escena (validación agotada tras reintentos) MUST NOT
  abortar la obra: se registra, se salta y la agregación opera con lo disponible.
- **FR-017**: Esta spec MUST NOT emitir alertas de continuidad, comparar valores
  entre sí, ni aplicar semántica de transición; esas capacidades pertenecen a la
  spec de detección de continuidad posterior. M3 solo construye y persiste la
  materia prima.

### Key Entities *(include if feature involves data)*

- **Atributo (Attribute)**: nodo por `(personaje, key, value_norm)`: `key` del
  catálogo cerrado, valor normalizado, clase (`static`/`stateful`), conteo de
  evidencias, primera evidencia. Varios valores distintos del mismo `key` para un
  personaje producen varios nodos (no se colapsan).
- **Evidencia de atributo (AttributeEvidence)**: nodo por personaje, `key` y escena
  — el hecho crudo que sustenta el atributo: valor normalizado, cita literal,
  confianza, escena. Es al atributo lo que `Mention` es a `Character` y
  `RelationEvidence` a `RELATES_TO`.
- **Gold de atributos**: anotación de referencia por obra: tripletas por `gold_id`
  de personaje (reusa los ids del gold de M1), `key`, `value_norm` esperado, clase.
- **Resultado de eval**: métricas de una ejecución (detección de tripletas, split
  por clase de `key`), comparable entre ejecuciones.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Detección de tripletas `(personaje, key, value_norm)` con **F1 ≥
  0,90** sobre el gold de las obras crafted.
- **SC-002**: El **100 %** de atributos y evidencias es rastreable hasta escena y
  cita de origen.
- **SC-003**: Cero nodos de atributo que referencien personajes inexistentes o
  fuera del cast del manuscrito (verificado por invariante).
- **SC-004**: Todo `key` con dos o más `value_norm` distintos para un personaje
  queda representado con un nodo por valor; cero colapsos (verificado por
  invariante) — la señal de continuidad se preserva íntegra.
- **SC-005**: Re-ejecutar sin cambios consume menos del **10 %** del coste/tiempo
  de la primera corrida y produce un grafo equivalente.
- **SC-006**: La eval completa corre con un solo comando en **menos de 10 minutos**
  en el entorno de desarrollo.
- **SC-007**: Una métrica bloqueante bajo umbral produce fallo automático y visible
  que bloquea la integración.
- **SC-008**: El usuario puede revisar las fichas de atributos de una novela y
  cotejarlas con el libro en **menos de 15 minutos** usando solo la salida
  inspeccionable.

## Assumptions

- **Solo atributos**: la **detección de continuidad** (comparación de valores,
  alertas, semántica de transición vivo→muerto) queda **fuera de alcance** — spec
  de análisis posterior que consume esta capa. Esta spec construye la materia prima.
- **Contrato M1 cerrado**: M3 consume la capa M1 según los contratos de
  `docs/superpowers/specs/002-char-extraction-eval/`. El cast entregado al LLM filtra
  `entity_kind = "person"`. Nada de esta spec depende de detalles internos de M1.
- **Catálogo de `key` inicial**: los 7 `key` son un punto de partida (invariantes
  físicos/identidad + estado vital), recalibrable con la primera medición real, con
  el cambio registrado. Mismo patrón que el enum de tipos de M2.
- **Normalización de valores**: el LLM emite `value_norm` (token canónico,
  independiente del idioma) además de la cita. La granularidad del vocabulario
  queda en Open Questions; se arranca con normalización libre y se revisa tras
  medir.
- **Sin cola de revisión humana**: un nodo de atributo erróneo es aditivo y
  reversible; el control de calidad es métrico + procedencia. El patrón
  `MergeCandidate` no aplica a atributos en M3.
- **Aislamiento de la base de tests**: los tests de integración de M3 dependen del
  mismo aislamiento de base que M1/M2 (wipes con scope). Prerequisito heredado, no
  parte del alcance de esta spec.
- **Coste**: tercera pasada LLM sobre el libro, mismo orden de magnitud que M1/M2,
  amortiguada por cache por hash.
- **Idioma**: obras de prueba en inglés y/o español.

## Decision Log

| # | Decisión | Rationale / trade-off aceptado |
|---|----------|--------------------------------|
| 1 | Frontera del milestone: **solo construcción de atributos**; detección de continuidad fuera | La detección es análisis, no construcción; el propio README la sitúa en `analysis/` y como métrica de eval, no en el modelo del grafo. Es también el primero de muchos consumidores del grafo (`docs/graph-north.md`). Se acepta descomponer el bloque "M2" del roadmap por segunda vez (relaciones ya salió aparte). |
| 2 | Scope de atributos: invariantes físicos/identidad + `status` (vivo/muerto) | Cubre los gazapos más típicos (rasgo físico contradictorio, muerto que reaparece) con mínimo riesgo de falso positivo aguas abajo. Atributos mutables (posesiones, títulos, ubicación) fuera: explotarían el ruido del futuro detector. |
| 3 | **Conservar todos los valores distintos por (personaje, key); no colapsar** | Es lo contrario a la agregación de M2. Colapsar a un valor dominante destruiría la señal misma del gazapo antes de que el detector la vea. "Mismo key + varios nodos de valor" *es* la señal de continuidad, servida en bandeja. |
| 4 | Dos clases de `key` (`static`/`stateful`), etiqueta ahora, lógica después | La clase es propiedad intrínseca del atributo y el detector la necesitará; guardarla es barato. Implementar transiciones ahora sería construir el detector, que está fuera de alcance. |
| 5 | Taxonomía híbrida: `key` de catálogo cerrado + `value_norm` normalizado | El catálogo cerrado y el valor normalizado hacen la eval medible por igualdad exacta; la cita conserva el matiz para producto/wiki. Mismo patrón enum+descriptor que M2. |
| 6 | Arquitectura: tercera pasada por escena sobre el cast resuelto | Consistente con M1/M2 (patrón triple contrato, universo cerrado, cache por hash, MERGE idempotente, aditivo). No toca capas previas. Se acepta el coste de una pasada LLM adicional. |
| 7 | Eval: gate en crafted, diagnóstico en novela real; métrica = F1 de tripletas | Mismo patrón que M1/M2. Gate barato y determinista; señal real sin bloquear por anotación laboriosa. |
| 8 | Sin cola de revisión humana para atributos | El modo de fallo es blando (nodo aditivo y reversible), al contrario que las fusiones de M1. Control por métrica + procedencia. |
| 9 | La wiki (M6) que consumirá estos atributos será **híbrida** (grafo + prosa) | Decisión respaldada por deep-research (`docs/graph-north.md` §4b): la wiki no se deriva solo del grafo. No afecta el alcance de M3, pero fija que `value_quote` (la cita) es dato de primera clase, no accesorio: es el re-ancla de la wiki. |

## Alternatives Considered

- **Incluir el detector de continuidad en esta spec (bloque M2 del README
  completo)**: cumpliría el DoD original en un solo milestone, pero acopla
  construcción y análisis, agranda el milestone y mezcla dos evals distintas
  (F1 de extracción vs precisión de alertas). Descartada: el detector es un
  consumidor del grafo, se modela mejor como spec propia sobre el grafo poblado.
- **Colapsar a un valor dominante por (personaje, key)** (como M2 con el tipo de
  relación): más limpio de consultar, pero **destruye la señal de continuidad**.
  Descartada frontalmente: contradice el propósito de la capa.
- **Vigilar todos los atributos (posesiones, títulos, afiliación)**: máxima
  cobertura, pero la mayoría son mutables → el futuro detector se ahogaría en
  falsos positivos (el modo de fallo crítico del README). Descartada como arranque;
  ampliable luego cambiando el catálogo.
- **Solo `key` / solo valor libre**: descartadas por perder la eval por igualdad
  exacta (valor libre) o el matiz (solo `key`).
- **Normalización con vocabulario controlado por `key` desde el día uno**: más
  fiable pero laborioso de definir por adelantado y frágil ante idiomas y matices.
  Diferida: se arranca con normalización libre del LLM y se promueve a vocabulario
  controlado por `key` si la primera medición muestra fallos de casamiento.
- **Detección durante la extracción (marcar el cambio al fichar)**: daría señal
  temprana, pero acopla extracción y juicio y complica contrato y gold. Descartada;
  el juicio vive en el detector posterior, que ve el libro completo.

## Open Questions

- **Granularidad de normalización de `value_norm`**: ¿basta el token libre
  normalizado por el LLM, o hace falta vocabulario controlado por `key` para que el
  futuro detector no falle casando "azul"/"azulado"/"blue"? A confirmar tras la
  primera medición; probablemente empuje trabajo hacia la spec del detector.
- **`age` en el set estático** — *RESUELTO (2026-07-19, primera medición real)*:
  el modelo mal-atribuye la edad por diálogo ("Tienes cuarenta años…") e infiere
  edad de adjetivos vagos ("el viejo Daniel"). Se **excluye del gate bloqueante**
  (queda en el catálogo como diagnóstico best-effort). Ver `eval/attributes/
  thresholds.py::GATE_KEYS`.
- **`gender` fuera del gate** — *RESUELTO (2026-07-19)*: el modelo no enuncia el
  género desde nombres/pronombres (recall 0 medido). Se extrae y anota, pero **no
  bloquea** el gate (best-effort), igual que `age`. Revisar con otro modelo/prompt.
- **`scar`/`hair` como semi-mutables**: una cicatriz nueva o un corte de pelo son
  cambios legítimos frecuentes. La clase `static` es correcta para el registro,
  pero el futuro detector necesitará tratarlos con más tolerancia que `eye_color`.
  Anotado para la spec del detector; no afecta la extracción.
- **Umbral de confianza de escritura**: M2 tenía umbral de escritura de aristas.
  ¿Los atributos de baja confianza se escriben igual (con la confianza como dato) o
  se retienen? Propuesta: escribir siempre y dejar el filtro al consumidor, ya que
  descartar un valor podría ocultar un gazapo. A confirmar en `/plan`.

## Change Log

| Fecha | Cambio | Razón |
|-------|--------|-------|
| 2026-07-19 | Creación de la spec | Brainstorm de M3; frontera fijada en solo atributos. |
