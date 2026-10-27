"""The catalog's routes (ARCHITECTURE §15): listings, the visits that verify them, and owners
with their agreement."""

from fastapi import APIRouter

from app.modules.catalog.router.listings import router as listings_router
from app.modules.catalog.router.owners import router as owners_router
from app.modules.catalog.router.verification import router as verification_router

router = APIRouter()
router.include_router(listings_router)
router.include_router(verification_router)
router.include_router(owners_router)
