# Deuda técnica conocida

Registro de problemas conocidos que no bloquean el avance actual pero deben
resolverse antes de dar una métrica por válida. Cada entrada cita su ubicación.

---

## M1 · La resolución B³ no está realmente cableada (stub)

**Estado:** deuda · detectado 2026-06-15

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

**Camino de salida (cuando se aborde):**
- Pasar `pred_clusters` reales a `bcubed_f1` (dejar de descartarlos).
- Anotar menciones en el gold (clusters de `mention_id` con surface/offsets) para que gold
  y pred compartan el mismo espacio de IDs y B³ sea fiel a research R4.
- Cargar los pares `MergeCandidate` reales para `count_silent_bad_merges`.

**Nota de coherencia:** mientras esto sea deuda, `docs/ABOUT.md` (M1 "✅ Completo";
"resolución B³ ≥ 0.85" como umbral vigente que corre en CI y bloquea el merge) sobre-afirma
el estado real. El gate de `tests/eval/test_characters_gate.py` hace SKIP cuando no hay
extracción, no PASS.
