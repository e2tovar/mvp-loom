# Feature Specification: M0 — Ingestión y segmentación de manuscritos

**Feature Branch**: `001-m0-ingest-segmentation`

**Created**: 2026-06-04

**Status**: Draft

**Input**: User description: "Vamos a hacer la primera especificación, que sea M0. De momento no tengo el libro de mi amigo, pero utilizaré otros públicos."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Ingerir un manuscrito y segmentarlo en capítulos y escenas (Priority: P1)

Un autor (o el ingeniero que opera el sistema) entrega un manuscrito completo en un
formato de archivo soportado. El sistema lo procesa y produce una **capa cruda
normalizada e inmutable**: el texto del libro descompuesto en capítulos, y cada
capítulo descompuesto en escenas, preservando el orden de lectura y la posición de cada
fragmento dentro del original.

**Why this priority**: Es el cimiento de todo el producto. El grafo, la wiki, la
continuidad y el análisis se construyen sobre esta segmentación. Sin una capa cruda
correcta, todo lo demás carece de base. Es el primer milestone del roadmap (M0) y su
DoD es ver un libro segmentado correctamente en escenas.

**Independent Test**: Se entrega una novela completa en un formato soportado y se
verifica que el resultado contiene los capítulos esperados, en orden, cada uno con sus
escenas, y que el texto narrativo se conserva íntegro sin contenido no-narrativo
(licencias, índices). Entrega valor por sí solo: convierte un archivo opaco en una
estructura navegable y verificable.

**Acceptance Scenarios**:

1. **Given** un manuscrito en un formato soportado con capítulos marcados,
   **When** el usuario lo ingiere, **Then** el sistema produce la lista de capítulos en
   el orden de lectura original, cada uno con su título (si existe) y su número de
   orden.
2. **Given** un capítulo que contiene separadores de escena explícitos,
   **When** se segmenta, **Then** el capítulo se divide en las escenas correspondientes,
   cada una con su orden dentro del capítulo y su posición en el manuscrito.
3. **Given** un capítulo sin separadores de escena explícitos,
   **When** se segmenta, **Then** el capítulo entero constituye una única escena (Nivel
   0: la frontera de capítulo es siempre inicio de escena).
4. **Given** un capítulo con uno o más separadores tipográficos explícitos (línea
   centrada de símbolos `* * *`, `***`, `~`, `· · ·`, un ornamento, o en `.docx` un
   párrafo con estilo/alineación de separador), **When** se segmenta, **Then** cada
   tramo entre separadores se convierte en una escena distinta (Nivel 1).
5. **Given** un archivo con material no-narrativo (portada, índice, licencia de dominio
   público, notas del editor), **When** se ingiere, **Then** ese material se excluye de
   la capa narrativa o se marca claramente como no-narrativo, sin contaminar capítulos y
   escenas.

---

### User Story 2 - Inspeccionar y verificar la segmentación (Priority: P2)

El usuario necesita confirmar que la segmentación es correcta antes de construir nada
encima. Puede revisar la estructura resultante (lista de capítulos, escenas por
capítulo, conteos, fragmento inicial de cada escena) y compararla con el libro original.

**Why this priority**: El DoD de M0 es *ver* el libro segmentado correctamente. Sin una
forma de inspeccionar el resultado, no hay manera de declarar el milestone hecho ni de
detectar errores de segmentación temprano.

**Independent Test**: Tras ingerir un libro, el usuario obtiene un resumen estructural
legible (capítulos, número de escenas por capítulo, conteo de palabras, primeras líneas
de cada escena) y puede cotejarlo contra el original para juzgar la corrección.

**Acceptance Scenarios**:

1. **Given** un manuscrito ya ingerido, **When** el usuario consulta el resultado,
   **Then** ve la jerarquía capítulo→escena con conteos y un fragmento identificador de
   cada unidad.
2. **Given** una segmentación con un error evidente (p. ej. dos capítulos fusionados),
   **When** el usuario la inspecciona, **Then** la información mostrada es suficiente
   para localizar dónde falló la segmentación.

---

### User Story 3 - Re-ingestión determinista e idempotente (Priority: P3)

Volver a ingerir el mismo manuscrito produce exactamente la misma segmentación, sin
duplicar ni alterar la capa cruda existente. Esto sienta la base del re-procesamiento
incremental barato que el proyecto exige.

**Why this priority**: La idempotencia es un principio de la constitución (cache por
hash de contenido) y habilita iterar sin coste ni resultados divergentes. No es
imprescindible para *ver* la primera segmentación, por eso es P3, pero es la base de la
operación a futuro.

**Independent Test**: Ingerir el mismo archivo dos veces produce resultados idénticos
(misma cantidad de capítulos/escenas, mismos límites, mismo orden) y la segunda
ejecución no crea duplicados.

**Acceptance Scenarios**:

