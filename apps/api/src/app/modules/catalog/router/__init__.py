"""The catalog's routes (ARCHITECTURE §15): listings, and the visits that verify them."""

from fastapi import APIRouter

from app.modules.catalog.router.listings import router as listings_router
from app.modules.catalog.router.verification import router as verification_router

router = APIRouter()
router.include_router(listings_router)
router.include_router(verification_router)
