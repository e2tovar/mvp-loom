# Research — M0: Ingestión y segmentación

**Feature**: `001-m0-ingest-segmentation` · **Fecha**: 2026-06-04

La spec quedó sin marcadores `NEEDS CLARIFICATION` (formatos y regla de escena
resueltos por el usuario). Esta fase consolida las decisiones técnicas que el plan
necesita. Formato por decisión: **Decisión · Razón · Alternativas descartadas**.

---

## D1 · Almacén de la capa cruda: Neo4j desde M0

**Decisión**: Persistir la capa cruda como nodos del grafo (`Manuscript`, `Chapter`,
`Scene`, `NonNarrativeBlock`) en Neo4j 5.x, levantado con `docker-compose`.

**Razón**: El Principio II de la constitución hace del grafo la única fuente de verdad;
el README incluye explícitamente "docker-compose con Neo4j" en M0. Materializar la capa
cruda en el grafo desde el inicio evita una migración posterior desde un store
intermedio y permite que M1 (personajes) lea directamente de `Scene`/`Chapter`.

**Alternativas descartadas**:
- *JSON/Parquet en disco*: más simple, pero crea un segundo origen de verdad que habría
  que migrar al grafo en M1; contradice el Principio II.
- *SQLite*: igual problema de doble store; no aporta sobre Neo4j que ya es requisito.

---

## D2 · Parsing EPUB

**Decisión**: `ebooklib` para leer el contenedor EPUB y recorrer el **spine** en orden
de lectura; `BeautifulSoup` (`lxml`) para extraer texto de cada documento XHTML. Los
ítems del spine y/o el `nav`/`toc.ncx` dan los límites de capítulo.

**Razón**: El EPUB ya codifica el orden de lectura (spine) y a menudo un capítulo por
documento XHTML, lo que hace la detección de capítulos casi infalible. `ebooklib` es la
librería estándar y madura para esto.

**Alternativas descartadas**:
- *`unstructured`*: potente pero pesado y menos determinista; introduce dependencia
  grande para poco beneficio en M0. Se reconsiderará si aparecen EPUB problemáticos.
- *Descomprimir el zip a mano*: reinventa `ebooklib` sin ganancia.

---

## D3 · Parsing TXT (Project Gutenberg)

**Decisión**: Lector de texto plano con detección de codificación (UTF-8 preferente,
fallback declarado). Stripping del boilerplate Gutenberg mediante los marcadores
`*** START OF THE PROJECT GUTENBERG EBOOK ... ***` y `*** END OF ... ***`. Detección de
capítulos por regex de encabezado: `CHAPTER`, `Capítulo`, numerales romanos/arábigos,
líneas en mayúsculas aisladas.

**Razón**: Los `.txt` de Gutenberg tienen un formato de boilerplate estable y conocido;
los marcadores delimitan la zona narrativa con fiabilidad. La detección de capítulos por
regex es determinista y medible.

**Alternativas descartadas**:
- *Asumir todo el archivo como narrativa*: contaminaría la capa cruda con licencia e
  índice (viola FR-007/SC-007).
- *Heurística por densidad de texto*: frágil y no determinista frente a los marcadores
  explícitos.

---

## D4 · Parsing DOCX

**Decisión**: `python-docx`. Capítulos por **estilo de encabezado** (`Heading 1/2`).
Separadores de escena por: (a) párrafos cuyo texto son solo símbolos separadores, o
(b) párrafos vacíos/ornamentales con estilo de separador o alineación centrada
(señal de estilo, no solo de caracteres) — conforme a FR-004a y al edge case de DOCX.

**Razón**: En DOCX la estructura vive en estilos, no solo en caracteres visibles;
`python-docx` expone `paragraph.style` y `paragraph.alignment`, justo las señales que el
usuario describió en el Nivel 1.

**Alternativas descartadas**:
- *Convertir DOCX→texto plano primero*: pierde la información de estilo que distingue un
  separador real de un salto de párrafo (rompe FR-004a).

---

## D5 · Algoritmo de segmentación de escenas (Nivel 0 + Nivel 1)

**Decisión**: Tras obtener los capítulos, dentro de cada uno:
1. **Nivel 0** — el inicio del capítulo abre la primera escena.
2. **Nivel 1** — escanear los bloques/párrafos del capítulo; un bloque que sea un
   **separador** (línea compuesta únicamente de símbolos separadores tras normalizar
   espacios, o señal de estilo en DOCX) cierra la escena actual y abre la siguiente. El
   bloque separador no forma parte del texto de ninguna escena.
3. Si no hay separadores, el capítulo es una única escena.

Conjunto de símbolos separadores reconocidos (regex, configurable): `*`, `·`, `~`, `—`,
`#`, `§`, espacios; una línea válida contiene solo esos caracteres y ≥1 símbolo no
espacio. Determinista y sin estado entre ejecuciones.

**Razón**: Cumple exactamente la regla acordada con el usuario; 100 % determinista
(preserva SC-005); separa la señal de separador del simple salto de párrafo (FR-004a).

**Alternativas descartadas**:
- *Contar líneas en blanco como separador siempre*: produce falsos cortes (rompe
  FR-004a y SC-003).
