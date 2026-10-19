"""The retention schedule (DPDP: keep personal data no longer than needed): rules from each module,
run by one daily job, each run recorded in the audit log. app/jobs.py lists the rules, so the
whole schedule reads in one place.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.core import audit

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock

logger = structlog.stdlib.get_logger(__name__)


@dataclass(frozen=True)
class RetentionRule:
    name: str
    # What is deleted, and when, in words: the schedule as a person reads it.
    schedule: str
    # Delete what is past its time; returns how many records went.
    purge: Callable[[AsyncSession, Clock], Awaitable[int]]


async def run_retention(
    session: AsyncSession, clock: Clock, rules: Sequence[RetentionRule]
) -> dict[str, int]:
    """Apply every rule in the job's transaction, and record what each removed."""
    removed = {rule.name: await rule.purge(session, clock) for rule in rules}
    logger.info("retention ran", **removed)
    await audit.record(
        session,
        clock=clock,
        actor=audit.SYSTEM,
        action="retention.ran",
        entity_type="retention",
        entity_id=clock.now().date().isoformat(),
        details=removed,
    )
    return removed
