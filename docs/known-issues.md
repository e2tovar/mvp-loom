# Deuda técnica conocida

Registro de problemas conocidos que no bloquean el avance actual pero deben
resolverse antes de dar una métrica por válida. Cada entrada cita su ubicación.

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
  gold).
- **Entidades sin nombre propio** emitidas por el extractor y presentes en el grafo:
  p. ej. `"the waiter"` y `"Pemberley"` (esta última es un lugar, no un personaje) —
  bajan precision sin ser errores de resolución.
- Decisión de abordaje (expandir gold vs. arreglar cascada de resolución vs. filtrar
  no-personajes en el extractor) pendiente.
- **B³ de P&P = no medido** (`resolution_b3: null`) — el gold no tiene anotación de
  menciones, por diseño (ver entrada de arriba); nunca se reporta un valor
  inventado.
