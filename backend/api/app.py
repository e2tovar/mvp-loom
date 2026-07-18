"""App FastAPI de Loom (M0 + M1).

En el arranque aplica el esquema del grafo de forma idempotente. La aplicación del
esquema es resiliente: si Neo4j no está disponible se registra un aviso y la app
arranca igual (útil para tests de contrato que no tocan la base de datos).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.api.routes_characters import router as characters_router
from backend.api.routes_manuscripts import router as manuscripts_router
from backend.api.routes_relations import router as relations_router
from backend.graph import client, schema

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("loom")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        with client.session() as sess:
            schema.apply_schema(sess)
        logger.info("Esquema del grafo aplicado correctamente")
    except Exception as exc:  # noqa: BLE001 - arranque resiliente
        logger.warning("No se pudo aplicar el esquema del grafo: %s", exc)
    yield
    client.close_driver()


app = FastAPI(
    title="Loom — M0+M1 Ingestión, segmentación y extracción de personajes",
    lifespan=lifespan,
)
app.include_router(manuscripts_router)
app.include_router(characters_router)
app.include_router(relations_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
