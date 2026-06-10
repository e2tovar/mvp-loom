# Feature Specification: M1 — Extracción y resolución de personajes + eval harness

**Feature Branch**: `002-char-extraction-eval`

**Created**: 2026-06-10

**Status**: Draft

**Input**: User description: "Hagamos la especificación del milestone 1"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Extraer los personajes de un manuscrito ingerido (Priority: P1)

A partir de un manuscrito ya segmentado en capítulos y escenas (capa cruda de M0), el
sistema identifica **todos los personajes** de la obra y los registra como entidades de
conocimiento: cada personaje con su nombre canónico, sus alias conocidos, su rol
aproximado en la historia y las escenas en las que aparece. Cada hecho registrado
conserva la referencia a la escena/pasaje del texto que lo sustenta.

**Why this priority**: Es el núcleo del milestone y del portfolio: la primera capa de
conocimiento extraída sobre la capa cruda. Personajes es la entidad de la que dependen
relaciones (M2), eventos (M3) y todo el análisis posterior. Sin personajes correctos,
nada de lo que sigue tiene base.

**Independent Test**: Se procesa una novela ya ingerida y se obtiene la lista de
personajes con sus alias y escenas de aparición; se coteja contra la lista real de
personajes del libro. Entrega valor por sí sola: el autor ve el reparto completo de su
obra con dónde aparece cada quien.

**Acceptance Scenarios**:

1. **Given** un manuscrito ingerido y segmentado, **When** se ejecuta la extracción de
   personajes, **Then** el sistema produce una lista de entidades-personaje, cada una
   con nombre canónico, alias detectados y las escenas donde aparece.
2. **Given** un personaje mencionado de múltiples formas a lo largo del libro (nombre
   completo, diminutivo, título, apodo), **When** se extrae, **Then** todas las
   menciones se consolidan en **una sola entidad** con sus alias registrados.
3. **Given** un hecho registrado sobre un personaje (p. ej. su primera aparición),
   **When** el usuario lo consulta, **Then** puede rastrear el hecho hasta la escena y
   el fragmento de texto que lo sustenta.
4. **Given** dos personajes distintos con nombres parecidos u homónimos, **When** se
   extrae, **Then** se mantienen como entidades separadas (no se fusionan por similitud
   superficial).
5. **Given** una escena donde un personaje aparece solo mediante pronombres o
   referencias indirectas ("la doctora"), **When** se extrae, **Then** la aparición se
   atribuye a la entidad correcta cuando el contexto lo permite.

---

### User Story 2 - Medir la calidad de la extracción con un dataset de oro (Priority: P2)

El equipo dispone de una anotación de referencia (dataset de oro) con la lista real de
personajes y alias de al menos una novela de prueba. Un arnés de evaluación compara la
salida del sistema contra esa referencia y produce métricas de calidad: cuántos
personajes reales se detectaron, cuántos detectados son reales, y qué tan bien se
agruparon las menciones en entidades. Las métricas se registran de forma comparable
entre ejecuciones y actúan como **puerta de calidad**: si bajan de los umbrales, el
cambio no se integra.

**Why this priority**: Es la mitad del DoD del milestone y la tesis del proyecto
(eval-first): cualquiera extrae personajes que *parecen* correctos; el diferencial es
medir si lo son. Sin la eval, la US1 no se puede declarar terminada.

**Independent Test**: Con un dataset de oro anotado y una salida de extracción
cualquiera, el arnés produce las métricas de detección y resolución, y falla
ruidosamente cuando la calidad cae por debajo del umbral. Puede probarse con salidas
sintéticas (perfecta, vacía, con errores conocidos) verificando que las métricas
responden como se espera.

**Acceptance Scenarios**:

1. **Given** un dataset de oro de personajes para una novela de prueba, **When** se
   ejecuta el arnés sobre la salida de la extracción, **Then** se obtienen métricas de
   detección (precisión, exhaustividad y su media armónica) y de calidad de la
   resolución de entidades.
2. **Given** dos ejecuciones de la extracción (p. ej. antes y después de un cambio),
   **When** se comparan sus resultados de eval, **Then** las métricas son comparables
   directamente y la regresión es visible.
