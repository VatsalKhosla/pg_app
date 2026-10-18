"""Probe endpoints: public, outside /v1, and excluded from tracing and info-level access logs."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.modules.system.schemas import Health, Readiness
from app.modules.system.service import ReadinessService

router = APIRouter(tags=["system"])


def get_readiness_service(request: Request) -> ReadinessService:
    return ReadinessService(engine=request.app.state.engine, redis=request.app.state.redis)


@router.get("/healthz", summary="Liveness: the process is up")
async def healthz() -> Health:
    return Health(status="ok")


@router.get(
    "/readyz",
    summary="Readiness: the database and Redis are reachable",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": Readiness,
            "description": "A dependency is unavailable",
        }
    },
)
async def readyz(
    response: Response,
    service: Annotated[ReadinessService, Depends(get_readiness_service)],
) -> Readiness:
    readiness = await service.check()
    if readiness.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return readiness
