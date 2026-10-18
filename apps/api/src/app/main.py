"""HTTP API entrypoint: ``uvicorn app.main:create_app --factory``.

Step 0.3 grows this into the full app factory (settings, logging, errors, readiness, middleware).
"""

from importlib.metadata import version
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict


class Health(BaseModel):
    """Liveness: the process is up and serving requests."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]


def create_app() -> FastAPI:
    app = FastAPI(title="PG platform API", version=version("pg-platform-api"))

    @app.get("/healthz", tags=["health"], summary="Liveness check")
    async def healthz() -> Health:
        return Health(status="ok")

    return app
