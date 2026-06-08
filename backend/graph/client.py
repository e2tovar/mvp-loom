"""Cliente Neo4j (conexión desde entorno, sesiones).

Lee la configuración de las variables de entorno (.env.example):
NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from neo4j import Driver, GraphDatabase, Session


def _settings() -> tuple[str, str, str]:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "loom-dev-password")
    return uri, user, password


@lru_cache(maxsize=1)
def get_driver() -> Driver:
    """Devuelve un Driver singleton (thread-safe, reusable)."""
    uri, user, password = _settings()
    return GraphDatabase.driver(uri, auth=(user, password))


@contextmanager
def session() -> Iterator[Session]:
    """Context manager para una sesión Neo4j."""
    drv = get_driver()
    sess = drv.session()
    try:
        yield sess
    finally:
        sess.close()


def close_driver() -> None:
    """Cierra el driver singleton (usar en shutdown)."""
    if get_driver.cache_info().currsize:
        get_driver().close()
        get_driver.cache_clear()
