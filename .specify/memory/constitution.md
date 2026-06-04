<!--
SYNC IMPACT REPORT
==================
Version change: TEMPLATE (unversioned) → 1.0.0
Rationale: Initial ratification. The file was an unfilled template; first concrete
adoption is a MINOR-from-zero baseline → 1.0.0.

Modified principles: N/A (initial adoption)
Added principles:
  - I. Eval-first (NO NEGOCIABLE)
  - II. El grafo es la columna vertebral
  - III. Contratos tipados (Pydantic) en toda salida del LLM
  - IV. Una sola puerta al LLM
  - V. Citas obligatorias (anclaje verificable en Passage)
  - VI. Idempotencia y cache por hash de contenido
  - VII. Profundidad antes que amplitud (depth-first, anti feature-creep)
Added sections:
  - Restricciones técnicas y de stack
  - Flujo de desarrollo y puertas de calidad
  - Governance

Templates requiring updates:
  - ✅ .specify/templates/plan-template.md — "Constitution Check" es genérico y lee
       este archivo dinámicamente; no requiere cambios.
  - ✅ .specify/templates/spec-template.md — sin conflicto con los principios.
  - ✅ .specify/templates/tasks-template.md — sin conflicto con los principios.
  - ⚠ .specify/templates/commands/ — directorio inexistente; nada que propagar.

Follow-up TODOs:
  - TODO(RATIFICATION_DATE): fecha de adopción original desconocida; se usa la fecha
    de esta primera ratificación (2026-06-04). Actualizar si existe una fecha previa.
-->

# Loom Constitution

## Core Principles

### I. Eval-first (NO NEGOCIABLE)

Ningún módulo de IA se considera terminado sin su evaluación en verde. Cada capacidad
de extracción o análisis MUST tener un golden dataset anotado por humanos y métricas
objetivas antes de declararse hecha: precision/recall/F1 para entidades y relaciones,
B-cubed (o F1 por pares) para resolución de entidades, tau de Kendall para orden
cronológico, y precisión de alertas para continuidad. La regresión de estas métricas
se ejecuta en cada cambio de prompt o modelo y MUST actuar como gate de CI: si una
métrica clave baja, no se mergea.

**Rationale:** Cualquiera enchufa un LLM y obtiene un mapa que *parece* correcto. Lo
que distingue este proyecto es medir si la extracción es correcta. Si la extracción
falla, todo lo construido encima es ruido.

### II. El grafo es la columna vertebral

El grafo de conocimiento narrativo (Neo4j) es la única fuente de verdad. Continuidad,
arcos, informe, wiki y recuperación MUST derivarse del grafo, no de almacenes
paralelos. La Story Wiki se deriva del grafo; no es un origen de datos independiente.
Neo4j hace de grafo Y de índice vectorial (HNSW nativo): un `Passage` es un nodo del
grafo con su `embedding` como propiedad. No se introducen bases vectoriales separadas
sin justificación explícita registrada en `docs/`.

**Rationale:** Un único sustrato consultable convierte el producto en una plataforma
coherente en vez de un conjunto de herramientas sueltas que se desincronizan.

### III. Contratos tipados (Pydantic) en toda salida del LLM

Ninguna salida del LLM se parsea como texto libre. Toda extracción MUST devolver
objetos Pydantic validados vía tool-use / JSON schema. El esquema tipado ES el
contrato entre el modelo y el resto del sistema.

**Rationale:** El parsing de texto libre es frágil y silenciosamente incorrecto; la
validación tipada falla rápido y hace auditable cada salida del modelo.

### IV. Una sola puerta al LLM

Todas las llamadas al LLM MUST pasar por la interfaz de `backend/llm/`. No se permiten
SDKs de proveedor dispersos por el código. La interfaz es agnóstica de proveedor; el
código de aplicación nunca conoce qué modelo concreto responde.

**Rationale:** Un único punto de acceso habilita caching, trazas, conteo de coste y
cambio de proveedor sin tocar la lógica de negocio.

### V. Citas obligatorias (anclaje verificable en Passage)

Toda afirmación analítica (informe, continuidad, respuesta de Q&A) MUST referenciar al
menos un `Passage` por id. Sin cita, no se emite ni se muestra. Las consultas locales
se anclan a pasajes recuperados; las globales agregan `CommunitySummary` que a su vez
trazan a pasajes.

