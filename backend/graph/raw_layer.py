"""Escritura y lectura idempotente de la capa cruda en Neo4j.

- Escritura: MERGE por ids estables derivados del contenido → re-ingerir converge al
  mismo grafo sin duplicar (FR-009, SC-005).
- Lectura: resumen estructural inspeccionable (FR-010, US2).

Las consultas Cypher viven aquí, nombradas (principio "Cypher revisable").
"""

from __future__ import annotations

from typing import Any

from neo4j import Session

from backend.core.errors import ManuscriptNotFoundError
from backend.ingest.models import Manuscript

# ── Cypher con nombre ─────────────────────────────────────────────────────────

_MERGE_MANUSCRIPT = """
MERGE (m:Manuscript {manuscript_id: $mid})
SET m += $props
"""

_MERGE_CHAPTERS = """
MATCH (m:Manuscript {manuscript_id: $mid})
UNWIND $chapters AS ch
MERGE (c:Chapter {chapter_id: ch.chapter_id})
SET c += ch.props
MERGE (m)-[:HAS_CHAPTER]->(c)
"""

_MERGE_SCENES = """
UNWIND $scenes AS sc
MATCH (c:Chapter {chapter_id: sc.chapter_id})
MERGE (s:Scene {scene_id: sc.scene_id})
SET s += sc.props
MERGE (c)-[:HAS_SCENE]->(s)
"""

_MERGE_NONNARRATIVE = """
MATCH (m:Manuscript {manuscript_id: $mid})
UNWIND $blocks AS nn
MERGE (n:NonNarrativeBlock {block_id: nn.block_id})
SET n += nn.props
MERGE (m)-[:HAS_NON_NARRATIVE]->(n)
"""

_MERGE_NEXT_CHAPTER = """
UNWIND $pairs AS p
MATCH (a:Chapter {chapter_id: p.from}), (b:Chapter {chapter_id: p.to})
MERGE (a)-[:NEXT_CHAPTER]->(b)
"""

_MERGE_NEXT_SCENE = """
UNWIND $pairs AS p
MATCH (a:Scene {scene_id: p.from}), (b:Scene {scene_id: p.to})
MERGE (a)-[:NEXT_SCENE]->(b)
"""

_EXISTS = "MATCH (m:Manuscript {manuscript_id: $mid}) RETURN count(m) AS n"

_READ_STRUCTURE = """
MATCH (m:Manuscript {manuscript_id: $mid})
OPTIONAL MATCH (m)-[:HAS_CHAPTER]->(c:Chapter)
WITH m, c ORDER BY c.order_narrative
OPTIONAL MATCH (c)-[:HAS_SCENE]->(s:Scene)
WITH m, c, s ORDER BY c.order_narrative, s.order_in_chapter
WITH m, c, collect(s) AS scenes
WITH m, collect({chapter: c, scenes: scenes}) AS chapters
OPTIONAL MATCH (m)-[:HAS_NON_NARRATIVE]->(n:NonNarrativeBlock)
RETURN m AS manuscript, chapters, collect(n) AS non_narrative
"""


# ── Helpers de propiedades ────────────────────────────────────────────────────


def _manuscript_props(m: Manuscript) -> dict[str, Any]:
    return {
        "manuscript_id": m.manuscript_id,
        "title": m.title,
        "source_format": m.source_format,
        "word_count": m.word_count,
        "chapter_count": m.chapter_count,
        "scene_count": m.scene_count,
        "ingested_at": m.ingested_at.isoformat(),
    }


def manuscript_exists(sess: Session, manuscript_id: str) -> bool:
    rec = sess.run(_EXISTS, mid=manuscript_id).single()
    return bool(rec and rec["n"] > 0)


