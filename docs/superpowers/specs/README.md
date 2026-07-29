# Specs

Especificaciones del proyecto, dentro del flujo **superpowers**. Dos tipos de contenido conviven aquí:

- **Carpetas `NNN-slug/`** — el **spec formal** de cada milestone (fuente de verdad viva).
  Cada una reúne `spec.md` (qué y por qué), `data-model.md` (la ontología), `quickstart.md`
  (el flujo ejecutable) y `contracts/` (schemas de API/extracción y Cypher). El plan de
  implementación NO vive aquí, sino en [`../plans/`](../plans/).
- **Archivos sueltos `YYYY-MM-DD-*-design.md`** — **design docs** de brainstorming, precursores
  de un spec formal. Son registro del discovery; el spec formal de la carpeta correspondiente
  los sustituye como fuente de verdad.

Los artefactos de planificación pesada de M0/M1 (`plan.md`, `tasks.md`, `research.md`,
`checklists/`), heredados de un formato anterior, están archivados en [`../legacy/`](../legacy/).

Los principios que todo spec debe respetar (la "constitución": eval-first, grafo = única fuente
de verdad, contratos tipados, etc.) están en el `README.md` de la raíz del repo, §2.
