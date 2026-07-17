# Deuda técnica conocida

Registro de problemas conocidos que no bloquean el avance actual pero deben
resolverse antes de dar una métrica por válida. Cada entrada cita su ubicación.

---

## M2 · Follow-ups tras la implementación de relaciones (rama `feature/m2-relations`, 2026-07-17)

**Estado:** ⏳ abiertos · registrados 2026-07-17

M2 (relaciones entre personajes) quedó completo y verificado: gate en verde sobre
`crafted-relations.txt` (pares extracted F1 = 1.0, type accuracy = 1.0 con
`openai/kimi-k2.5`), suite unit + integración (36) en verde, re-ejecución idempotente
(2ª corrida 4/4 cache hits). Follow-ups no bloqueantes detectados en el review final
de rama, en orden de prioridad:

1. **[Constitución] `_load_scenes` con Cypher fuera de `backend/graph/`.**
   `backend/extraction/relations/pipeline.py` incrusta la query de carga de escenas
   (copia literal de `backend/extraction/pipeline.py` de M1). Extraer a un
   `get_scenes_in_order(sess, mid)` en `backend/graph/` y llamarlo desde ambos
   pipelines: corrige la desviación y elimina la query duplicada.

2. **[API] `has_relations` → 409 ambiguo.** Un manuscrito donde M2 corrió pero todas
   las relaciones quedaron bajo `WRITE_THRESHOLD` (cero aristas) devuelve
   `409 not_extracted`, indistinguible de "M2 nunca corrió"
   (`backend/api/routes_relations.py`, `backend/graph/relations.py::has_relations`).
   Considerar un marcador de "procesado" separado de "tiene aristas".

3. **[Limpieza] `SceneRelations.notes` es un campo de salida muerto.** Declarado en
   `backend/extraction/relations/schemas.py` pero nunca leído en pipeline, agregación,
   cache ni eval. Eliminar o cablear a un log de diagnóstico.

4. **[M3] Evidencia de relación obsoleta ante re-resolución de M1.**
   `get_evidences_by_pair` lee toda la `RelationEvidence` histórica del manuscrito. Si
   una futura re-resolución de M1 cambia/fusiona `character_id`s, la evidencia con ids
   muertos sobrevive (nunca se purga) y sigue contando en `evidence_count`/votos de
   tipo. `replace_relates_to` protege contra aristas fantasma, no contra evidencia
   fantasma. Fuera de alcance de M2; abordar cuando M3 toque re-resolución.

5. **[Tests/docs] Cobertura y precisión menores.** (a) `test_relation_aggregation`:
   falta caso de conflicto asimétrico de roles (un solo slot discrepa → ambos None) y
   caso de frontera `WRITE_THRESHOLD` (conf == 0.5 no es None) — comportamiento
   verificado correcto, solo falta el test. (b)
   `test_inferred_pred_does_not_hit_extracted_precision` afirma recall, no precision
   (el nombre engaña; comportamiento correcto). (c) `quickstart.md` usa
   `crafted-three-chapters.txt` (diagnóstico, sin relaciones extracted) como ejemplo
   del runner en vez de la obra del gate `crafted-relations.txt`.

6. **[Umbrales] Umbral de escritura y de gate sin recalibración real.**
   `WRITE_THRESHOLD = 0.5` y los umbrales del gate (F1 ≥ 0.90, type ≥ 0.90) son
   objetivos iniciales; la única medición real es la obra sintética del gate (que da
   1.0/1.0 por diseño). Falta una corrida diagnóstica sobre novela real (P&P/HP1) para
   confirmar/recalibrar, con la anotación de gold de relaciones ampliada.

---

## M1 · La cascada de resolución sobre-fusiona personajes por apellido

**Estado:** ✅ resuelto 2026-07-13 · detectado 2026-07-13

`EntityRegistry._normalize` eliminaba los honoríficos de forma incondicional, así que
dos personajes que difieren **solo** por el honorífico sobre un apellido compartido
colapsaban a la misma clave de índice: `Mr. Bennet`/`Mrs. Bennet` → `"bennet"`;
`Lady Lucas`/`Miss Lucas` (alias de `Charlotte Lucas`) → `"lucas"`. Esa colisión
disparaba la ruta **determinista de nivel 1** (`registry.find` en `resolve_candidate`,
y la rama de colisión en `registry.add`): fusión con confianza 1.0, sin LLM ni cola.
Como el `merged_into` canónico alimenta el `character_id`, la segunda entidad nunca
obtenía nodo propio → absorción silenciosa.

