"""Tests unitarios de resolución de entidades (T017).

Sin red, sin Neo4j: LLM falso inyectado donde se necesita.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.extraction.registry import EntityRegistry, is_unnamed
from backend.extraction.resolution import (
    MergeCandidateProposal,
    is_collective,
    resolve_candidate,
)
from backend.extraction.schemas import CharacterCandidateOut, MergeJudgement


def _candidate(name: str, aliases=None, role="unknown", present=True) -> CharacterCandidateOut:
    return CharacterCandidateOut(
        canonical_name=name,
        aliases=aliases or [],
        role=role,
        is_present_in_scene=present,
    )


def _registry(*names: str) -> EntityRegistry:
    reg = EntityRegistry()
    for n in names:
        reg.add(n, [], "unknown")
    return reg


# ── Normalización ─────────────────────────────────────────────────────────────


def test_normalize_honorifics():
    """Entidades con y sin honorífico se reconocen como iguales."""
    reg = EntityRegistry()
    reg.add("Darcy", [], "secondary")
    cand = _candidate("Mr. Darcy")
    result = resolve_candidate(cand, reg)
    assert result.merged_into == "Darcy"


def test_normalize_accents():
    """Nombres con/sin acentos se normalizan al mismo token."""
    reg = EntityRegistry()
    reg.add("Inés", [], "secondary")
    cand = _candidate("Inés")
    result = resolve_candidate(cand, reg)
    assert result.merged_into == "Inés"


# ── Honoríficos distintos NO fusionan (bug de cascada P&P) ────────────────────


def test_different_honorifics_same_surname_not_merged():
    """Mr. X y Mrs. X comparten apellido pero distinto honorífico → NO auto-merge.

    Caso real P&P: `Mrs. Bennet` fue absorbida en `Mr. Bennet` porque ambos
    normalizaban a "bennet". El honorífico es lo único que los distingue.
    """
    reg = _registry("Mr. Bennet")
    result = resolve_candidate(_candidate("Mrs. Bennet"), reg, llm_client=None)
    assert result.merged_into is None
    assert result.canonical_name == "Mrs. Bennet"


def test_conflicting_honorific_alias_not_merged():
    """Miss Lucas (alias de Charlotte) y Lady Lucas → distinto honorífico → separados.

    Caso real P&P: `Charlotte Lucas` (alias "Miss Lucas") fue absorbida en
    `Lady Lucas` porque "miss lucas" y "lady lucas" normalizaban a "lucas".
    """
    reg = EntityRegistry()
    reg.add("Charlotte Lucas", ["Miss Lucas"], "secondary")
    result = resolve_candidate(_candidate("Lady Lucas"), reg, llm_client=None)
    assert result.merged_into is None
    assert result.canonical_name == "Lady Lucas"


def test_registry_keeps_distinct_honorifics_separate():
    """El registro no colapsa dos honoríficos distintos sobre el mismo apellido."""
    reg = EntityRegistry()
    reg.add("Mr. Bennet", [], "secondary")
    reg.add("Mrs. Bennet", [], "secondary")
    assert len(reg) == 2


def test_bare_name_still_matches_single_honorific_form():
    """Un apellido sin honorífico sí resuelve a la única forma con honorífico (Darcy)."""
    reg = EntityRegistry()
    reg.add("Mr. Darcy", [], "protagonist")
    result = resolve_candidate(_candidate("Darcy"), reg, llm_client=None)
    assert result.merged_into == "Mr. Darcy"


# ── Auto-merge determinista ───────────────────────────────────────────────────


def test_exact_match_auto_merges():
    """Match exacto → merged_into sin llamar al LLM."""
    reg = _registry("Elizabeth Bennet")
    result = resolve_candidate(_candidate("Elizabeth Bennet"), reg)
    assert result.merged_into == "Elizabeth Bennet"
    assert result.merge_candidate is None


def test_alias_match_auto_merges():
    """Match por alias → merged_into sin llamar al LLM."""
    reg = EntityRegistry()
    reg.add("Elizabeth Bennet", ["Lizzy", "Eliza"], "protagonist")
    result = resolve_candidate(_candidate("Lizzy"), reg)
    assert result.merged_into == "Elizabeth Bennet"


def test_new_entity_no_merge():
    """Entidad completamente nueva → sin merge, sin propuesta."""
    reg = _registry("Elizabeth Bennet")
    result = resolve_candidate(_candidate("Mr. Collins"), reg)
    assert result.merged_into is None
    assert result.merge_candidate is None
    assert result.canonical_name == "Mr. Collins"


# ── Homónimos NO fusionados por similitud ─────────────────────────────────────


def test_homonym_not_merged_without_llm():
    """Sin LLM client, entidades similares pero distintas no se fusionan."""
    reg = _registry("Thomas Hardy")
    cand = _candidate("Thomas")
    result = resolve_candidate(cand, reg, llm_client=None)
    assert result.merged_into is None


# ── Colectivos filtrados ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    ["los soldados", "la multitud", "todos", "the crowd", "some villagers"],
)
def test_collective_is_detected(name):
    assert is_collective(name) is True


def test_collective_returns_as_is():
    """Colectivo → ResolutionResult sin merge ni propuesta."""
    reg = _registry("Ana")
    result = resolve_candidate(_candidate("los guardias"), reg)
    assert result.merged_into is None
    assert result.merge_candidate is None
    assert result.filtered is True


# ── Descriptores sin nombre propio ────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    ["the waiter", "one of the girls", "the young lady", "el mozo", "the coachman"],
)
def test_unnamed_descriptor_detected(name):
    assert is_unnamed(name) is True


@pytest.mark.parametrize("name", ["Sarah", "Mr. Darcy", "Elizabeth Bennet", "Álvaro"])
def test_named_character_not_unnamed(name):
    assert is_unnamed(name) is False


def test_collective_result_is_filtered():
    """Colectivo → filtered=True para que el pipeline NO lo escriba."""
    reg = _registry("Ana")
    result = resolve_candidate(_candidate("los guardias"), reg)
    assert result.filtered is True


def test_unnamed_result_is_filtered():
    reg = _registry("Ana")
    result = resolve_candidate(_candidate("the waiter"), reg)
    assert result.filtered is True


def test_normal_candidate_not_filtered():
    reg = _registry("Ana")
    result = resolve_candidate(_candidate("Mr. Collins"), reg)
    assert result.filtered is False


# ── Zona gris va a cola (LLM falso) ──────────────────────────────────────────


def _fake_llm(same: bool, confidence: float) -> MagicMock:
    client = MagicMock()
    client.complete_structured.return_value = MergeJudgement(
        same_entity=same,
        confidence=confidence,
        rationale="test",
    )
    return client


def test_high_confidence_auto_merges_via_llm():
    """Confianza ≥ 0.9 → auto-merge."""
    reg = _registry("Darcy")
    cand = _candidate("Mr Darcy")
    result = resolve_candidate(cand, reg, llm_client=_fake_llm(True, 0.95))
    assert result.merged_into == "Darcy"


def test_gray_zone_queues_candidate():
    """0.5 ≤ confianza < 0.9 → MergeCandidate, entidades separadas."""
    reg = _registry("Elizabeth")
    cand = _candidate("Eliza")
    result = resolve_candidate(cand, reg, llm_client=_fake_llm(True, 0.72))
    assert result.merged_into is None
    assert isinstance(result.merge_candidate, MergeCandidateProposal)
    assert result.merge_candidate.confidence == 0.72


def test_low_confidence_no_queue():
    """Confianza < 0.5 → sin merge, sin propuesta (demasiado dudoso)."""
    reg = _registry("Ana")
    cand = _candidate("Annie")
    result = resolve_candidate(cand, reg, llm_client=_fake_llm(True, 0.3))
    assert result.merged_into is None
    assert result.merge_candidate is None


# ── Decisiones previas respetadas ────────────────────────────────────────────


def test_rejected_decision_not_re_proposed():
    """Un par previamente rechazado no se vuelve a proponer (INV-M1-4)."""
    reg = _registry("Ana")
    cand = _candidate("Annie")
    cid_a = "ms::ana"
    cid_b = "ms::annie"
    pair = (cid_a, cid_b) if cid_a < cid_b else (cid_b, cid_a)
    prior = {pair: "rejected"}
    result = resolve_candidate(cand, reg, llm_client=_fake_llm(True, 0.8), prior_decisions=prior)
    assert result.merge_candidate is None


# ── Evidencia bajo demanda (citas previas de A) ──────────────────────────────


def test_evidence_fn_called_only_for_llm_judgement():
    """evidence_fn se invoca solo cuando hay pregunta al LLM, con el canonical de A."""
    calls = []

    def fake_evidence(canonical):
        calls.append(canonical)
        return ["Cita previa de la entidad A."]

    reg = EntityRegistry()
    reg.add("Fitzwilliam Darcy", [], "protagonist")
    client = _fake_llm(False, 0.2)
    resolve_candidate(
        _candidate("Georgiana Darcy"), reg,
        llm_client=client, scene_text="escena", evidence_fn=fake_evidence,
    )
    assert calls == ["Fitzwilliam Darcy"]
    user_arg = client.complete_structured.call_args[0][1]
    assert "Cita previa de la entidad A." in user_arg


def test_evidence_fn_not_called_on_deterministic_merge():
    """Match exacto (nivel 1) no paga el coste de evidencia."""
    calls = []
    reg = _registry("Elizabeth Bennet")
    resolve_candidate(
        _candidate("Elizabeth Bennet"), reg,
        llm_client=_fake_llm(True, 0.9), evidence_fn=lambda c: calls.append(c) or [],
    )
    assert calls == []


# ── Nivel 2 honorific-aware (cierra el agujero que b05b1f5 dejó abierto) ─────


def test_incompatible_honorifics_never_merge_even_with_confident_llm():
    """El agujero real: nivel 1 separaba Mr./Mrs. Bennet pero nivel 2 los re-fusionaba.

    Con un LLM que responde same_entity=True al 0.95, honoríficos incompatibles
    NO deben fusionarse NI encolarse: son personas distintas por definición.
    """
    reg = _registry("Mr. Bennet")
    result = resolve_candidate(
        _candidate("Mrs. Bennet"), reg, llm_client=_fake_llm(True, 0.95)
    )
    assert result.merged_into is None
    assert result.merge_candidate is None


def test_miss_vs_mr_same_surname_never_merge():
    reg = _registry("Mr. Darcy")
    result = resolve_candidate(
        _candidate("Miss Darcy"), reg, llm_client=_fake_llm(True, 0.95)
    )
    assert result.merged_into is None
    assert result.merge_candidate is None


def test_same_surname_different_given_name_queues_not_merges():
    """Georgiana Darcy vs Fitzwilliam Darcy: apellido igual, pila distinta →
    aunque el LLM diga 0.95, como máximo cola humana, jamás auto-merge."""
    reg = _registry("Fitzwilliam Darcy")
    result = resolve_candidate(
        _candidate("Georgiana Darcy"), reg, llm_client=_fake_llm(True, 0.95)
    )
    assert result.merged_into is None
    assert isinstance(result.merge_candidate, MergeCandidateProposal)


# ── Over-merge honorífico vía alias desnudo (bug descubierto en Task 4) ────────


def test_lookup_miss_does_not_match_mr_with_bare_alias():
    """'Miss Darcy' NO debe resolver a 'Mr. Darcy' en nivel 1 aunque exista el
    alias desnudo 'Darcy' (son hermanos: Georgiana vs Fitzwilliam)."""
    reg = EntityRegistry()
    reg.add("Mr. Darcy", ["Darcy"], "protagonist")
    assert reg.find("Miss Darcy") is None
    # las formas legítimas siguen resolviendo
    assert reg.find("Mr. Darcy").canonical_name == "Mr. Darcy"
    assert reg.find("Darcy").canonical_name == "Mr. Darcy"


def test_miss_darcy_not_merged_into_mr_darcy_at_level1():
    """Sin LLM, el candidato con alias 'Miss Darcy' no se fusiona en nivel 1."""
    reg = EntityRegistry()
    reg.add("Mr. Darcy", ["Darcy"], "protagonist")
    result = resolve_candidate(
        _candidate("Georgiana Darcy", aliases=["Miss Darcy"]), reg, llm_client=None
    )
    assert result.merged_into is None


def test_given_name_plus_shared_surname_queues_not_auto_merges():
    """'Georgiana Darcy' vs el apellido desnudo de 'Mr. Darcy': aunque el LLM
    diga same=0.95, como máximo cola humana — jamás auto-merge silencioso (SC-003)."""
    reg = EntityRegistry()
    reg.add("Mr. Darcy", ["Darcy"], "protagonist")
    result = resolve_candidate(
        _candidate("Georgiana Darcy"),
        reg,
        llm_client=_fake_llm(True, 0.95),
        scene_text="Georgiana greeted them at Pemberley.",
    )
    assert result.merged_into is None
    assert isinstance(result.merge_candidate, MergeCandidateProposal)


# ── Prompt de merge lleva contexto evidencial (no pregunta a ciegas) ─────────


def test_merge_llm_receives_context():
    """El prompt de merge lleva aliases, roles y fragmento de escena.

    Nota: sin alias "Darcy" en el registro para no chocar con el bug latente
    (fuera de alcance de esta tarea) de `registry._lookup`, donde un alias
    honorífico entrante ("Miss Darcy") empareja de forma determinista (nivel 1)
    contra un alias sin honorífico ya registrado, sin comprobar compatibilidad
    de honoríficos — eso saltaría el nivel 2 (LLM) que este test verifica.
    """
    reg = EntityRegistry()
    reg.add("Fitzwilliam Darcy", [], "protagonist")
    client = _fake_llm(False, 0.2)
    resolve_candidate(
        _candidate("Georgiana Darcy", aliases=["Miss Darcy"]),
        reg,
        llm_client=client,
        scene_text="Georgiana, his sister, was at Pemberley.",
    )
    system_arg, user_arg = client.complete_structured.call_args[0][:2]
    assert "Pemberley" in user_arg
    assert "Miss Darcy" in user_arg
    assert "extracción" not in system_arg.lower()  # no reutiliza el prompt de extracción