3. **Given** una extracción cuya métrica clave cae por debajo del umbral acordado,
   **When** se ejecuta la verificación de calidad, **Then** el resultado es un fallo
   explícito que bloquea la integración del cambio.

---

### User Story 3 - Revisar fusiones dudosas en lugar de fusionar a ciegas (Priority: P3)

Cuando el sistema no está seguro de si dos menciones corresponden al mismo personaje
(confianza por debajo de un umbral), **no fusiona automáticamente**: deja ambas
entidades separadas y encola el caso como pendiente de revisión humana, con el contexto
necesario para decidir (menciones, escenas, fragmentos).

**Why this priority**: Las fusiones erróneas son el modo de fallo más destructivo de la
resolución de entidades (dos personajes colapsados en uno corrompen todo el grafo
posterior). El umbral de confianza con revisión humana es un principio del proyecto.
Es P3 porque la extracción y la eval pueden operar antes de tener la cola de revisión,
pero el mecanismo debe existir dentro del milestone.

**Independent Test**: Se procesa un texto con un caso ambiguo conocido (dos personajes
con nombres similares) y se verifica que el sistema los mantiene separados y reporta el
caso como dudoso con su contexto, en lugar de fusionarlos silenciosamente.

**Acceptance Scenarios**:

1. **Given** dos menciones cuya correspondencia es dudosa para el sistema, **When**
   termina la extracción, **Then** las entidades quedan separadas y el caso aparece en
   la lista de fusiones pendientes de revisión con su contexto.
2. **Given** la lista de casos dudosos, **When** el usuario la consulta, **Then** cada
   caso incluye las menciones implicadas, las escenas donde ocurren y fragmentos de
   texto suficientes para decidir.

---

### User Story 4 - Re-extracción idempotente y barata (Priority: P4)

Re-ejecutar la extracción sobre un manuscrito que no cambió no repite el trabajo
costoso: los resultados por unidad de texto se reutilizan a partir de su contenido, y
la salida es consistente entre ejecuciones. Si cambia una parte del manuscrito, solo se
recomputa lo afectado.

**Why this priority**: Principio constitucional del proyecto (idempotencia y cache por
hash de contenido) y condición para iterar sobre prompts/modelos sin coste prohibitivo.
Es P4 porque el milestone puede demostrarse sin la cache, pero operar sin ella vuelve
la iteración cara.

**Independent Test**: Se ejecuta la extracción dos veces sobre el mismo manuscrito; la
segunda ejecución termina en una fracción del tiempo/coste y produce el mismo
resultado.

**Acceptance Scenarios**:

1. **Given** un manuscrito ya extraído, **When** se vuelve a ejecutar la extracción sin
   cambios en el texto, **Then** el resultado es equivalente y el trabajo de análisis
   costoso no se repite.
2. **Given** un manuscrito donde cambió una sola escena, **When** se re-ejecuta la
   extracción, **Then** solo se reprocesa el texto afectado y el resto se reutiliza.

---

### Edge Cases

- **Personajes sin nombre propio** ("el posadero", "la mujer del tren"): se registran
  como entidades con su designación descriptiva, sin inventarles nombre.
- **Homónimos reales** (dos personajes llamados igual, p. ej. padre e hijo): deben
  permanecer como entidades separadas; la similitud de nombre no basta para fusionar.
- **Cambios de designación a lo largo del libro** (un personaje que se revela como otro,
  títulos que cambian de portador): el caso es legítimamente difícil; si la confianza es
  baja, debe ir a revisión humana, nunca fusionarse en silencio.
- **Menciones colectivas** ("los soldados", "la multitud"): no deben generar entidades
  de personaje individuales.
- **Personajes solo mencionados** (nombrados en conversación pero que nunca aparecen en
  escena): se registran como entidades, distinguibles de los que sí aparecen.
- **Mascotas/animales con nombre y agencia narrativa**: criterio del dataset de oro; el
  sistema sigue lo que la anotación de referencia defina como "personaje".
