"""Pipeline de extracción de relaciones (M2, spec 003).

Flujo: escenas en orden narrativo → cast resuelto (APPEARS_IN, person) → LLM →
validación de universo cerrado → RelationEvidence en grafo → agregación
determinista → RELATES_TO. Reanudable por cache. NO modifica capas M0/M1.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from backend.core.errors import ExtractionError, NotExtractedError
from backend.extraction.relations.aggregation import aggregate_pair
from backend.extraction.relations.prompts import SYSTEM_PROMPT, build_user_prompt
from backend.extraction.relations.schemas import (
    CastEntry,
    RelationSceneContext,
    SceneRelations,
)
from backend.graph import characters as char_graph
from backend.graph import relations as rel_graph
from backend.graph.client import session as db_session
from backend.observability.tracing import traced

log = logging.getLogger(__name__)


@dataclass
class RelationsPipelineResult:
    manuscript_id: str
    scenes_processed: int = 0
    scenes_skipped: int = 0
    scenes_failed: int = 0
    evidences_written: int = 0
    relations_written: int = 0
    cache_hits: int = 0


def _load_scenes(manuscript_id: str) -> list[dict[str, Any]]:
    """Escenas de M0 en orden narrativo (misma query que el pipeline M1)."""
    with db_session() as sess:
        result = sess.run(
            """
            MATCH (m:Manuscript {manuscript_id: $mid})-[:HAS_CHAPTER]->(ch:Chapter)
                  -[:HAS_SCENE]->(s:Scene)
            RETURN s.scene_id AS scene_id,
                   s.text AS text,
                   ch.title AS chapter_title,
                   s.order_narrative_global AS order
            ORDER BY s.order_narrative_global
            """,
            mid=manuscript_id,
        )
        return [dict(r) for r in result]


def _validate_evidences(
    out: SceneRelations,
    cast_ids: set[str],
    scene_id: str,
) -> list[dict[str, Any]]:
    """Universo cerrado (FR-001) + dedupe por par (FR-002) + orden canónico."""
    by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    for ev in out.evidences:
        if ev.character_a_id not in cast_ids or ev.character_b_id not in cast_ids:
            log.warning(
                "Evidencia fuera del cast en %s: (%s, %s) — descartada",
                scene_id,
                ev.character_a_id,
                ev.character_b_id,
            )
            continue
        data = ev.model_dump()
        a, b = rel_graph.canonical_pair(ev.character_a_id, ev.character_b_id)
        if a != ev.character_a_id:  # normalizar: roles viajan con su personaje
            data["character_a_id"], data["character_b_id"] = a, b
            data["role_a"], data["role_b"] = data["role_b"], data["role_a"]
        pair = (a, b)
        if pair not in by_pair or data["confidence"] > by_pair[pair]["confidence"]:
            by_pair[pair] = data
    return list(by_pair.values())


def _trace_metadata(manuscript_id: str, llm_client=None, cache=None, force: bool = False) -> dict:
    return {
        "manuscript_id": manuscript_id,
        "model": cache.model if cache is not None else None,
        "prompt_version": cache.prompt_version if cache is not None else None,
        "schema_version": cache.schema_version if cache is not None else None,
    }


@traced("extraction.relations", metadata_fn=_trace_metadata)
def run_relations_pipeline(
    manuscript_id: str,
    llm_client=None,
    cache=None,
    force: bool = False,
) -> RelationsPipelineResult:
    """Ejecuta la extracción de relaciones para un manuscrito con capa M1."""
    scenes = _load_scenes(manuscript_id)
    if not scenes:
        from backend.core.errors import ManuscriptNotFoundError

        raise ManuscriptNotFoundError(
            f"Manuscrito no encontrado o sin escenas: {manuscript_id}"
        )

    with db_session() as sess:
        if not char_graph.has_extraction(sess, manuscript_id):
            raise NotExtractedError(
                f"M2 requiere personajes extraídos (M1) para {manuscript_id}. "
                "Ejecuta: python -m backend.extraction.run"
            )
        casts = rel_graph.get_scene_casts(sess, manuscript_id)

    if llm_client is None:
        from backend.llm.litellm_client import LiteLLMClient

        llm_client = LiteLLMClient()

    result = RelationsPipelineResult(manuscript_id=manuscript_id)

    for scene_row in scenes:
        scene_id: str = scene_row["scene_id"]
        cast = casts.get(scene_id, [])
        if len(cast) < 2:
            result.scenes_skipped += 1
            continue

        ctx = RelationSceneContext(
            scene_id=scene_id,
            chapter_title=scene_row.get("chapter_title"),
            scene_text=scene_row["text"] or "",
            cast=[CastEntry(**c) for c in cast],
        )

        out: SceneRelations | None = None
        if cache and not force:
            out = cache.get(ctx)
            if out is not None:
                result.cache_hits += 1

        if out is None:
            cast_json = json.dumps(
                [c.model_dump() for c in ctx.cast], ensure_ascii=False
            )
            try:
                out = llm_client.complete_structured(
                    SYSTEM_PROMPT,
                    build_user_prompt(
                        scene_id=scene_id,
                        chapter_title=ctx.chapter_title,
                        scene_text=ctx.scene_text,
                        cast_json=cast_json,
                    ),
                    SceneRelations,
                )
            except ExtractionError as exc:
                log.error("Escena %s falló tras reintentos: %s — se salta", scene_id, exc)
                result.scenes_failed += 1
                continue
            if cache:
                cache.set(ctx, out)

        cast_ids = {c["character_id"] for c in cast}
        scene_evidences_written = 0
        for ev in _validate_evidences(out, cast_ids, scene_id):
            with db_session() as sess:
                rel_graph.upsert_relation_evidence(sess, manuscript_id, scene_id, ev)
            result.evidences_written += 1
            scene_evidences_written += 1

        result.scenes_processed += 1
        log.info(
            "Escena %s: cast=%d, evidencias=%d",
            scene_id,
            len(cast),
            scene_evidences_written,
        )

    # Agregación sobre TODAS las evidencias persistidas (no solo esta corrida).
    with db_session() as sess:
        by_pair = rel_graph.get_evidences_by_pair(sess, manuscript_id)
        aggregated = [
            agg for evs in by_pair.values() if (agg := aggregate_pair(evs)) is not None
        ]
        rel_graph.replace_relates_to(sess, manuscript_id, aggregated)
    result.relations_written = len(aggregated)
    return result