El honorífico es descartable solo para emparejar una forma sin título contra su forma
con título (`Darcy` ↔ `Mr. Darcy`, misma persona). **Dos honoríficos distintos** sobre
la misma base son personas distintas.

**Resolución:** índice honorífico-aware en `backend/extraction/registry.py`. El índice
pasa de `dict[str, str]` a `dict[base, dict[honorífico, canonical]]`. La resolución:
honorífico exacto → esa entidad; forma con título contra la única forma sin título de
esa base → misma entidad; base sin título con varias formas con título distintas →
ambiguo, sin auto-merge. Cubierto por tests deterministas en
`tests/unit/test_resolution.py` (`test_different_honorifics_same_surname_not_merged`,
`test_conflicting_honorific_alias_not_merged`,
`test_registry_keeps_distinct_honorifics_separate`,
`test_bare_name_still_matches_single_honorific_form`). El eval gate sobre las obras
crafted sigue verde (F1 ≥ 0.90, B³ ≥ 0.85, `silent_bad_merges = 0`).

**Pendiente:** re-correr `pride-and-prejudice.txt` completo para reconfirmar sobre
datos reales (coste de cuota LLM). El nivel 2 (auto-merge del LLM) no se tocó: si un
modelo juzgara `Mr. X` y `Mrs. X` como el mismo personaje con confianza ≥ 0.9 seguiría
fusionando, pero ya no de forma silenciosa por normalización.

---

## M1 · La resolución B³ no está realmente cableada (stub)

**Estado:** ✅ resuelto 2026-07-11 · detectado 2026-06-15

La detección F1 mide algo real al ejecutar el harness. La **resolución B³ no**: hoy
devolvería `0.0` aunque se lance el flujo completo, por dos motivos independientes de
ejecutar la extracción.

1. **El runner descarta los clusters reales de menciones.**
   `eval/characters/runner.py:83` carga `pred_clusters` (clusters de `mention_id` reales,
   calculados en `_load_system_output`, líneas 56-58) pero **nunca los pasa a `bcubed_f1`**.
   En su lugar, las líneas 98-102 construyen clusters de un solo elemento con espacios de
   IDs disjuntos (`["elena"]` del gold vs `["pred:<id>"]` del sistema). En `bcubed_f1`
   toda mención cae en la rama "solo en uno" → precisión = recall = 0 → **B³ F1 = 0.0
   siempre**. Los comentarios `runner.py:92-94` lo admiten como simplificación.

2. **El gold no tiene anotaciones a nivel de mención.**
   `eval/fixtures/*.characters.gold.json` solo registra `appearances` a nivel de escena.
   Aunque se conectara `pred_clusters`, no hay referencia gold de menciones contra la que
   medir el agrupamiento.

Relacionado: `count_silent_bad_merges` se invoca con `[]` en `runner.py:104` — no carga
los `MergeCandidate` reales del grafo, así que esa métrica tampoco refleja el estado real.

**Resolución (2026-07-11):** `eval/characters/alignment.py` alinea gold↔pred en el
espacio de claves `"c{cap}/s{escena}::{surface}"`; los golds de las obras del gate
llevan `mentions` anotadas; el runner pasa los clusters reales a `bcubed_f1` y los
pares reales de `MergeCandidate` a `count_silent_bad_merges`. Los golds sin anotación
de menciones (pride-and-prejudice) reportan `resolution_b3: null` — no medido, nunca
un valor inventado. El gate exige B³ no-null para sus obras.

---

## M1 · `silent_bad_merges` no captura absorciones silenciosas

**Estado:** deuda · detectado 2026-07-13

`count_silent_bad_merges` (`eval/characters/metrics.py:165-183`) solo cuenta un par
gold como "mal fusionado" si **ambas** entidades gold siguen siendo localizables en
pred (`pred_a`/`pred_b` no-None, línea 173: `if pred_a is None or pred_b is None:
continue`). Si una entidad gold **desaparece por completo** — absorbida dentro de
otra sin dejar un `pred` propio que haga match — la rama `continue` la salta y la
métrica no penaliza nada.

Caso real confirmado en la corrida de P&P del 2026-07-12 (grafo tras
`python -m backend.extraction.run` sobre `pride-and-prejudice.txt`, git sha
`0ad5ea6`): el gold `mrs-bennet` (`Mrs. Bennet`, sin aliases) no tiene ninguna
entidad `Character` propia en el grafo — fue absorbida dentro de `Mr. Bennet`, cuyo
nodo terminó con los aliases `["mamma", "your mother", "her mother", "the mother",
"Mamma", "their mother", "my mother"]`. `silent_bad_merges` para esa corrida reportó
`0` (ver `eval/results/characters-pride-and-prejudice-txt-20260712-0ad5ea6.json`),
pero hubo una absorción real no detectada por la métrica.

