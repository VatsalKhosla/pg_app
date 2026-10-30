"""The pricing module's job handlers (app/jobs.py registers them, and the nightly schedule)."""

from typing import TYPE_CHECKING, Final

import structlog

from app.modules.pricing.service import AlertChecks

if TYPE_CHECKING:
    from app.core.outbox import JobContext, JobPayload

# Nightly: the market and last week's clamps, for pricing's integrity alerts (ADR 0043).
CHECK_INTEGRITY: Final = "pricing.check_integrity"

logger = structlog.stdlib.get_logger(__name__)


async def check_integrity_handler(context: JobContext, _payload: JobPayload) -> None:
    checks = AlertChecks(context.session, context.clock)
    below = await checks.market()
    clamped = await checks.clamps()
    logger.info("pricing integrity checked", below_market=below, clamps_frequent=clamped)