1. **Given** un manuscrito ya ingerido, **When** se ingiere de nuevo el mismo archivo,
   **Then** el resultado es idéntico al anterior y no se generan unidades duplicadas.
2. **Given** dos archivos con contenido idéntico pero distinto nombre, **When** se
   ingieren, **Then** la segmentación resultante es la misma.

---

### Edge Cases

- **Sin marcadores de capítulo**: un manuscrito sin encabezados de capítulo
  reconocibles debe tratarse como un único capítulo (o detectar capítulos por
  convención tipográfica), nunca fallar silenciosamente.
- **Convenciones de separador de escena variadas**: `* * *`, `***`, líneas en blanco
  múltiples, símbolos ornamentales. El sistema debe reconocer las convenciones más
  comunes.
- **Material de dominio público de Gutenberg**: cabeceras/pies de licencia, boilerplate
  de "Project Gutenberg", índices y listas de contenidos deben excluirse de lo
  narrativo.
- **Texto con acentos y caracteres no ASCII** (español y otros idiomas): la
  codificación se preserva sin corrupción.
- **Libros largos** (100k+ palabras): la ingestión completa sin agotar recursos ni
  truncar el texto.
- **Archivo corrupto, vacío o de formato no soportado**: se rechaza con un mensaje claro
  en lugar de producir una segmentación parcial o engañosa.
