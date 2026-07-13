"""Cliente Neo4j (conexión desde entorno, sesiones).

Lee la configuración del archivo .env y de las variables de entorno
(.env.example): NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE
(opcional). Las variables ya presentes en el entorno tienen prioridad
sobre el .env.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from dotenv import load_dotenv

from neo4j import Driver, GraphDatabase, Session

load_dotenv()


def _settings() -> tuple[str, str, str]:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:17687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "loom-dev-password")
    return uri, user, password


def _default_database() -> str | None:
    """Base de datos por defecto; None delega en el default del servidor."""
    return os.environ.get("NEO4J_DATABASE") or None


@lru_cache(maxsize=1)
def get_driver() -> Driver:
    """Devuelve un Driver singleton (thread-safe, reusable)."""
    uri, user, password = _settings()
    return GraphDatabase.driver(uri, auth=(user, password))


@contextmanager
def session(database: str | None = None) -> Iterator[Session]:
    """Context manager para una sesión Neo4j.

    `database` permite apuntar a una base específica; si se omite, usa
    NEO4J_DATABASE (o el default del servidor si tampoco está definida).
    """
    drv = get_driver()
    db = database or _default_database()
    sess = drv.session(database=db) if db else drv.session()
    try:
        yield sess
    finally:
        sess.close()


def close_driver() -> None:
    """Cierra el driver singleton (usar en shutdown)."""
    if get_driver.cache_info().currsize:
        get_driver().close()
        get_driver.cache_clear()