def write_raw_layer(sess: Session, m: Manuscript) -> None:
    """Escribe la capa cruda de forma idempotente (MERGE)."""
    chapters = [
        {
            "chapter_id": c.chapter_id,
            "props": {
                "chapter_id": c.chapter_id,
                "manuscript_id": c.manuscript_id,
                "order_narrative": c.order_narrative,
                "title": c.title,
                "kind": c.kind,
                "word_count": c.word_count,
                "start_offset": c.start_offset,
                "end_offset": c.end_offset,
            },
        }
        for c in m.chapters
    ]
    scenes = [
        {
            "scene_id": s.scene_id,
            "chapter_id": s.chapter_id,
            "props": {
                "scene_id": s.scene_id,
                "chapter_id": s.chapter_id,
                "manuscript_id": s.manuscript_id,
                "order_in_chapter": s.order_in_chapter,
                "order_narrative_global": s.order_narrative_global,
                "text": s.text,
                "char_count": s.char_count,
                "start_offset": s.start_offset,
                "end_offset": s.end_offset,
                "boundary_reason": s.boundary_reason,
                "snippet": s.snippet,
            },
        }
        for c in m.chapters
        for s in c.scenes
    ]
    nn_blocks = [
        {
            "block_id": n.block_id,
            "props": {
                "block_id": n.block_id,
                "manuscript_id": n.manuscript_id,
                "kind": n.kind,
                "text": n.text,
                "detected_by": n.detected_by,
                "position": n.position,
            },
        }
        for n in m.non_narrative_blocks
    ]

    ordered_chapters = [c.chapter_id for c in m.chapters]
    chapter_pairs = [
        {"from": a, "to": b}
        for a, b in zip(ordered_chapters, ordered_chapters[1:], strict=False)
    ]
    ordered_scenes = [s.scene_id for c in m.chapters for s in c.scenes]
    scene_pairs = [
        {"from": a, "to": b}
        for a, b in zip(ordered_scenes, ordered_scenes[1:], strict=False)
    ]

    def _tx(tx: Session) -> None:
        tx.run(_MERGE_MANUSCRIPT, mid=m.manuscript_id, props=_manuscript_props(m))
        tx.run(_MERGE_CHAPTERS, mid=m.manuscript_id, chapters=chapters)
        if scenes:
            tx.run(_MERGE_SCENES, scenes=scenes)
        if nn_blocks:
            tx.run(_MERGE_NONNARRATIVE, mid=m.manuscript_id, blocks=nn_blocks)
        if chapter_pairs:
            tx.run(_MERGE_NEXT_CHAPTER, pairs=chapter_pairs)
        if scene_pairs:
            tx.run(_MERGE_NEXT_SCENE, pairs=scene_pairs)

    sess.execute_write(_tx)


def get_structure(
    sess: Session,
    manuscript_id: str,
    *,
    include_snippets: bool = True,
    snippet_len: int = 120,
) -> dict[str, Any]:
    """Devuelve el resumen estructural inspeccionable (FR-010)."""
    rec = sess.run(_READ_STRUCTURE, mid=manuscript_id).single()
    if rec is None or rec["manuscript"] is None:
        raise ManuscriptNotFoundError(f"No existe el manuscrito '{manuscript_id}'.")

    m = dict(rec["manuscript"])
    chapters_out = []
    for entry in rec["chapters"]:
        c = entry["chapter"]
        if c is None:
            continue
        c = dict(c)
        scenes_out = []
        for s in entry["scenes"]:
            s = dict(s)
            scene = {
                "order_in_chapter": s["order_in_chapter"],
                "order_narrative_global": s["order_narrative_global"],
                "char_count": s["char_count"],
                "boundary_reason": s["boundary_reason"],
            }
            if include_snippets:
                scene["snippet"] = (s.get("snippet") or "")[:snippet_len]
            scenes_out.append(scene)
        chapters_out.append(
            {
                "order_narrative": c["order_narrative"],
                "title": c.get("title"),
                "kind": c.get("kind"),
                "word_count": c["word_count"],
                "scene_count": len(scenes_out),
                "scenes": scenes_out,
            }
        )

    non_narrative = []
    for n in rec["non_narrative"]:
        if n is None:
            continue
        n = dict(n)
        non_narrative.append(
            {"kind": n["kind"], "detected_by": n["detected_by"], "position": n["position"]}
        )

    return {
        "manuscript_id": m["manuscript_id"],
        "title": m.get("title"),
        "source_format": m["source_format"],
        "word_count": m["word_count"],
        "chapter_count": m["chapter_count"],
        "scene_count": m.get("scene_count", sum(c["scene_count"] for c in chapters_out)),
        "chapters": chapters_out,
        "non_narrative_blocks": non_narrative,
    }
