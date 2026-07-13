"""Pipeline de extracción de personajes (T014).

Flujo: escenas en orden narrativo → SceneContext → LLM → verificar surfaces/offsets
→ resolución → escritura al grafo. Reanudable por cache (T032/T033, US4).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from backend.extraction.prompts import SYSTEM_PROMPT, build_user_prompt
from backend.extraction.registry import EntityRegistry
from backend.extraction.resolution import (
    MergeCandidateProposal,
    ResolutionResult,
    resolve_candidate,
)
from backend.extraction.schemas import SceneContext, SceneExtraction
from backend.graph import characters as char_graph
from backend.graph.client import session as db_session

log = logging.getLogger(__name__)


@dataclass
class SceneResult:
    scene_id: str
    characters_seen: list[str] = field(default_factory=list)
    mentions_written: int = 0
    merge_proposals: list[MergeCandidateProposal] = field(default_factory=list)
    cache_hit: bool = False


@dataclass
class PipelineResult:
    manuscript_id: str
    total_characters: int = 0
    total_mentions: int = 0
    total_merge_candidates: int = 0
    scenes_processed: int = 0
    scene_results: list[SceneResult] = field(default_factory=list)


def _load_scenes(manuscript_id: str) -> list[dict[str, Any]]:
    """Carga escenas de M0 en orden narrativo."""
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


def _find_offset(text: str, surface: str) -> tuple[int, int] | None:
    """Localiza `surface` en `text`; devuelve (start, end) o None si no existe."""
    idx = text.find(surface)
    if idx == -1:
        return None
    return idx, idx + len(surface)


def _prior_decisions(manuscript_id: str) -> dict[tuple[str, str], str]:
    """Carga decisiones humanas previas usando canonical_names como clave (INV-M1-4)."""
    decisions: dict[tuple[str, str], str] = {}
    with db_session() as sess:
        result = sess.run(
            """
            MATCH (mc:MergeCandidate {manuscript_id: $mid})
            WHERE mc.status IN ['accepted', 'rejected']
            MATCH (a:Character {character_id: mc.character_a_id})
            MATCH (b:Character {character_id: mc.character_b_id})
            RETURN a.canonical_name AS a, b.canonical_name AS b, mc.status AS status
            """,
            mid=manuscript_id,
        )
        for rec in result:
            pair = (rec["a"], rec["b"]) if rec["a"] < rec["b"] else (rec["b"], rec["a"])
            decisions[pair] = rec["status"]
    return decisions


def _write_merge_candidate(
    manuscript_id: str,
    proposal: MergeCandidateProposal,
    registry: EntityRegistry,
) -> None:
    """Persiste un MergeCandidate en el grafo (sin fusionar)."""
    cid_a = char_graph.character_id(manuscript_id, proposal.canonical_a)
    cid_b = char_graph.character_id(manuscript_id, proposal.canonical_b)
    mc_id = char_graph.merge_candidate_id(cid_a, cid_b)
    with db_session() as sess:
        sess.run(
            """
            MERGE (mc:MergeCandidate {candidate_id: $mc_id})
            ON CREATE SET
                mc.manuscript_id   = $mid,
                mc.character_a_id  = $cid_a,
                mc.character_b_id  = $cid_b,
                mc.confidence      = $confidence,
                mc.rationale       = $rationale,
                mc.evidence_json   = $evidence,
                mc.status          = 'pending'
            WITH mc
            MATCH (m:Manuscript {manuscript_id: $mid})
            MERGE (m)-[:HAS_MERGE_CANDIDATE]->(mc)
            WITH mc
            MATCH (a:Character {character_id: $cid_a})
            MERGE (mc)-[:PROPOSES_MERGE]->(a)
            WITH mc
            MATCH (b:Character {character_id: $cid_b})
            MERGE (mc)-[:PROPOSES_MERGE]->(b)
            """,
            mc_id=mc_id,
            mid=manuscript_id,
            cid_a=cid_a,
            cid_b=cid_b,
            confidence=proposal.confidence,
            rationale=proposal.rationale,
            evidence=json.dumps(proposal.evidence),
        )


def run_pipeline(
    manuscript_id: str,
    llm_client=None,
    cache=None,
    force: bool = False,
) -> PipelineResult:
    """Ejecuta el pipeline de extracción para un manuscrito.

    Args:
        manuscript_id: Id del manuscrito (debe existir en M0).
        llm_client: Instancia de LLMClient. Si es None se construye desde env.
        cache: Instancia de ExtractionCache (T032). None = sin cache.
        force: Si True, ignora la cache (respeta decisiones humanas).
    """
    if llm_client is None:
        from backend.llm.litellm_client import LiteLLMClient

        llm_client = LiteLLMClient()

    scenes = _load_scenes(manuscript_id)
    if not scenes:
        from backend.core.errors import ManuscriptNotFoundError

        raise ManuscriptNotFoundError(f"Manuscrito no encontrado o sin escenas: {manuscript_id}")

    prior = _prior_decisions(manuscript_id)
    registry = EntityRegistry()
    filtered_names: set[str] = set()
    result = PipelineResult(manuscript_id=manuscript_id)

    for scene_row in scenes:
        scene_id: str = scene_row["scene_id"]
        scene_text: str = scene_row["text"] or ""
        chapter_title: str | None = scene_row.get("chapter_title")

        ctx = SceneContext(
            scene_id=scene_id,
            chapter_title=chapter_title,
            scene_text=scene_text,
            known_entities=registry.all_entries(),
        )

        scene_res = SceneResult(scene_id=scene_id)

        # Cache lookup (T033 integra la cache aquí)
        extraction: SceneExtraction | None = None
        if cache and not force:
            extraction = cache.get(ctx)
            if extraction:
                scene_res.cache_hit = True
                log.debug("Cache hit: %s", scene_id)

        if extraction is None:
            user_prompt = build_user_prompt(
                scene_id=scene_id,
                chapter_title=chapter_title,
                scene_text=scene_text,
                known_entities_json=json.dumps(registry.to_json_list(), ensure_ascii=False),
            )
            extraction = llm_client.complete_structured(
                SYSTEM_PROMPT, user_prompt, SceneExtraction
            )
            if cache:
                cache.set(ctx, extraction)

        # Procesar entidades nuevas
        for candidate in extraction.new_characters:
            res: ResolutionResult = resolve_candidate(
                candidate,
                registry,
                llm_client=llm_client,
                prior_decisions=prior,
                scene_text=scene_text,
            )

            if res.filtered:
                filtered_names.add(candidate.canonical_name)
                for alias in candidate.aliases:
                    filtered_names.add(alias)
                continue

            canonical = res.canonical_name if res.merged_into is None else res.merged_into

            # Registrar en el registry (si es entidad nueva o alias actualizado)
            if res.merged_into is None:
                registry.add(canonical, candidate.aliases, candidate.role)
            else:
                # Añadir posibles alias nuevos a la entidad existente
                entry = registry.find(canonical)
                if entry:
                    new_aliases = list(set(entry.aliases) | set(candidate.aliases))
                    registry.add(canonical, new_aliases, entry.role)

            # Persistir en grafo
            with db_session() as sess:
                cid = char_graph.upsert_character(
                    sess=sess,
                    manuscript_id=manuscript_id,
                    canonical_name=canonical,
                    aliases=registry.find(canonical).aliases if registry.find(canonical) else [],
                    role=candidate.role,
                    is_mentioned_only=not candidate.is_present_in_scene,
                    first_scene_id=scene_id,
                )

            if res.merge_candidate:
                scene_res.merge_proposals.append(res.merge_candidate)
                _write_merge_candidate(manuscript_id, res.merge_candidate, registry)

            scene_res.characters_seen.append(canonical)

        # Procesar menciones
        for mention in extraction.mentions:
            offsets = _find_offset(scene_text, mention.surface)
            if offsets is None:
                log.warning(
                    "Surface '%s' no encontrado en escena %s — descartado",
                    mention.surface,
                    scene_id,
                )
                continue

            start, end = offsets
            canonical = mention.links_to or mention.surface
            entry = registry.find(canonical)
            if entry is None:
                if canonical in filtered_names or mention.surface in filtered_names:
                    log.debug("Mención de entidad filtrada descartada: %s", mention.surface)
                else:
                    log.warning(
                        "Mención sin personaje registrado ('%s') en escena %s — descartada",
                        canonical,
                        scene_id,
                    )
                continue
            canonical = entry.canonical_name

            cid = char_graph.character_id(manuscript_id, canonical)
            with db_session() as sess:
                char_graph.upsert_mention(
                    sess=sess,
                    scene_id=scene_id,
                    manuscript_id=manuscript_id,
                    character_id_val=cid,
                    surface=mention.surface,
                    kind=mention.kind,
                    start_offset=start,
                    end_offset=end,
                    quote=mention.quote,
                )

            scene_res.mentions_written += 1

        # APPEARS_IN por escena (si hubo menciones)
        if scene_res.mentions_written > 0:
            for canonical in set(scene_res.characters_seen):
                cid = char_graph.character_id(manuscript_id, canonical)
                with db_session() as sess:
                    char_graph.upsert_appears_in(
                        sess=sess,
                        character_id_val=cid,
                        scene_id=scene_id,
                        kind="present",
                        mention_count_in_scene=scene_res.mentions_written,
                        first_mention_id="",
                    )

        result.total_mentions += scene_res.mentions_written
        result.total_merge_candidates += len(scene_res.merge_proposals)
        result.scenes_processed += 1
        result.scene_results.append(scene_res)

        log.info(
            "Escena %s: %d menciones, %d nuevos, cache=%s",
            scene_id,
            scene_res.mentions_written,
            len(scene_res.characters_seen),
            scene_res.cache_hit,
        )

    result.total_characters = len(registry)
    return result
