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
