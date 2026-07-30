# Respuestas LLM congeladas (material del gate)

Estas son las respuestas del modelo a "¿qué ves en esta escena?" para las **4
obras crafted** de los gates de eval — 21 escenas, 5 459 bytes de texto. Están
versionadas a propósito, al contrario que `.cache/`.

## Por qué

Sin ellas, sembrar el grafo cuesta llamadas de pago, y por eso los tres gates se
omitían solos en cualquier base limpia: la suite pasaba en verde sin haber medido
nada (`docs/known-issues.md` → "M3 · Follow-ups", punto 4).

## Qué congelan y qué NO

Congelan **solo** la salida del LLM. En cada corrida siguen ejecutándose de verdad
la resolución de entidades, la agregación, la escritura al grafo y el cálculo de
métricas — que es donde han estado casi todos los bugs reales (p. ej. la cascada
que fusionaba `Mrs. Bennet` dentro de `Mr. Bennet`: el modelo devolvía las dos
bien, el fallo era nuestro).

Lo que **no** detectan: que el proveedor cambie el modelo por debajo. Para eso
está la corrida diagnóstica manual sobre novela real.

## Cómo se regeneran

La clave de cada entrada es `SHA-256(texto_escena + PROMPT_VERSION + modelo +
SCHEMA_VERSION)`. Si cambias el prompt, el esquema o el modelo, estas entradas
dejan de acertar y el pipeline volverá a llamar al LLM — deliberado: cambiar el
prompt obliga a re-medir.

```bash
docker compose up -d
LOOM_CACHE_DIR=eval/fixtures/llm-cache python -m eval.seed
```

Modelo con el que se generaron: `openai/kimi-k2.5`. `PROMPT_VERSION` de M1 = 4,
`SCHEMA_VERSION` de M1 = 3 (2026-07-30).

## Qué NO va aquí

Las novelas completas (Orgullo y Prejuicio, Harry Potter 1). Son diagnóstico
manual, no material del gate, y su caché vive en `.cache/` sin versionar.
`tests/eval/test_frozen_cache.py::test_frozen_cache_stays_small` lo vigila.