- **Numeración de capítulos no estándar** (prólogo, epílogo, interludios, "Capítulo
  Cero"): se conservan en su orden de lectura.
- **Escena que cruza la frontera de capítulo** (cliffhanger a mitad de escena): bajo el
  Nivel 0 se parte en dos escenas adyacentes. Se acepta como inofensivo en M0: solo
  divide una escena en dos contiguas, sin perder texto ni alterar el orden.
- **`.docx` con separadores por estilo en vez de símbolos**: el corte de escena puede
  venir dado por el estilo o la alineación del párrafo (no por caracteres visibles); el
  sistema debe reconocer esa señal además de los separadores textuales.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST aceptar un manuscrito completo en los formatos `.epub`,
  `.txt` y `.docx`. Los dos primeros cubren las fuentes de dominio público (Project
  Gutenberg) y el tercero, el formato eventual del manuscrito del autor.
- **FR-002**: El sistema MUST descomponer el manuscrito en capítulos, preservando el
  orden de lectura original y, cuando exista, el título de cada capítulo.
- **FR-003**: El sistema MUST descomponer cada capítulo en escenas, asignando a cada
  escena su orden dentro del capítulo y su posición dentro del manuscrito.
- **FR-004**: El sistema MUST definir el límite de escena mediante dos niveles
  deterministas:
  - **Nivel 0** — toda frontera de capítulo es inicio de escena; un capítulo sin
    separadores internos constituye una única escena.
  - **Nivel 1** — dentro de un capítulo, cada separador tipográfico explícito (línea
    centrada compuesta solo de símbolos como `* * *`, `***`, `~`, `· · ·`, un ornamento;
    o en `.docx` un párrafo vacío/ornamental con estilo o alineación de separador, o
    doble espaciado) inicia una nueva escena.
  La detección semántica de cortes no marcados (Nivel 2, asistida por LLM) queda
  **fuera de alcance de M0** y se aborda en un milestone propio posterior.
- **FR-004a**: El sistema MUST distinguir un separador de escena real de un simple
  espacio entre párrafos: la señal válida es una línea compuesta únicamente de símbolos
  separadores (o, en `.docx`, un párrafo con estilo/alineación de separador), no
  cualquier salto de párrafo.
- **FR-005**: El sistema MUST conservar metadatos de posición que permitan rastrear cada
  capítulo y escena de vuelta a su ubicación en el manuscrito original.
- **FR-006**: El sistema MUST tratar la capa cruda resultante como **inmutable**: una
  vez generada para un manuscrito dado, no se altera salvo por una re-ingestión
  explícita.
- **FR-007**: El sistema MUST excluir de la capa narrativa el contenido no-narrativo
  reconocible (licencias, boilerplate de Project Gutenberg, índices, portadas) o
  marcarlo inequívocamente como no-narrativo.
- **FR-008**: El sistema MUST preservar el texto narrativo íntegro y la codificación de
  caracteres (incluidos acentos y caracteres no ASCII) sin pérdida ni corrupción.
- **FR-009**: El sistema MUST producir resultados idénticos y deterministas al ingerir
  dos veces el mismo contenido, sin crear duplicados.
- **FR-010**: El sistema MUST exponer un resumen estructural inspeccionable del
  resultado (jerarquía capítulo→escena, conteos de palabras/escenas, fragmento
  identificador por unidad) suficiente para verificar la corrección manualmente.
- **FR-011**: El sistema MUST rechazar archivos vacíos, corruptos o de formato no
  soportado con un mensaje de error claro, sin producir una segmentación parcial.
- **FR-012**: El sistema MUST conservar unidades estructurales fuera del esquema típico
  de capítulos (prólogo, epílogo, interludios) en su orden de lectura.

### Key Entities *(include if feature involves data)*

- **Manuscrito**: el documento de origen entregado por el usuario. Representa la fuente
  inmutable. Atributos relevantes: identificador derivado de su contenido, formato de
  origen, título de la obra (si se puede determinar), conteo total de palabras.
- **Capítulo**: unidad estructural de primer nivel. Atributos: número/orden de lectura,
  título (opcional), conteo de palabras, referencia al manuscrito de origen.
- **Escena**: unidad estructural dentro de un capítulo y unidad mínima de la capa cruda.
  Atributos: orden dentro del capítulo, orden/posición narrativa global en el
  manuscrito, límites de texto, fragmento identificador.
- **Bloque no-narrativo**: contenido detectado como no perteneciente a la narración
  (licencia, índice, portada), conservado o marcado pero excluido de capítulos/escenas.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Al ingerir una novela de dominio público de referencia, **el 100 % de los
  capítulos** del original aparecen en el resultado, en el orden de lectura correcto.
- **SC-002**: La detección de límites de capítulo alcanza una exactitud **≥ 95 %**
  (capítulos correctamente delimitados frente al total) sobre un conjunto de al menos 2
  novelas de dominio público de prueba.
- **SC-003**: La detección de separadores de escena explícitos (Nivel 1) alcanza una
  exactitud **≥ 90 %** frente a la anotación de referencia de separadores, sin generar
  falsos cortes a partir de simples saltos de párrafo, sobre el mismo conjunto de
  prueba. (Las escenas no marcadas quedan absorbidas en su capítulo por el Nivel 0 y no
  cuentan como error en M0.)
- **SC-004**: **Ningún** carácter del texto narrativo original se pierde ni se corrompe:
  el texto narrativo reconstruido a partir de las escenas coincide con el original tras
  descontar el material no-narrativo.
- **SC-005**: Re-ingerir el mismo manuscrito produce un resultado **idéntico** en cuanto
  a número y límites de capítulos y escenas (determinismo verificable).
- **SC-006**: Una novela de hasta **150 000 palabras** se ingiere y segmenta por
  completo en **menos de 5 minutos** en el entorno de desarrollo.
- **SC-007**: El material no-narrativo (boilerplate de licencia/índice) **no aparece**
  dentro de ningún capítulo o escena narrativa en las novelas de prueba.
- **SC-008**: El usuario puede confirmar visualmente la corrección de la segmentación de
  un libro completo en **menos de 10 minutos** usando solo el resumen estructural.

## Assumptions

- **Sin libro del amigo todavía**: la validación de M0 se hará contra **novelas de
  dominio público** (p. ej. Project Gutenberg). El manuscrito original del amigo se
  incorporará más adelante sin cambiar el contrato de esta funcionalidad.
- **Alcance estrictamente estructural**: M0 produce únicamente la segmentación
  capítulo→escena de la capa cruda. La extracción de entidades, relaciones, atributos,
  resúmenes o puntuaciones (tensión, sentimiento) queda **fuera de alcance** y pertenece
  a milestones posteriores (M1+).
- **Segmentación determinista en M0 (Niveles 0 y 1)**: M0 se lanza solo con detección
  determinista de escenas (frontera de capítulo + separadores tipográficos explícitos).
  La **detección semántica con LLM (Nivel 2)** —para ficción literaria que salta de
  tiempo/lugar sin marcador— se difiere a su **propio milestone**; allí se procesará una
  llamada por capítulo (nunca por párrafo) y solo sobre capítulos sin marcadores,
  devolviendo índices de inicio de escena, razón y confianza. Mantener M0 determinista
  preserva el criterio de re-ingestión idéntica (SC-005).
- **Formatos de entrada**: M0 soporta `.epub`, `.txt` y `.docx`. Las pruebas inmediatas
  usan `.epub`/`.txt` de dominio público; `.docx` se incluye desde ya para no rehacer la
  ingestión cuando llegue el manuscrito del autor.
- **Idioma**: las obras de prueba pueden estar en español o inglés; el sistema no
  traduce ni interpreta semánticamente el contenido en M0.
- **Verificación manual en M0**: el DoD se valida por inspección humana del resumen
  estructural. El eval harness formal con dataset de oro y métricas automatizadas
  comienza en M1 (personajes), conforme al roadmap; las métricas de exactitud de este
  documento se miden contra una anotación manual de las novelas de prueba.
- **Una obra por ingestión**: cada operación procesa un único manuscrito completo; la
  ingestión por lotes queda fuera de alcance.
- **Entorno de desarrollo local**: los objetivos de rendimiento se refieren al entorno
  de desarrollo del proyecto, no a una infraestructura de producción dimensionada.
