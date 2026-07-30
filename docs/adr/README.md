# Architecture Decision Records

Decisiones de arquitectura del proyecto, con su contexto, la decisión tomada,
sus consecuencias y las alternativas descartadas. Un ADR se escribe cuando una
elección técnica es difícil de revertir o condiciona milestones posteriores.

## Convención

- Nombre de archivo: `NNNN-titulo-en-kebab-case.md` (cuatro dígitos, correlativo).
- Encabezado uniforme:
  - Título: `# ADR-NNNN — <título legible>`
  - Metadatos: `**Estado**: Aceptada · **Fecha**: YYYY-MM-DD · **Milestone**: MX`
- Estados posibles: `Propuesta`, `Aceptada`, `Sustituida por ADR-NNNN`, `Obsoleta`.
- Un ADR aceptado no se edita para cambiar la decisión: se crea uno nuevo que lo sustituye.

## Índice

| ADR | Título | Estado | Milestone |
|-----|--------|--------|-----------|
| [0001](0001-raw-layer-in-neo4j.md) | La capa cruda vive en Neo4j desde M0 | Aceptada | M0 |
| [0002](0002-llm-gateway-litellm.md) | LLM Gateway: LiteLLM multi-proveedor | Aceptada | M1 |
| [0003](0003-langfuse-observability.md) | Observabilidad de producción con Langfuse (self-hosted) | Aceptada | cross-cutting |
