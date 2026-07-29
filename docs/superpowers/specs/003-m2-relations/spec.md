# Feature Specification: M2 — Extracción de relaciones entre personajes + eval harness

**Feature Branch**: `feature/m2-relations` (spec `003-m2-relations`)

**Created**: 2026-07-17

**Status**: Draft

**Input**: Brainstorm de M2 en paralelo al cierre de M1 (rama `004-m1-extraction-precision`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Extraer las relaciones entre los personajes de una obra (Priority: P1)

Sobre un manuscrito con personajes ya extraídos y resueltos (capa M1), el sistema
identifica las **relaciones entre pares de personajes** — parentesco, romance, amistad,
antagonismo, vínculo profesional o social — y las registra como aristas de conocimiento:
cada relación con su tipo, un descriptor corto ("tío y tutor"), los roles de cada
personaje cuando se conocen, y si la relación está **enunciada en la prosa** o
**deducida de la interacción**. Cada relación se sustenta en evidencias ancladas a
escenas concretas con su cita textual.

**Why this priority**: Es el núcleo del milestone: la segunda capa de conocimiento del
grafo. Las relaciones alimentan la wiki (M5), el análisis de continuidad y toda
consulta estructural ("¿cómo están conectados X e Y?"). Sin ellas el grafo es un censo,
no una red.

**Independent Test**: Se procesa una novela con capa M1 completa y se obtiene la lista
de relaciones por par con tipo, descriptor y evidencias; se coteja contra las
relaciones reales del libro. Entrega valor por sí sola: el autor ve el mapa relacional
de su reparto.

**Acceptance Scenarios**:

1. **Given** un manuscrito con personajes extraídos (M1), **When** se ejecuta la
   extracción de relaciones, **Then** el sistema produce relaciones agregadas por par
   con tipo, descriptor, procedencia (`extracted`/`inferred`) y confianza.
2. **Given** una relación enunciada en el texto ("su hermana Jane"), **When** se
   extrae, **Then** la relación queda marcada `extracted` con la cita que la sustenta.
3. **Given** una relación nunca enunciada pero deducible de la interacción, **When** se
   extrae, **Then** la relación queda marcada `inferred` y nunca se presenta como hecho
   sin esa marca.
4. **Given** una relación asimétrica (padre→hija, amo→sirviente), **When** se extrae,
   **Then** la arista única del par registra el rol de cada personaje.
5. **Given** una relación que evoluciona a lo largo del libro, **When** se extrae,
   **Then** la relación agregada refleja el tipo dominante/final y las evidencias por
   escena conservan el rastro completo de la evolución.
6. **Given** cualquier relación registrada, **When** el usuario la consulta, **Then**
   puede rastrearla hasta las escenas y citas que la sustentan.

---

### User Story 2 - Medir la calidad de las relaciones con un dataset de oro (Priority: P2)

El equipo dispone de una anotación de referencia de relaciones para las obras de
prueba. Un arnés de evaluación compara la salida del sistema contra esa referencia y
produce métricas comparables entre ejecuciones que actúan como **puerta de calidad**.

**Why this priority**: Tesis eval-first del proyecto: sin métrica, las relaciones
extraídas solo *parecen* correctas. Sin la eval, la US1 no se puede declarar terminada.

**Independent Test**: Con un gold de relaciones y una salida cualquiera, el arnés
produce F1 de detección de pares y accuracy de tipo, desglosadas por procedencia, y
falla ruidosamente bajo umbral. Verificable con salidas sintéticas (perfecta, vacía,
con errores conocidos).

**Acceptance Scenarios**:

1. **Given** un gold de relaciones de una obra, **When** se ejecuta el arnés, **Then**
   se obtienen precisión/exhaustividad/F1 de **detección de pares** y **accuracy de
   tipo** sobre los pares acertados, reportadas por separado para relaciones
   `extracted` e `inferred`.
2. **Given** dos ejecuciones (antes/después de un cambio), **When** se comparan sus
   resultados, **Then** las métricas son directamente comparables y la regresión es
   visible.
3. **Given** una métrica bloqueante bajo umbral en las obras del gate, **When** corre
   la verificación de calidad, **Then** el resultado es un fallo explícito que bloquea
   la integración.

---

### User Story 3 - Inspeccionar el mapa de relaciones (Priority: P3)

El usuario consulta las relaciones de una obra de forma inspeccionable: pares con tipo,
descriptor, roles, procedencia, confianza y evidencias, para cotejarlas con el libro
sin interfaz gráfica.

**Why this priority**: La verificación manual es el complemento del gate automático y
el entregable visible del milestone. Es P3 porque la extracción y la eval funcionan sin
el endpoint, pero el DoD exige salida inspeccionable.

**Acceptance Scenarios**:

1. **Given** una obra con relaciones extraídas, **When** el usuario consulta la lista,
   **Then** ve cada par con tipo, descriptor, roles, procedencia, confianza, conteo de
   evidencias y primera evidencia.

---

### User Story 4 - Re-extracción idempotente y barata (Priority: P4)

Re-ejecutar la extracción de relaciones sobre un manuscrito sin cambios reutiliza el
trabajo por escena desde la cache; si cambia una escena, solo se recomputa lo afectado
y la agregación se rehace de forma determinista.

**Acceptance Scenarios**:

1. **Given** un manuscrito ya procesado, **When** se re-ejecuta sin cambios, **Then**
   el resultado converge al mismo grafo y el trabajo LLM no se repite.
2. **Given** un cambio en una escena, **When** se re-ejecuta, **Then** solo esa escena
   pasa por el LLM y la agregación por par se recalcula con las evidencias vigentes.

---

### Edge Cases

- **Relaciones nunca enunciadas** (deducibles solo de la interacción): se admiten como
  `inferred`, marcadas; nunca compiten con hechos `extracted` en la eval bloqueante.
- **Relaciones a distancia** (dos personajes que jamás co-aparecen pero cuya relación
  se enuncia — "el hijo del ausente"): la evidencia puede citar a un personaje presente
  y otro solo mencionado en la escena; ambos deben pertenecer al cast del manuscrito.
- **Pares con personaje `is_mentioned_only`**: válidos; la relación se ancla a las
  escenas donde se enuncia.
- **Relación que cambia de tipo** (antagonismo → romance): la agregación refleja el
  tipo dominante/final; las evidencias conservan el arco completo.
- **Menciones colectivas** ("los Bennet", "los soldados"): no generan relaciones — solo
  pares de `Character` individuales existentes.
- **Auto-relación** (A con A): inválida por esquema.
- **Personajes fuera del cast entregado**: cualquier evidencia que los referencie se
  rechaza en validación; el LLM no puede introducir entidades nuevas.
- **Escena sin relaciones**: salida vacía válida; no se inventa nada.
- **Texto con instrucciones embebidas**: el manuscrito es texto no confiable; jamás se
  interpreta como instrucciones (mismo principio que M1).
- **Obras en español e inglés**: la extracción funciona en ambos idiomas de las obras
  de prueba.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST extraer, por escena, evidencias de relación únicamente
  entre personajes del **cast entregado** (personajes de la capa M1 presentes o
  mencionados en la escena); toda referencia fuera del cast MUST rechazarse en
  validación.
- **FR-002**: Las salidas del motor MUST validarse contra un esquema tipado; máximo
  **una evidencia por par por escena** (el motor consolida las señales de la escena).
- **FR-003**: Cada evidencia MUST registrar: par de personajes, tipo del catálogo
  cerrado (`family`, `romantic`, `friendship`, `antagonism`, `professional`, `social`,
  `other`), descriptor libre corto, roles opcionales por personaje, procedencia
  (`extracted`/`inferred`), confianza y cita textual de la escena.
- **FR-004**: El sistema MUST consolidar las evidencias de cada par en **una relación
  agregada** mediante reglas deterministas (sin LLM): tipo dominante ponderando
  `extracted` sobre `inferred` con desempate por orden narrativo tardío, descriptor y
  roles de las evidencias del tipo ganador, confianza máxima del tipo ganador,
  procedencia `extracted` si existe al menos una evidencia extracted del tipo ganador.
- **FR-005**: Una relación agregada con confianza bajo el **umbral de escritura**
  (configurable) MUST NOT asertarse como arista; sus evidencias MUST persistir para
  consulta y re-agregación futura. No hay cola de revisión humana para relaciones en M2.
- **FR-006**: Toda relación y toda evidencia MUST conservar procedencia rastreable:
  evidencia → escena + cita; relación agregada → su primera evidencia.
- **FR-007**: Las relaciones son semánticamente **simétricas y únicas por par**
  (almacenadas en dirección canónica determinista); la asimetría se captura en los
  roles, nunca duplicando aristas.
- **FR-008**: La extracción MUST ser idempotente y cacheada: el trabajo por escena se
  reutiliza cuando no cambian contenido de escena, cast ni versión de prompt;
  re-ejecutar sin cambios converge al mismo grafo.
- **FR-009**: M2 MUST NOT modificar ninguna propiedad de las capas M0/M1
  (`Manuscript`/`Chapter`/`Scene`/`NonNarrativeBlock`/`Character`/`Mention`/
  `MergeCandidate`); solo añade nodos y relaciones nuevos.
- **FR-010**: El sistema MUST mantener un gold de relaciones versionado para las obras
  del gate (crafted) y un gold parcial de relaciones principales para al menos una
  novela real (diagnóstico).
- **FR-011**: El arnés MUST calcular: (a) precisión/exhaustividad/F1 de **detección de
  pares no ordenados**, (b) **accuracy de tipo** sobre pares acertados, ambas
  desglosadas por procedencia. El descriptor libre no se evalúa en el gate.
- **FR-012**: La eval MUST actuar como puerta bloqueante sobre las obras crafted
  usando **solo las métricas de relaciones `extracted`**; las `inferred` se reportan
  como diagnóstico no bloqueante.
- **FR-013**: Los resultados de eval MUST registrarse de forma comparable entre
  ejecuciones (obra, métricas, umbrales, `git_sha`, versión de prompt, modelo).
- **FR-014**: El sistema MUST exponer las relaciones de una obra de forma
  inspeccionable vía API (tipo, descriptor, roles, procedencia, confianza, evidencias).
- **FR-015**: El contenido del manuscrito MUST tratarse como texto no confiable.
- **FR-016**: Ejecutar M2 sobre un manuscrito sin capa M1 MUST producir un error
  explícito, nunca una salida vacía silenciosa.
- **FR-017**: El fallo de una escena (validación agotada tras reintentos) MUST NOT
  abortar la obra: se registra, se salta y la agregación opera con lo disponible.

### Key Entities *(include if feature involves data)*

- **Relación (RELATES_TO)**: arista agregada única por par de personajes: tipo,
  descriptor, roles, procedencia, confianza, conteo de evidencias, primera evidencia.
- **Evidencia de relación (RelationEvidence)**: nodo por par y escena — el hecho crudo
  que sustenta la relación: tipo, descriptor, procedencia, confianza, cita, escena.
  Es a la relación lo que `Mention` es a `Character`.
- **Gold de relaciones**: anotación de referencia por obra: pares por `gold_id` de
  personaje (reusa los ids del gold de M1), tipo, procedencia esperada.
- **Resultado de eval**: métricas de una ejecución (detección de pares, accuracy de
  tipo, split por procedencia), comparable entre ejecuciones.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Detección de pares `extracted` con **F1 ≥ 0,90** sobre el gold de las
  obras crafted.
- **SC-002**: Accuracy de tipo **≥ 0,90** sobre los pares acertados de las obras
  crafted.
- **SC-003**: El **100 %** de relaciones y evidencias es rastreable hasta escena y cita
  de origen.
- **SC-004**: Cero aristas que referencien personajes inexistentes o fuera del cast del
  manuscrito (verificado por invariante).
- **SC-005**: Re-ejecutar sin cambios consume menos del **10 %** del coste/tiempo de la
  primera corrida y produce un grafo equivalente.
- **SC-006**: La eval completa corre con un solo comando en **menos de 10 minutos** en
  el entorno de desarrollo.
- **SC-007**: Una métrica bloqueante bajo umbral produce fallo automático y visible que
  bloquea la integración.
- **SC-008**: El usuario puede revisar el mapa de relaciones de una novela y cotejarlo
  con el libro en **menos de 15 minutos** usando solo la salida inspeccionable.

## Assumptions

- **Solo relaciones**: atributos de personaje (status, ubicación) y continuidad
  (`knows/unaware_of`, `open_wounds`) quedan **fuera de alcance** — specs posteriores.
  El bloque "M2" del roadmap se descompone; esta spec cubre su primer tercio.
- **Contrato M1 cerrado**: M2 consume la capa M1 según los contratos de
  `docs/superpowers/specs/002-char-extraction-eval/` en `main` (M1 completo, incluye
  `Character.entity_kind`). El cast entregado al LLM de relaciones filtra
  `entity_kind = "person"`: los animales quedan fuera de las relaciones en M2,
  coherente con la política del gold de M1 (que los excluye del reparto). Nada de esta
  spec depende de detalles internos de la extracción M1.
- **Catálogo de tipos inicial**: los 7 tipos del enum son un punto de partida
  razonable; recalibrable con la primera medición real, con el cambio registrado.
- **Sin cola de revisión humana**: una arista de relación errónea es aditiva y
  reversible (a diferencia de una fusión de entidades); el control de calidad es
  métrico + umbral de escritura + marca de procedencia. El patrón `MergeCandidate` se
  transplanta después si el producto lo exige.
- **Descriptor libre no evaluado**: es dato de producto (wiki M5); evaluarlo requeriría
  LLM-as-judge, diferido.
- **Aislamiento de la base de tests**: los tests de integración de M2 dependen de
  resolver el known-issue crítico #1 (wipes sin scope destruyen la capa cruda). Es
  **prerequisito declarado**, no parte del alcance de esta spec.
- **Coste**: segunda pasada LLM sobre el libro, mismo orden de magnitud que M1,
  amortiguada por cache por hash.
- **Idioma**: obras de prueba en inglés y/o español.

## Decision Log

| # | Decisión | Rationale / trade-off aceptado |
|---|----------|--------------------------------|
| 1 | Scope: solo relaciones; atributos y continuidad fuera | Milestone pequeño, medible y cerrable — mismo patrón que M1. Se acepta descomponer el bloque "M2" del roadmap en varias specs. |
| 2 | Taxonomía híbrida: enum cerrado + descriptor libre | El enum hace la eval medible con matching exacto; el descriptor conserva el matiz para producto. Se acepta que el descriptor quede sin evaluar en el gate. |
| 3 | Relación agregada por par + evidencia por escena; sin estados/arcos | La procedencia es constitucional y queda cubierta; modelar arcos exigiría un gold mucho más laborioso y una eval ambigua. Los datos por escena permiten añadir arcos después **sin re-extraer**. |
| 4 | Procedencia `extracted`/`inferred`, ambas admitidas y marcadas | Patrón adoptado del prior art (graphify). Las inferidas enriquecen el grafo pero nunca se presentan ni evalúan como hechos. |
| 5 | Aristas simétricas únicas por par + roles | Evita duplicar A→B/B→A (idempotencia y eval más simples); la asimetría vive en `role_a`/`role_b`. |
| 6 | Eval: gate en crafted, diagnóstico en novela real | Mismo patrón que M1: gate barato y determinista; señal real sin bloquear por cola larga. |
| 7 | Arquitectura: segunda pasada por escena sobre el cast resuelto (approach A) | No toca el pipeline M1 (compatible con la rama de precisión activa), reusa cache/IDs/MERGE, y las relaciones nacen ancladas a `character_id` resueltos. Se acepta el coste de una segunda pasada LLM. |
| 8 | Sin cola de revisión humana; umbral de escritura + evidencias persistidas | El modo de fallo es blando (arista reversible), al contrario que las fusiones de M1. Se acepta que la zona gris no se asevere en el grafo. |
| 9 | Gate bloqueante solo sobre `extracted` | Castigar el recall de deducciones contra un gold subjetivo reproduce el ruido de umbral visto en M1 (cola larga). `inferred` se mide y reporta, no bloquea. |
| 10 | Cast de la escena como universo cerrado del LLM | Elimina por diseño la alucinación de entidades (riesgo #7 de known-issues); un par fuera del cast es error de validación, no dato. |
| 11 | Cast filtra `entity_kind = "person"` (animales fuera) | Resuelto al mergear M1 completo (sync point previsto): coherente con el gold de M1, que excluye animales del reparto. Incluirlos después es cambiar un filtro, no el modelo. |

## Alternatives Considered

- **Extracción conjunta personajes+relaciones en una pasada (approach B)**: mitad de
  coste LLM, pero acopla contratos y evals de M1/M2 y choca frontalmente con la rama
  `004-m1-extraction-precision` activa. Descartada por romper el desarrollo en paralelo.
- **Pasada global por pares post-hoc (approach C)**: mejor visión de libro completo
  para relaciones inferidas, pero O(pares) llamadas caras, heurística de candidatos
  que pierde relaciones a distancia, y procedencia por escena a reconstruir.
  Descartada como base; **compatible como refuerzo futuro** (consolidador por par
  sobre evidencias acumuladas, sin releer texto).
- **Solo enum / solo etiqueta libre**: descartadas por perder matiz o por exigir
  matching semántico (LLM-as-judge) en la eval desde el día uno.
- **Estados por tramo narrativo / snapshot final**: descartadas por gold laborioso y
  eval ambigua, o por romper la procedencia total.
- **Aristas dirigidas duplicadas**: descartada; duplica superficie de eval y complica
  la idempotencia sin ganar información que los roles no capturen.
- **Gate bloqueante sobre novela real**: descartado; anotación laboriosa, cuota LLM
  por iteración y ruido de cola larga ya observado en M1.
- **Cola de revisión humana para relaciones**: descartada en M2 (ver Decision Log #8).

## Open Questions

- **Umbral de escritura inicial (0,5)**: valor de partida sin medición real; la primera
  corrida diagnóstica sobre novela real debe confirmarlo o recalibrarlo.
- **Suficiencia del enum de 7 tipos**: ¿aparecen en las obras reales relaciones que no
  encajan y saturan `other`? Revisar tras la primera medición.
- **Volumen de evidencias `inferred` en novelas largas**: sin dato aún de cuántas
  produce el modelo por escena; si el ruido es alto, puede requerir instrucción de
  parquedad en el prompt o umbral propio.
- **Evolución temporal (arcos de relación)**: diferida deliberadamente; qué milestone
  la absorbe (¿M3 eventos? ¿spec propia?) queda por decidir en el roadmap.
