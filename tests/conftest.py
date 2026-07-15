"""Fixtures compartidas de los tests de M0.

AISLAMIENTO DE LA BASE (crítico): Neo4j Community solo expone una base (`neo4j`),
compartida entre los tests y los datos reales de desarrollo. Por eso la limpieza
del harness NUNCA borra de forma global: solo toca manuscritos de test
(`test-*` sintéticos + las fixtures crafted que ingieren los tests). Cualquier
obra real (pride-and-prejudice, demos) queda intacta.
Ver docs/known-issues.md → "Follow-ups tras bugfixes + demo HP1", punto 1.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "eval" / "fixtures"

# Prefijo de los manuscript_id sintéticos que crean los tests (write_raw_layer).
_TEST_ID_PREFIX = "test-"

# Fixtures crafted que los tests de integración ingieren vía la API. Sus
# manuscript_id son hashes del contenido: se derivan con el mismo pipeline
# productivo para no hardcodear el hash ni duplicar la lógica de identidad.
_CRAFTED_FIXTURES = (
    ("crafted-three-chapters.txt", "txt"),
    ("crafted-two-chapters.epub", "epub"),
)


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


@lru_cache(maxsize=1)
def _crafted_manuscript_ids() -> tuple[str, ...]:
    """manuscript_id de las fixtures crafted, derivados del pipeline de ingesta.

    Puro (no toca la base). Si alguna fixture no puede parsearse, se omite de la
    limpieza en lugar de caer en un borrado sin scope.
    """
    from backend.ingest.pipeline import parse_manuscript

    ids: list[str] = []
    for name, fmt in _CRAFTED_FIXTURES:
        try:
            ids.append(parse_manuscript(FIXTURES_DIR / name, fmt).manuscript_id)
        except Exception:  # noqa: BLE001
            pass
    return tuple(ids)


def _wipe_manuscripts(sess: object, manuscript_ids: list[str]) -> None:
    """Borra los nodos de los manuscritos dados, scoped por manuscript_id.

    Guard anti-regresión: el borrado SIEMPRE está acotado a la lista de ids. No
    existe ruta para un `DETACH DELETE` global; una lista vacía es un no-op.
    """
    if not manuscript_ids:
        return
    sess.run(  # type: ignore[attr-defined]
        "MATCH (n) WHERE n.manuscript_id IN $ids DETACH DELETE n",
        ids=list(manuscript_ids),
    )


@pytest.fixture
def neo4j_session() -> Iterator[object]:
    """Sesión Neo4j con esquema aplicado y datos de test limpios.

    Solo limpia manuscritos de test (nunca datos reales). Skip si Neo4j no está.
    """
    if not _neo4j_available():
        pytest.skip("Neo4j no disponible (docker compose up para tests de integración)")

    from backend.graph import client, schema

    with client.session() as sess:
        schema.apply_schema(sess)
        # Manuscritos sintéticos (test-*): borrado scoped por prefijo.
        sess.run(
            "MATCH (n) WHERE n.manuscript_id STARTS WITH $prefix DETACH DELETE n",
            prefix=_TEST_ID_PREFIX,
        )
        # Fixtures crafted ingeridas por los tests: borrado scoped por id exacto.
        _wipe_manuscripts(sess, list(_crafted_manuscript_ids()))
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
