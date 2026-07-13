# Fixtures de evaluación — M0

Obras de dominio público y fixtures fabricadas para el proto-eval de segmentación
(SC-002 capítulos, SC-003 separadores de escena) y los tests unitarios/integración.

## Obras de dominio público

| Archivo | Obra | Fuente | Licencia |
|---------|------|--------|----------|
| `pride-and-prejudice.txt` | *Pride and Prejudice* (Jane Austen) | [Project Gutenberg #1342](https://www.gutenberg.org/files/1342/1342-0.txt) | Dominio público (Project Gutenberg License) |

Esta edición incluye boilerplate de Gutenberg, una "LIST OF ILLUSTRATIONS" (contenido
no-narrativo) y leyendas de ilustración — material realista para ejercitar FR-007
(exclusión de no-narrativo) y la detección de capítulos. Tiene **61 capítulos** y no usa
separadores tipográficos de escena (cada capítulo es una escena por Nivel 0).

## Fixtures fabricadas (ground truth exacta)

Generadas de forma determinista por `python eval/fixtures/build_fixtures.py`. Ejercitan
los caminos que la obra real no cubre: separadores de escena de Nivel 1, formatos
`.epub` y `.docx`, prólogo/epílogo, acentos y boilerplate sintético.

| Archivo | Formato | Capítulos | Separadores de escena | Notas |
|---------|---------|-----------|------------------------|-------|
| `crafted-three-chapters.txt` | txt | 3 (+ prólogo) | 2 (en el cap. 2) | marcadores Gutenberg sintéticos; acentos |
| `crafted-two-chapters.epub` | epub | 2 | 1 (en el cap. 1) | un documento XHTML por capítulo |
| `crafted-two-chapters.docx` | docx | 2 | 1 (separador por estilo + por símbolos) | estilos Heading 1 + párrafo separador |

Las anotaciones de referencia viven junto a cada fixture como
`<nombre>.annotation.json` (ver `eval/segmentation/accuracy.py` para el formato).

> Las fixtures `.epub`/`.docx` se regeneran con el builder; si cambia el builder,
> re-ejecutarlo y versionar los binarios resultantes.

## Golden datasets de personajes (M1)

Cada obra tiene un archivo `<nombre>.characters.gold.json` con la lista de personajes
canónicos, aliases, rol y apariciones (coordenadas `c{chapter_order}/s{scene_order}`).

### Criterios de frontera para anotación

- **Colectivos sin nombre propio** (`los soldados`, `la multitud`): NO se anotan.
- **Mascotas y animales con nombre** (p. ej. un perro llamado "Rex"): NO se anotan en M1.
- **Solo-mencionados** (personaje que nunca aparece en escena): se incluyen con
  `is_mentioned_only: true`; sus apariciones se listan en `appearances`.
- **Aliases**: se incluyen solo alias que aparecen en el texto; no variantes inventadas.
- **Homónimos**: dos personajes distintos con el mismo nombre se anotan como entidades
  separadas con `gold_id` distinto.
- **Alias que cambian de forma con el argumento** (p. ej. "Miss Lucas" → "Mrs. Collins"):
  ambas formas se incluyen en `aliases` de la misma entidad.

### Anotación a nivel de mención (`mentions`) {#mentions}

Las obras del gate de CI llevan además, por personaje, la lista de menciones:
`{"scene": "c{cap}/s{escena}", "surface": "<texto exacto>"}`.

- Se anotan solo menciones **nombradas** (name/alias/title/description); los
  pronombres resueltos (`pronoun_resolved`) quedan fuera del espacio B³.
- Una entrada por par (escena, surface): el pipeline solo persiste la primera
  ocurrencia de cada surface por escena (mention_id determinista), así que la
  clave de alineación `"c{n}/s{m}::{surface}"` es unívoca en ambos lados.
- Golds sin `mentions` (p. ej. pride-and-prejudice) reportan `resolution_b3: null`
  en el eval — la métrica queda "no medida", nunca un valor inventado.

| Archivo | Obra | Personajes anotados |
|---------|------|---------------------|
| `crafted-three-chapters.txt.characters.gold.json` | *Una Historia Fabricada* | 2 (Elena, Marco) — con anotación de menciones |
| `crafted-two-chapters.epub.characters.gold.json` | *Una Historia Fabricada* (epub) | 2 (Elena, Marco) — texto regenerado con menciones reales |
| `pride-and-prejudice.txt.characters.gold.json` | *Pride and Prejudice* | 10 personajes principales (anotación parcial inicial; expandir con primera medición real) |

> Las dos primeras obras (txt y epub) son las obras del gate de CI
> (`tests/eval/test_characters_gate.py:EVAL_WORKS`) y llevan anotación de
> menciones completa (ver sección anterior). El gold de Pride and Prejudice
> aún no la lleva.
