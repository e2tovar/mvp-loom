"""Fixtures compartidas de los tests de M0."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "eval" / "fixtures"

_LABELS = ("Manuscript", "Chapter", "Scene", "NonNarrativeBlock")


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


def _neo4j_available() -> bool:
    try:
        from backend.graph import client

        driver = client.get_driver()
        driver.verify_connectivity()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture
def neo4j_session() -> Iterator[object]:
    """Sesión Neo4j con esquema aplicado y base limpia. Skip si Neo4j no está arriba."""
    if not _neo4j_available():
        pytest.skip("Neo4j no disponible (docker compose up para tests de integración)")

    from backend.graph import client, schema

    with client.session() as sess:
        schema.apply_schema(sess)
        for label in _LABELS:
            sess.run(f"MATCH (n:{label}) DETACH DELETE n")
        yield sess


@pytest.fixture
def api_client() -> Iterator[object]:
    """TestClient de FastAPI.

    No se entra como context manager a propósito: así no se ejecuta el lifespan (que
    cerraría el driver Neo4j compartido entre tests). El esquema lo aplica la fixture
    `neo4j_session` en los tests de integración; los tests de contrato de error no
    tocan la base de datos.
    """
    from fastapi.testclient import TestClient

    from backend.api.app import app

    os.environ.setdefault("NEO4J_PASSWORD", "loom-dev-password")
    yield TestClient(app)