- **Obras en español e inglés**: la extracción funciona en ambos idiomas de las novelas
  de prueba, incluyendo diminutivos y tratamientos propios de cada idioma (Don/Doña,
  Mr./Mrs.).
- **Texto que contiene instrucciones** (un manuscrito con texto imperativo o con pinta
  de comando): el contenido del manuscrito se trata como texto no confiable; nunca se
  interpreta como instrucciones para el sistema.
- **Novelas largas (100k+ palabras)**: la extracción completa el libro entero sin
  degradar la consolidación de entidades entre el principio y el final (un alias del
  capítulo 1 sigue resolviéndose bien en el capítulo 60).
- **Falta de personajes** (texto no narrativo o ensayo ingerido por error): el sistema
  produce una lista vacía o mínima sin inventar personajes.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST identificar los personajes presentes en un manuscrito ya
  ingerido y segmentado (salida de M0), produciendo una entidad por personaje real de
  la obra.
- **FR-002**: El sistema MUST consolidar todas las menciones de un mismo personaje
  (nombre completo, diminutivos, apodos, títulos, referencias descriptivas resolubles)
  en una única entidad con su lista de alias.
- **FR-003**: El sistema MUST registrar, por cada personaje, las escenas en las que
  aparece, preservando la distinción entre *aparecer en escena* y *ser mencionado*
  cuando el texto lo permita.
- **FR-004**: Cada entidad y cada aparición registrada MUST conservar la procedencia:
  la escena (y el fragmento de texto) de la que se extrajo, de modo que todo hecho sea
  rastreable hasta el original.
- **FR-005**: El sistema MUST asignar a cada fusión de menciones un nivel de confianza;
  por debajo del umbral configurado, las entidades MUST permanecer separadas y el caso
  MUST encolarse para revisión humana con su contexto (menciones, escenas, fragmentos).
- **FR-006**: El sistema MUST exponer la lista de personajes resultante de forma
  inspeccionable (nombre canónico, alias, rol aproximado, conteo de apariciones,
  primera aparición) para verificación manual.
- **FR-007**: Las salidas del motor de extracción MUST validarse contra un esquema
  tipado; ninguna salida se acepta como texto libre sin estructura.
- **FR-008**: El sistema MUST mantener un dataset de oro versionado con la anotación de
  referencia (personajes, alias, escenas de aparición) de al menos **2 obras de
  prueba**, junto a las obras mismas.
- **FR-009**: El arnés de evaluación MUST calcular, contra el dataset de oro: (a)
  precisión, exhaustividad y media armónica de la **detección** de personajes, y (b)
  una métrica de calidad del **agrupamiento** de menciones en entidades (resolución).
- **FR-010**: Los resultados de la eval MUST registrarse de forma comparable entre
  ejecuciones (misma obra, mismas métricas) para hacer visible cualquier regresión.
- **FR-011**: La eval MUST actuar como puerta de calidad automatizada: una métrica
  clave por debajo del umbral produce un fallo explícito que bloquea la integración
  del cambio.
- **FR-012**: La extracción MUST ser re-ejecutable de forma idempotente: el trabajo por
  unidad de texto se reutiliza cuando el contenido no cambió, y solo se recomputa lo
  afectado por un cambio.
- **FR-013**: El contenido del manuscrito MUST tratarse como texto no confiable: el
  sistema nunca interpreta el texto de la obra como instrucciones propias.
- **FR-014**: El sistema MUST mantener un registro acumulado de entidades durante el
  procesamiento de la obra, de modo que las menciones de unidades posteriores se
  enlacen a entidades existentes en lugar de duplicarlas.

### Key Entities *(include if feature involves data)*

- **Personaje**: entidad de conocimiento que representa a un personaje de la obra.
  Atributos: nombre canónico, alias, rol aproximado (protagonista/antagonista/
  secundario), primera aparición, referencia de procedencia.
- **Mención**: ocurrencia concreta de un personaje en el texto (nombre, alias,
  referencia resoluble), ligada a su escena y posición. Es la evidencia a partir de la
  cual se construyen las entidades.
- **Aparición**: vínculo personaje→escena que indica presencia (o mención) del
  personaje en esa escena, con su procedencia.
