"""Pricing's routes (ARCHITECTURE §15): the policies in force, admins' changes to them and to
rent bands, PGs' rule sets and ops' editor for them, quotes and the price calendar."""

from fastapi import APIRouter

from app.modules.pricing.router.editor import router as editor_router
from app.modules.pricing.router.policies import router as policies_router
from app.modules.pricing.router.quotes import router as quotes_router
from app.modules.pricing.router.rule_sets import router as rule_sets_router

router = APIRouter()
router.include_router(policies_router)
router.include_router(quotes_router)
router.include_router(rule_sets_router)
router.include_router(editor_router)
