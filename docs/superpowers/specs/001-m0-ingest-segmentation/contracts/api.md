# API Contract — M0 Ingestión y segmentación

**Feature**: `001-m0-ingest-segmentation` · Servicio: FastAPI · Base: `/`

M0 expone dos endpoints. La ingestión es síncrona (D8). Todos los cuerpos JSON usan los
modelos Pydantic de `data-model.md`. Errores con `application/problem+json`-like:
`{ "error": "<code>", "detail": "<mensaje legible>" }`.

---

## POST /manuscripts

Sube un manuscrito, ejecuta el pipeline (parse → segmentar → escribir capa cruda) y
devuelve el identificador y un resumen.

**Request**: `multipart/form-data`
- `file` (requerido): el archivo del manuscrito (`.epub`, `.txt` o `.docx`).

**Responses**

`201 Created` — ingestión nueva completada:
```json
{
  "manuscript_id": "9f2c…",
  "title": "Orgullo y prejuicio",
  "source_format": "epub",
  "word_count": 121532,
  "chapter_count": 61,
  "scene_count": 184,
  "non_narrative_block_count": 3,
  "created": true
}
```

`200 OK` — el mismo contenido ya estaba ingerido (idempotencia, FR-009): cuerpo idéntico
con `"created": false`. No se duplica nada en el grafo.

`400 Bad Request` — archivo vacío o corrupto (FR-011):
```json
{ "error": "invalid_file", "detail": "El archivo está vacío o no se pudo leer." }
```

`415 Unsupported Media Type` — formato no soportado (FR-011):
```json
{ "error": "unsupported_format", "detail": "Formato '.pdf' no soportado. Use epub, txt o docx." }
```

`422 Unprocessable Entity` — el archivo se leyó pero no contiene narrativa segmentable
(p. ej. solo boilerplate):
```json
{ "error": "no_narrative_content", "detail": "No se detectó contenido narrativo." }
```

**Garantías**
- Determinista: misma entrada → mismo `manuscript_id` y mismo recuento (SC-005).
- Idempotente: reenviar el mismo contenido nunca crea duplicados (FR-009).
- Sin pérdida: el texto narrativo se preserva íntegro (FR-008, SC-004).

---

## GET /manuscripts/{manuscript_id}/structure

Devuelve el resumen estructural inspeccionable que sustenta la verificación manual del
DoD (FR-010, US2, SC-008).

**Path params**: `manuscript_id` (str).

**Query params** (opcionales):
- `include_snippets` (bool, default `true`): incluir el fragmento identificador por
  escena.
- `snippet_len` (int, default `120`): longitud del fragmento.

**Responses**

`200 OK`:
```json
{
  "manuscript_id": "9f2c…",
  "title": "Orgullo y prejuicio",
  "source_format": "epub",
  "word_count": 121532,
  "chapter_count": 61,
  "scene_count": 184,
  "chapters": [
    {
      "order_narrative": 1,
      "title": "Capítulo 1",
      "kind": "chapter",
      "word_count": 1043,
      "scene_count": 2,
      "scenes": [
        {
          "order_in_chapter": 1,
          "order_narrative_global": 1,
          "char_count": 2310,
          "boundary_reason": "chapter_start",
          "snippet": "Es una verdad universalmente reconocida…"
        }
      ]
    }
  ],
  "non_narrative_blocks": [
    { "kind": "license", "detected_by": "gutenberg_marker", "position": "before" }
  ]
}
```

`404 Not Found` — no existe ese manuscrito:
```json
{ "error": "not_found", "detail": "No existe el manuscrito '9f2c…'." }
```

**Garantías**
- La jerarquía capítulo→escena, los conteos y los fragmentos bastan para localizar un
  error de segmentación (US2, escenario 2).
- El resumen es estable entre llamadas mientras la capa cruda sea inmutable (FR-006).

---

## Notas de contrato

- Estos contratos son el límite externo de M0; cualquier cambio incompatible exige
  versionar (política de la constitución).
- Endpoints de borrado/re-ingestión explícita y soporte por lotes quedan fuera de M0.
- El frontend (M7) consumirá `GET …/structure`; el contrato se diseña ya pensando en esa
  vista.
