"""Resolución de entidades: cascada determinista → LLM → cola humana (research R3).

Niveles:
1. Determinista (confianza 1.0): coincidencia exacta o alias conocido → auto-merge.
2. Heurístico + LLM (confianza calculada): similitud de nombre → MergeJudgement.
   - confianza ≥ 0.9  → auto-merge
   - 0.5 ≤ c < 0.9    → MergeCandidate (cola humana)
   - c < 0.5           → entidades separadas, sin cola
3. Colectivos sin nombre propio → filtrados.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from backend.extraction.registry import EntityRegistry, _split
from backend.extraction.schemas import CharacterCandidateOut, MergeJudgement

log = logging.getLogger(__name__)

# Umbral de auto-merge LLM
_MERGE_THRESHOLD: float = 0.9
# Umbral mínimo para encolar como MergeCandidate
_QUEUE_THRESHOLD: float = 0.5

_COLLECTIVE_PATTERN = re.compile(
    r"^(los|las|unos|unas|the|some|all|every|those|these|a group|"
    r"el grupo|la multitud|todos|todas|varios|varias)\b",
    re.IGNORECASE,
)

def is_collective(name: str) -> bool:
    return bool(_COLLECTIVE_PATTERN.match(name.strip()))


_LEADING_ARTICLE = re.compile(
    r"^(the|a|an|el|la|los|las|un|una|unos|unas|one of the|one of|some of the)\s+",
    re.IGNORECASE,
)


def is_unnamed(name: str) -> bool:
    """Descriptor genérico sin nombre propio («the waiter», «one of the girls»).

    Tras quitar el artículo inicial, si ningún token empieza en mayúscula no hay
    nombre propio → no es un personaje anotable (criterios del gold,
    eval/fixtures/README.md).
    """
    stripped = _LEADING_ARTICLE.sub("", name.strip())
    if not stripped:
        return True
    return not any(tok[:1].isupper() for tok in stripped.split())


@dataclass
class MergeCandidateProposal:
    """Propuesta de fusión en zona gris para la cola humana."""

    canonical_a: str
    canonical_b: str
    confidence: float
    rationale: str
    evidence: list[dict] = field(default_factory=list)


@dataclass
class ResolutionResult:
    """Resultado de resolver un CharacterCandidateOut contra el registro."""

    canonical_name: str
    merged_into: str | None = None  # None = entidad nueva o auto-merge ya aplicado
    merge_candidate: MergeCandidateProposal | None = None
    filtered: bool = False  # colectivo/sin-nombre: NO escribir al grafo


def resolve_candidate(
    candidate: CharacterCandidateOut,
    registry: EntityRegistry,
    llm_client=None,
    prior_decisions: dict[tuple[str, str], str] | None = None,
    scene_text: str = "",
) -> ResolutionResult:
    """Resuelve un candidato de extracción contra el registro.

    Args:
        candidate: Entidad nueva propuesta por el LLM.
        registry: Registro de entidades acumulado.
        llm_client: Implementación de LLMClient para el nivel 2 (opcional en tests).
        prior_decisions: Diccionario {(a, b) → "accepted"|"rejected"} de decisiones
                         humanas previas (INV-M1-4).
        scene_text: Texto completo de la escena donde apareció `candidate`, usado
                    como evidencia (fragmento) en el juicio LLM de nivel 2.

    Returns:
        ResolutionResult con el nombre canónico final y posibles candidatos de fusión.
    """
    if is_collective(candidate.canonical_name) or is_unnamed(candidate.canonical_name):
        log.debug("Filtrado (colectivo/sin nombre): %s", candidate.canonical_name)
        return ResolutionResult(canonical_name=candidate.canonical_name, filtered=True)

    prior_decisions = prior_decisions or {}

    # Nivel 1: coincidencia determinista
    existing = registry.find(candidate.canonical_name)
    if existing:
        return ResolutionResult(
            canonical_name=existing.canonical_name,
            merged_into=existing.canonical_name,
        )

    # Comprobar aliases del candidato
    for alias in candidate.aliases:
        existing = registry.find(alias)
        if existing:
            return ResolutionResult(
                canonical_name=existing.canonical_name,
                merged_into=existing.canonical_name,
            )

    # Nivel 2: similitud heurística + LLM
    if llm_client is not None:
        for entry in registry.all_entries():
            pair = _canonical_pair(entry.canonical_name, candidate.canonical_name)

            prior = prior_decisions.get(pair)
            if prior == "rejected":
                continue
            if prior == "accepted":
                return ResolutionResult(
                    canonical_name=entry.canonical_name,
                    merged_into=entry.canonical_name,
                )

            similar, allow_auto = _are_similar(
                candidate.canonical_name, entry.canonical_name
            )
            if not similar:
                continue

            judgement = _ask_llm_merge(candidate, entry, scene_text, llm_client)
            if judgement is None:
                continue

            if (
                judgement.same_entity
                and allow_auto
                and judgement.confidence >= _MERGE_THRESHOLD
            ):
                log.debug(
                    "Auto-merge LLM: %s → %s (confianza=%.2f)",
                    candidate.canonical_name,
                    entry.canonical_name,
                    judgement.confidence,
                )
                return ResolutionResult(
                    canonical_name=entry.canonical_name,
                    merged_into=entry.canonical_name,
                )

            if judgement.same_entity and judgement.confidence >= _QUEUE_THRESHOLD:
                proposal = MergeCandidateProposal(
                    canonical_a=entry.canonical_name,
                    canonical_b=candidate.canonical_name,
                    confidence=judgement.confidence,
                    rationale=judgement.rationale,
                )
                return ResolutionResult(
                    canonical_name=candidate.canonical_name,
                    merge_candidate=proposal,
                )

    return ResolutionResult(canonical_name=candidate.canonical_name)


def _canonical_pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def _are_similar(name_a: str, name_b: str) -> tuple[bool, bool]:
    """(similar, allow_auto_merge) — decide si consultar al LLM y con qué techo.

    - Honoríficos distintos y ambos presentes (Mr./Mrs./Miss sobre la misma
      base) → personas distintas por definición: ni similar ni fusionable.
    - Apellido compartido con nombre de pila distinto → similar, pero el
      auto-merge queda vetado: como máximo cola humana (SC-003).
    """
    hon_a, base_a = _split(name_a)
    hon_b, base_b = _split(name_b)

    if hon_a and hon_b and hon_a != hon_b:
        return False, False

    if base_a == base_b or base_a in base_b or base_b in base_a:
        return True, True

    parts_a, parts_b = base_a.split(), base_b.split()
    if len(parts_a) > 1 and len(parts_b) > 1 and parts_a[-1] == parts_b[-1]:
        return True, parts_a[:-1] == parts_b[:-1]

    return False, False


_SCENE_EXCERPT_CHARS = 1500


def _ask_llm_merge(
    candidate: CharacterCandidateOut,
    entry,
    scene_text: str,
    llm_client,
) -> MergeJudgement | None:
    try:
        from backend.extraction.prompts import MERGE_SYSTEM_PROMPT, build_merge_prompt

        user = build_merge_prompt(
            name_a=entry.canonical_name,
            aliases_a=entry.aliases,
            role_a=entry.role,
            name_b=candidate.canonical_name,
            aliases_b=candidate.aliases,
            role_b=candidate.role,
            scene_excerpt=scene_text[:_SCENE_EXCERPT_CHARS],
        )
        return llm_client.complete_structured(MERGE_SYSTEM_PROMPT, user, MergeJudgement)
    except Exception as exc:
        log.warning(
            "Error al consultar LLM para merge %s/%s: %s",
            entry.canonical_name,
            candidate.canonical_name,
            exc,
        )
        return None
