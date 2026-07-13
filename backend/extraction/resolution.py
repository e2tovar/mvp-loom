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
import unicodedata
from dataclasses import dataclass, field

from backend.extraction.registry import EntityRegistry
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

_HONORIFICS = re.compile(
    r"^(mr\.?|mrs\.?|ms\.?|miss|dr\.?|prof\.?|sir|lord|lady|don|doña|"
    r"señor|señora|señorita|monsieur|madame|mademoiselle)\s+",
    re.IGNORECASE,
)


def _normalize(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    stripped = _HONORIFICS.sub("", ascii_str)
    return stripped.casefold().strip()


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
) -> ResolutionResult:
    """Resuelve un candidato de extracción contra el registro.

    Args:
        candidate: Entidad nueva propuesta por el LLM.
        registry: Registro de entidades acumulado.
        llm_client: Implementación de LLMClient para el nivel 2 (opcional en tests).
        prior_decisions: Diccionario {(a, b) → "accepted"|"rejected"} de decisiones
                         humanas previas (INV-M1-4).

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
        norm_candidate = _normalize(candidate.canonical_name)
        for entry in registry.all_entries():
            norm_entry = _normalize(entry.canonical_name)
            pair = _canonical_pair(entry.canonical_name, candidate.canonical_name)

            # Verificar decisiones previas (INV-M1-4)
            prior = prior_decisions.get(pair)
            if prior == "rejected":
                continue
            if prior == "accepted":
                return ResolutionResult(
                    canonical_name=entry.canonical_name,
                    merged_into=entry.canonical_name,
                )

            if not _are_similar(norm_candidate, norm_entry):
                continue

            judgement = _ask_llm_merge(
                candidate.canonical_name,
                entry.canonical_name,
                llm_client,
            )
            if judgement is None:
                continue

            if judgement.same_entity and judgement.confidence >= _MERGE_THRESHOLD:
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


def _are_similar(norm_a: str, norm_b: str) -> bool:
    """Heurística rápida para decidir si vale la pena llamar al LLM."""
    if norm_a == norm_b:
        return True
    # Subcadena (p.ej. "darcy" en "mr darcy")
    if norm_a in norm_b or norm_b in norm_a:
        return True
    # Apellido compartido (última palabra)
    parts_a = norm_a.split()
    parts_b = norm_b.split()
    if len(parts_a) > 1 and len(parts_b) > 1 and parts_a[-1] == parts_b[-1]:
        return True
    return False


def _ask_llm_merge(
    name_a: str,
    name_b: str,
    llm_client,
) -> MergeJudgement | None:
    try:
        from backend.extraction.prompts import SYSTEM_PROMPT

        user = (
            f"¿Son «{name_a}» y «{name_b}» el mismo personaje?\n"
            "Responde con same_entity, confidence (0.0–1.0) y rationale."
        )
        return llm_client.complete_structured(SYSTEM_PROMPT, user, MergeJudgement)
    except Exception as exc:
        log.warning("Error al consultar LLM para merge %s/%s: %s", name_a, name_b, exc)
        return None