- *Nivel 2 semántico con LLM en M0*: descartado por alcance; rompería el determinismo.

---

## D6 · Idempotencia por hash de contenido

**Decisión**: `manuscript_id = sha256(contenido_narrativo_normalizado)`. La
normalización (orden de bloques, normalización de saltos de línea, exclusión del
boilerplate) ocurre **antes** del hash, de modo que dos archivos con el mismo contenido
narrativo —aunque difieran en nombre o metadatos del contenedor— produzcan el mismo id
(US3, escenario 2). Las escrituras al grafo usan `MERGE` por id.

**Razón**: Principio VI (cache/idempotencia por hash). Hashear el contenido normalizado
—no los bytes crudos— hace la identidad robusta frente a diferencias de empaquetado.

**Alternativas descartadas**:
- *Hash de bytes crudos del archivo*: dos exports del mismo libro darían ids distintos
  (rompe US3 escenario 2).
- *UUID aleatorio por ingestión*: no idempotente; duplicaría en re-ingestión.

---

## D7 · Detección de contenido no-narrativo

**Decisión**: Reglas deterministas por formato: marcadores Gutenberg en `.txt`;
documentos de navegación/portada y secciones de TOC en `.epub`; páginas de
título/copyright/índice por heurística de posición y palabras clave
(`Copyright`, `Índice`, `Table of Contents`, `Project Gutenberg`). El material detectado
se conserva como `NonNarrativeBlock` (marcado, no borrado) pero excluido de
capítulos/escenas.

**Razón**: FR-007/SC-007 exigen que no contamine lo narrativo; conservarlo marcado (en
lugar de descartarlo) preserva trazabilidad y permite revisar falsos positivos.

**Alternativas descartadas**:
- *Borrado silencioso*: pierde trazabilidad y dificulta depurar falsos positivos.
- *Clasificación con LLM*: innecesaria y no determinista para M0.

---

## D8 · Forma de la API e ingestión síncrona

**Decisión**: Dos endpoints FastAPI: `POST /manuscripts` (sube el archivo, ejecuta el
pipeline de forma **síncrona** y devuelve el `manuscript_id` y un resumen) y
`GET /manuscripts/{id}/structure` (resumen estructural inspeccionable). Sin
orquestación con estado en M0.

**Razón**: Sin LLM, el pipeline de una novela de 150k palabras es cuestión de segundos;
la simplicidad síncrona basta y cumple SC-006 con holgura. Prefect/Temporal (workflow
con estado, puertas humanas) pertenece a M8 según el roadmap.

**Alternativas descartadas**:
- *Workflow Prefect desde M0*: complejidad prematura; viola el espíritu depth-first
  (Principio VII) sin necesidad real todavía.
- *Cola de tareas asíncrona*: innecesaria para cargas de segundos en entorno local.

---

## D9 · Proto-eval de segmentación como gate de CI

**Decisión**: Crear `eval/fixtures/` con ≥2 novelas de dominio público y un archivo de
**anotación de referencia** por obra (número y títulos de capítulos; posiciones de los
separadores de escena explícitos). `eval/segmentation/accuracy.py` calcula la exactitud
de capítulos (SC-002) y de separadores de escena (SC-003). Un test en `tests/eval/`
falla si alguna métrica cae bajo umbral; se ejecuta en CI.

**Razón**: Honra el Principio I (medible + gate de CI) sin construir todavía el harness
completo de M1 (precision/recall/F1, B-cubed), que aplica a la extracción semántica
inexistente en M0.

**Alternativas descartadas**:
- *Solo verificación manual*: no satisface el Principio I (sin gate automatizado).
- *Harness completo de M1 ya en M0*: amplitud prematura; M0 no tiene entidades que
  medir con esas métricas.

---

## D10 · Anotación de referencia y selección de obras

**Decisión**: Elegir obras con estructura de capítulos clara y, al menos una, con
separadores de escena explícitos. Anotación en un formato simple versionado junto a la
fixture (p. ej. lista de offsets/índices de capítulo y de separador). Registrar
procedencia y licencia de dominio público en `eval/fixtures/README.md`.

**Razón**: SC-002/003 requieren una referencia contra la que medir; la procedencia
documentada respeta el principio de privacidad/transparencia y facilita reproducir.

**Alternativas descartadas**:
- *Anotar el libro del amigo*: aún no disponible (supuesto de la spec); además no es de
  dominio público para versionar en el repo.

---

## Dependencias y versiones (resumen)

| Componente | Elección | Notas |
|------------|----------|-------|
| Runtime | Python 3.12+ | Ya fijado en `pyproject.toml`/`.python-version` |
| API | FastAPI + Pydantic v2 | Pydantic = contrato (Principio III) |
| Grafo | Neo4j 5.x (driver `neo4j`) | docker-compose; Cypher en `backend/graph/` |
| EPUB | `ebooklib` + `beautifulsoup4` + `lxml` | spine + XHTML |
| DOCX | `python-docx` | estilos + alineación |
| TXT | stdlib | + stripping Gutenberg |
| Tests | `pytest` | unidad + integración + proto-eval |

Sin dependencias de LLM ni de proveedor en M0 (Principio IV, vacuo).
