"""The compliance module's routes: data requests and grievances."""

from fastapi import APIRouter

from app.modules.compliance.router.data_requests import router as data_requests_router
from app.modules.compliance.router.grievances import router as grievances_router

router = APIRouter()
router.include_router(data_requests_router)
router.include_router(grievances_router)
