"""Tests unitarios de la cola de fusiones (T030).

Sin Neo4j: testea lógica de id, zona gris y decisiones previas.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.extraction.registry import EntityRegistry
from backend.extraction.resolution import resolve_candidate
from backend.extraction.schemas import CharacterCandidateOut, MergeJudgement
from backend.graph.characters import merge_candidate_id


def _candidate(name: str, aliases=None) -> CharacterCandidateOut:
    return CharacterCandidateOut(
        canonical_name=name,
        aliases=aliases or [],
        role="unknown",
        is_present_in_scene=True,
    )


def _fake_llm(same: bool, confidence: float) -> MagicMock:
    client = MagicMock()
    client.complete_structured.return_value = MergeJudgement(
        same_entity=same, confidence=confidence, rationale="test"
    )
    return client


# ── Id determinista del par ───────────────────────────────────────────────────


def test_merge_candidate_id_deterministic():
    """El id del candidato no depende del orden de los argumentos."""
    id_ab = merge_candidate_id("ms:ch:aaa", "ms:ch:bbb")
    id_ba = merge_candidate_id("ms:ch:bbb", "ms:ch:aaa")
    assert id_ab == id_ba


def test_merge_candidate_id_unique_for_different_pairs():
    id1 = merge_candidate_id("ms:ch:aaa", "ms:ch:bbb")
    id2 = merge_candidate_id("ms:ch:aaa", "ms:ch:ccc")
    assert id1 != id2


# ── Zona gris encola en vez de fusionar ──────────────────────────────────────


def test_gray_zone_creates_proposal_not_merge():
    """Confianza en [0.5, 0.9) → MergeCandidate, sin merge aplicado."""
    reg = EntityRegistry()
    reg.add("Elizabeth", [], "protagonist")
    # "Eli" es subcadena de "elizabeth" → _are_similar=True → LLM consultado
    cand = _candidate("Eli")
    result = resolve_candidate(cand, reg, llm_client=_fake_llm(True, 0.75))
    assert result.merged_into is None
    assert result.merge_candidate is not None
    assert result.merge_candidate.confidence == 0.75


def test_high_confidence_auto_merges():
    """Confianza ≥ 0.9 → merged_into, sin propuesta de candidato."""
    reg = EntityRegistry()
    reg.add("Elena", [], "protagonist")
    cand = _candidate("Elena")
    result = resolve_candidate(cand, reg, llm_client=_fake_llm(True, 0.95))
    assert result.merged_into == "Elena"
    assert result.merge_candidate is None


# ── Decisiones previas respetadas ────────────────────────────────────────────


def test_rejected_pair_not_re_proposed():
    """Un par con decisión 'rejected' no genera nueva propuesta (INV-M1-4)."""
    reg = EntityRegistry()
    reg.add("Elizabeth", [], "secondary")
    # "Eli" es subcadena → similar → LLM consultado → pero pair rejected
    cand = _candidate("Eli")
    pair = ("Eli", "Elizabeth") if "Eli" < "Elizabeth" else ("Elizabeth", "Eli")
    prior = {pair: "rejected"}
    result = resolve_candidate(cand, reg, llm_client=_fake_llm(True, 0.8), prior_decisions=prior)
    assert result.merge_candidate is None


def test_accepted_pair_auto_merges_without_llm():
    """Un par con decisión 'accepted' se fusiona directamente (INV-M1-4)."""
    reg = EntityRegistry()
    reg.add("Elizabeth", [], "secondary")
    cand = _candidate("Eli")
    pair = ("Eli", "Elizabeth") if "Eli" < "Elizabeth" else ("Elizabeth", "Eli")
    prior = {pair: "accepted"}
    result = resolve_candidate(cand, reg, llm_client=_fake_llm(True, 0.8), prior_decisions=prior)
    assert result.merged_into == "Elizabeth"