Un `silent_bad_merges: 0` en `eval/results/*.json` **no garantiza SC-003** mientras
este blind spot exista. Arreglarlo de verdad requiere procedencia a nivel de mención
(saber qué mención terminó en qué `Character` final para poder decir "el gold X no
tiene ningún representante en pred porque fue tragado por Y") — es un rediseño de la
métrica, no un parche puntual.

**Actualización 2026-07-13:** el *disparador* concreto de esta absorción (la cascada
que fusionaba `Mrs. Bennet` dentro de `Mr. Bennet`) está **resuelto** — ver la entrada
"cascada de resolución sobre-fusiona por apellido" abajo. El blind spot de la métrica
sigue siendo **deuda**: la absorción ya no ocurre por esa vía, pero la métrica seguiría
sin detectarla si otra ruta (p. ej. un auto-merge del LLM en nivel 2) la reintrodujera.
El rediseño con procedencia a nivel de mención queda diferido.

---

## M1 · Edge de `pair_known` en `count_silent_bad_merges`: infra-conteo posible

**Estado:** deuda · detectado 2026-07-13

En la misma función (`eval/characters/metrics.py:177-181`), `pair_known` decide si
una fusión detectada ya "se sabía" (existe un `MergeCandidate` para ese par) usando
el mismo matching por solapamiento de alias que `detection_f1`
(`_entities_match`, línea 31-33). Si un `MergeCandidate` real del grafo tiene
aliases genéricos o pronombres (p. ej. "her mother", "Mamma" — ver el caso de
`Mrs. Bennet`/`Mr. Bennet` arriba), ese candidate puede solapar por accidente con
*cualquier* par gold que también use un alias genérico, marcando como `pair_known =
True` un caso que en realidad no corresponde al par correcto. El efecto es
infra-contar `silent_bad_merges`: una fusión mala se descarta como "ya conocida" por
un candidate que no es el suyo. No hay caso confirmado en el grafo actual con este
patrón exacto, pero la condición estructural para que ocurra ya existe (aliases
genéricos compartidos entre personajes distintos, como se ve en el caso de arriba).

---

## M1 · Estado de la eval de Pride & Prejudice (primera medición real)

**Estado:** deuda · detectado 2026-07-13

Primera corrida real end-to-end sobre `pride-and-prejudice.txt` (2026-07-12, git sha
`0ad5ea6`, ver `eval/results/characters-pride-and-prejudice-txt-20260712-0ad5ea6.json`):

- **Detection F1 = 0.205** (precision 0.115, recall 0.900) — muy por debajo del
  umbral del gate (0.90). El gate de CI (`tests/eval/test_characters_gate.py`) no
  corre esta obra (`EVAL_WORKS` solo incluye las dos obras "crafted"); este número
  es diagnóstico, no un fallo de CI.
- **Gold parcial**: `eval/fixtures/pride-and-prejudice.txt.characters.gold.json`
  solo anota 10 protagonistas principales. El extractor identifica decenas más
  (77 `Character` en el grafo tras esta corrida) — buena parte de la precision baja
  es simplemente "personajes reales que el gold no incluye", no falsos positivos.
  El README de fixtures pide expandir el gold; esta es la primera medición real que
  cuantifica cuánto falta.
- **2 bugs de la cascada de resolución** confirmados en el grafo real: `Mrs. Bennet`
  fusionada dentro de `Mr. Bennet` (ver entrada de `silent_bad_merges` arriba), y
  `Charlotte Lucas` fusionada dentro de `Lady Lucas` (el nodo `Lady Lucas` terminó
  con aliases `["Charlotte", "Miss Lucas"]`, propios de `Charlotte Lucas` en el
  gold). **Resueltos 2026-07-13** — ver la entrada "cascada de resolución
  sobre-fusiona por apellido" abajo. Falta re-correr P&P completo para reconfirmar
  sobre datos reales (coste de cuota LLM); el mecanismo exacto está cubierto por
  tests unitarios deterministas.
- **Entidades sin nombre propio** emitidas por el extractor y presentes en el grafo:
  p. ej. `"the waiter"` y `"Pemberley"` (esta última es un lugar, no un personaje) —
  bajan precision sin ser errores de resolución.
- Decisión de abordaje (expandir gold vs. arreglar cascada de resolución vs. filtrar
  no-personajes en el extractor) pendiente.
- **B³ de P&P = no medido** (`resolution_b3: null`) — el gold no tiene anotación de
  menciones, por diseño (ver entrada de arriba); nunca se reporta un valor
  inventado.

---

## M1 · Follow-ups tras bugfixes + demo HP1 (rama `m1-extraction-bugfixes`, 2026-07-14/15)

**Estado:** parcialmente resuelto · registrados 2026-07-15 · puntos 1-4 resueltos 2026-07-15

Los 8+ bugs originales quedaron resueltos y verificados (ver commits de la rama;
crafted PASS 1.0/1.0/0, P&P F1 0.800, HP1 F1 0.806, cero merges silenciosos, cola
humana resuelta). Lo siguiente son follow-ups descubiertos durante la re-medición y
la demo de Harry Potter 1 (español), en orden de prioridad:

1. **[CRÍTICO] Aislamiento de la base de test. ✅ resuelto 2026-07-15.**
   `tests/conftest.py` (fixture `neo4j_session`) hacía `MATCH (n:{label}) DETACH
   DELETE n` sobre `Manuscript/Chapter/Scene/NonNarrativeBlock` **sin filtrar por
   manuscript_id**, contra la misma base `neo4j` que guarda los datos reales. Cada
   corrida de integración **destruía la capa cruda de todos los libros** (ocurrió 3
   veces en una sola sesión). **Resolución:** Neo4j Community solo expone una base, así
   que el fix acota el borrado a manuscritos de test (`test-*`) más las fixtures
   crafted que los tests ingieren (derivadas del mismo pipeline productivo, sin
   hardcodear el hash). Nunca toca otro `manuscript_id`. Cubierto por
   `tests/integration/test_harness_isolation.py`.

2. **[M0] Front-matter del epub extraído como personajes. ✅ resuelto 2026-07-15.**
   En HP1 el extractor sacó como personajes a la autora (J. K. Rowling), traductores e
   ilustradores y nombres de la dedicatoria. **Resolución:** `Block` gana
   `source_role`, rellenado por `EpubParser` desde el `guide` que el propio epub
   declara (cover/toc/copyright/dedication/…); `partition_paratext` aparta ese
   contenido a `NonNarrativeBlock` antes de la segmentación de capítulos, aunque
   tenga su propio heading — sin tocar prólogo/prefacio, que sigue tratándose como
   narrativa (ambigüedad resuelta por el LLM, no por esta capa determinista). Además,
   el prompt (regla 9, `PROMPT_VERSION` 3→4) instruye al modelo a devolver listas
   vacías ante paratexto que se le haya escapado a la capa estructural. Verificado en
   el reproceso real de HP1 (ver abajo): ningún nombre de autora/traductor/dedicatoria
   aparece entre los 95 personajes extraídos.

3. **[Filtro] Descriptores relacionales que capitalizan la primera palabra. ✅
   resuelto 2026-07-15.** `is_unnamed` dejaba pasar "Abuelo de Harry Potter", "Mr.
   Darcy's father" (mayúscula inicial engañaba al heurístico). **Resolución:**
   `is_unnamed` detecta construcciones genitivas/posesivas ("\<parentesco\> de/of
   \<Nombre\>", "\<Nombre\>'s \<parentesco\>") reutilizando la lista de parentescos ya
   existente; más la regla 10 del prompt, que instruye al modelo a anotar esos
   descriptores como mención (`kind="description"`), no como personaje nuevo. Verificado
   en el reproceso de HP1: ningún descriptor relacional aparece en la lista de 95
   personajes.

4. **[Política] Mascotas/animales con nombre. ✅ resuelto 2026-07-15.** El extractor
   sacaba a Hedwig, Fluffy, Scabbers, Norberto, los gatos de la Sra. Figg como
   personajes; el gold los excluye (criterio M1). **Decisión (usuario, brainstorming):**
   no crear un tipo de nodo separado (obligaría a definir ya la ontología completa de
   entidades) ni descartarlos en extracción (se pierde información irrecuperable). En
   su lugar, `Character.entity_kind` ("person" | "animal") lo marca el propio LLM
   (regla 8 del prompt) — juicio semántico que escala a libros no vistos, a diferencia
   de una lista de nombres. El eval excluye `entity_kind="animal"` del cómputo de
   detección (ni acierto ni falso positivo). Verificado: los 11 animales de HP1
   (Hedwig, Fluffy, Norberto, Scabbers, Fang, Trevor, Señora Norris, Tibbles, Snowy,
   Señor Paws, Tufty) quedaron correctamente marcados.

   **Caveat de reproducibilidad:** `entity_kind` se fija solo en `ON CREATE` del
   `MERGE` (idempotencia: una corrida repetida no debe pisar un valor ya asignado).
   Efecto práctico: reproducir estos 11 animales requiere una extracción **desde
   grafo limpio** (como en esta verificación); sobre un grafo que ya tuviera esos
   personajes como `"person"` de una corrida anterior, una re-extracción NO los
   reclasificaría — el `MERGE` haría match y `ON MATCH` no toca `entity_kind`. Hoy no
   existe una vía no destructiva para corregir una entidad mal clasificada; solo
   borrar y re-extraer.

   **Resultado de la verificación E2E (reproceso completo, 2026-07-15, prompt v4):**
   - Gate CI (crafted): PASS 1.0/1.0/0 en ambas obras — sin regresión.
   - HP1: Detection F1 **0.806 → 0.844** (mejora; menos paratexto/descriptores/animales
     contaminando la precisión). B³ sigue sin medir (gold sin anotación de menciones).
   - P&P: Detection F1 **0.800 → 0.757**. **Corrección (2026-07-15, tras revisión de
     rama):** una primera versión de esta entrada afirmaba que las 4 corridas previas
     del mismo día eran "mismo código, mismo prompt v3" oscilando 0.233–0.800, y que
     por tanto el 0.757 caía dentro de esa varianza — **esa lectura era incorrecta**.
     Verificado directamente contra `eval/results/characters-pride-and-prejudice-txt-
     20260714-*.json`: las 4 corridas usan **tres prompts distintos** (683528b →
     prompt v1, F1 0.233; ecc31c9 → prompt v2, F1 0.750; c918204 → prompt v3, F1
     0.800; 33348b6 → prompt v3, F1 0.785), no una sola versión de código. El único
     par comparable de verdad con hoy (mismo prompt v3, antes de este follow-up) es
     0.785 y 0.800. El resultado de hoy con prompt v4 (precision 0.609, recall 1.0,
     F1 0.757) queda **ligeramente por debajo** de ambos — una caída pequeña, no una
     mejora ni un no-cambio.
     No hay evidencia suficiente para afirmar que sea una regresión causada por los
     fixes de este follow-up (recall se mantiene perfecto, `silent_bad_merges=0`, y
     solo hay una muestra con prompt v4 frente a dos con v3 — el punto 6, cola larga
     no determinista, sigue siendo un factor real y no descartable), pero tampoco hay
     evidencia para descartarlo. **Queda abierto, sin explicación validada** — no se
     cierra como "dentro de varianza conocida" hasta tener más corridas con prompt v4
     que permitan comparar de verdad contra el mismo baseline (v3). No se ajustó nada
     para forzar un número mejor ni para minimizar este resultado.

5. **[Umbral] Detección 0.9 para novela completa.** P&P (0.757–0.800 según corrida) y
   HP1 (0.844) no llegan a 0.9 sobre todo por cola larga de personajes de una mención +
   política del gold, no por calidad del modelo (recall alto, cero merges silenciosos).
   El spec permite recalibrar con justificación. Opción: umbral propio para novela
   completa o tratarlas como diagnóstico no-gating; el gate de CI (crafted) se mantiene
   en 0.9. **Sigue abierto** — decisión de política pendiente, fuera del scope de este
   follow-up.

6. **[No determinismo] Cola larga.** Personajes de una sola mención (cromos de ranas:
   Merlín, Morgana…) aparecen en una corrida y no en otra. Inherente al LLM sobre
   menciones únicas. **Sigue abierto** — confirmado de nuevo por la varianza de P&P
   documentada en el punto 4.

7. **[Riesgo] Fuga de nombres canon del LLM.** El modelo emite nombres que no están en
   el texto ("Garrick Ollivander", "Arabella Figg" en HP1). Aquí ayudó; con un libro
   desconocido es riesgo de alucinación. Vigilar / anclar al texto. **Sigue abierto.**

8. **[Menor] B³ no medido en P&P ni HP1** — falta anotación de menciones (laboriosa);
   solo las crafted lo miden hoy. Y splits de coref residuales tipo Maria/Maria Lucas.
   **Sigue abierto.**

**Estado del grafo tras el punto 1:** ya no hay riesgo de que una corrida de tests
destruya datos reales; el fix acota el borrado a manuscritos de test/crafted.