**Rationale:** El anclaje obligatorio a la fuente es lo que mata la alucinación y hace
que el autor pueda confiar en cada afirmación del sistema.

### VI. Idempotencia y cache por hash de contenido

La extracción MUST cachearse por hash de contenido del chunk y ser idempotente al
escribir en el grafo. Re-ejecutar el pipeline tras un cambio menor MUST recomputar solo
lo cambiado y ser determinista en la medida de lo posible. La wiki se mantiene
diff-aware: editar un capítulo regenera únicamente las páginas afectadas.

**Rationale:** Los manuscritos son largos y caros de procesar; sin idempotencia y cache
el coste y la latencia hacen inviable la iteración.

### VII. Profundidad antes que amplitud (depth-first, anti feature-creep)

El roadmap se ejecuta depth-first y eval-gated: no se avanza a un milestone sin cumplir
su Definition of Done. El valor está en hacer *una cosa difícil con rigor* —la
extracción precisa de un grafo narrativo y su evaluación medible— no nueve cosas a
medias. Features fuera del núcleo (portada, traducción, imprenta, distribución) MUST
resistirse hasta que el núcleo esté sólido y medido.

**Rationale:** El feature creep diluye el esfuerzo justo donde reside el valor
diferencial y el rigor de ingeniería del proyecto.

## Restricciones técnicas y de stack

- **Backend:** Python 3.12+, FastAPI + Pydantic v2.
- **Grafo + vectores:** Neo4j 5.x (índice vectorial nativo + APOC + GDS/Leiden). No se
  añaden Qdrant/pgvector ni equivalentes sin ADR que lo justifique.
- **Orquestación:** workflow con estado, reanudable y con puertas humanas (Prefect o
  Temporal). No usar una cadena de funciones suelta para el pipeline largo.
- **LLM y embeddings:** interfaz agnóstica de proveedor; salidas estructuradas; modelos
  clase Claude/GPT. Embeddings guardados como propiedad de `Passage`.
- **Cypher revisable:** las consultas al grafo viven nombradas en `backend/graph/`,
  nunca incrustadas ad hoc en otras capas.
- **Frontend:** React + TypeScript + Vite.
- **Observabilidad:** trazas por llamada LLM, conteo de tokens y coste por etapa.
- **Privacidad del autor:** "no entrenamos con tu obra"; manejo de datos explícito y
  opción de borrado. El manuscrito normalizado es una capa cruda inmutable.

## Flujo de desarrollo y puertas de calidad

- **Milestones eval-gated (M0–M8):** cada milestone tiene un DoD objetivo; el verde de
  su eval es condición de cierre (ver Principio I y VII).
- **Human-in-the-loop:** las fusiones de entidades por debajo del umbral de confianza
  MUST marcarse para revisión humana; no se fusiona a ciegas.
- **Gate de CI:** la suite de regresión de evals bloquea el merge ante caída de
  métricas clave; los tests de lógica (`pytest`) corren aparte del eval harness.
- **Docs vivas (patrón LLM Wiki):** cada cambio relevante actualiza la página
  correspondiente en `docs/` y/o la Story Wiki; las decisiones de diseño se registran
  como ADRs en `docs/`.
- **Revisión:** toda PR verifica el cumplimiento de esta constitución; cualquier
  complejidad añadida MUST justificarse explícitamente.

## Governance

Esta constitución supersede cualquier otra práctica del proyecto. Las enmiendas
requieren: (1) documentación del cambio y su motivación, (2) actualización de versión
según la política semántica, y (3) propagación a las plantillas y guías dependientes.

Política de versionado (semver del documento):
- **MAJOR:** eliminación o redefinición incompatible de principios o gobernanza.
- **MINOR:** adición de un principio/sección o expansión material de la guía.
- **PATCH:** aclaraciones, redacción y refinamientos no semánticos.

Cumplimiento: todas las PRs y revisiones MUST verificar conformidad con los principios.
La guía operativa de runtime para los agentes de código vive en `README.md` (contrato
de trabajo) y en `CLAUDE.md`; ante conflicto, esta constitución prevalece.

**Version**: 1.0.0 | **Ratified**: 2026-06-04 | **Last Amended**: 2026-06-04
