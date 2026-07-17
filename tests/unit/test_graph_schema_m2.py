"""El delta de esquema M2 está declarado en SCHEMA_STATEMENTS (idempotente)."""

from __future__ import annotations

import pytest

from backend.graph.schema import SCHEMA_STATEMENTS

pytestmark = pytest.mark.unit


def test_m2_constraint_declared() -> None:
    assert any(
        "relation_evidence_id_unique" in s and "IF NOT EXISTS" in s
        for s in SCHEMA_STATEMENTS
    )


def test_m2_indexes_declared() -> None:
    assert any("relation_evidence_by_manuscript" in s for s in SCHEMA_STATEMENTS)
    assert any("relation_evidence_by_scene" in s for s in SCHEMA_STATEMENTS)