- **Caso de fusión dudosa**: par (o grupo) de entidades candidatas a ser el mismo
  personaje con confianza bajo umbral; incluye contexto para decisión humana y estado
  (pendiente/aceptada/rechazada).
- **Dataset de oro**: anotación de referencia por obra: lista real de personajes, alias
  y apariciones, versionada junto al arnés.
- **Resultado de eval**: métricas de una ejecución del arnés sobre una obra (detección
  y resolución), comparable entre ejecuciones.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: La detección de personajes alcanza una media armónica de precisión y
  exhaustividad (**F1 ≥ 0,90**) sobre el dataset de oro de las obras de prueba.
- **SC-002**: La calidad del agrupamiento de menciones en entidades (resolución)
  alcanza **≥ 0,85** en la métrica de clustering acordada sobre el dataset de oro.
- **SC-003**: **Cero fusiones erróneas silenciosas** en las obras de prueba: ningún par
  de personajes distintos del dataset de oro termina fusionado en una sola entidad sin
  haber pasado por la cola de revisión.
- **SC-004**: El **100 %** de los hechos registrados (entidades y apariciones) es
  rastreable hasta una escena y fragmento de origen.
- **SC-005**: Re-ejecutar la extracción sobre un manuscrito sin cambios reutiliza el
  trabajo previo: la segunda ejecución consume menos del **10 %** del coste/tiempo de
  la primera y produce un resultado equivalente.
- **SC-006**: La eval completa (detección + resolución sobre las obras de prueba) se
  ejecuta de principio a fin con un solo comando y termina en **menos de 10 minutos**
  en el entorno de desarrollo, para poder correr en cada cambio.
- **SC-007**: Una métrica clave por debajo del umbral bloquea la integración: el fallo
  es automático y visible, sin intervención manual.
- **SC-008**: El usuario puede revisar la lista de personajes de una novela completa
  (nombres, alias, apariciones) y cotejarla con el libro en **menos de 15 minutos**
  usando solo la salida inspeccionable del sistema.

## Assumptions

- **Solo personajes**: M1 extrae únicamente entidades-personaje y sus apariciones.
  Relaciones entre personajes, atributos físicos (color de ojos, etc.), eventos,
  tramas y temas quedan **fuera de alcance** (M2+). El campo de conocimiento
  (`sabe/ignora`) y heridas abiertas del prior art se difieren a M2 (continuidad).
- **Obras de prueba de dominio público**: el dataset de oro se construye sobre al menos
  2 obras de dominio público ya usadas en M0 (p. ej. *Pride and Prejudice* y las obras
  artesanales de fixtures), anotadas manualmente. El libro del amigo se incorporará
  cuando esté disponible sin cambiar el contrato.
- **Umbrales iniciales**: los umbrales de SC-001 (F1 ≥ 0,90) y SC-002 (≥ 0,85) son
  objetivos iniciales razonables para novelas con reparto moderado; se podrán recalibrar
  con la primera medición real, pero cualquier cambio de umbral queda registrado y
  justificado (nunca se baja en silencio para "poner verde" una regresión).
- **Anotación de referencia como árbitro**: las decisiones de frontera (¿una mascota es
  personaje?, ¿un personaje solo mencionado cuenta?) las fija la anotación del dataset
  de oro, no el motor; el sistema se evalúa contra lo anotado.
- **El motor usa un modelo de lenguaje**: la extracción se apoya en un modelo de
  lenguaje con salidas estructuradas y un registro de entidades acumulado; los detalles
  de proveedor, prompts y orquestación pertenecen al plan de implementación, no a esta
  spec.
- **Coste acotado por diseño**: el procesamiento es por unidad de texto (escena o
  capítulo) con reutilización por hash de contenido; no se reprocesa el libro entero
  por cambios menores.
- **Revisión humana fuera de interfaz gráfica**: en M1 la cola de fusiones dudosas es
  inspeccionable y resoluble por medios simples (la interfaz de producto llega en M7);
  basta con que la decisión humana sea posible y quede registrada.
- **Idioma**: las obras de prueba están en inglés y/o español; no hay traducción ni
  soporte garantizado para otros idiomas en M1.
