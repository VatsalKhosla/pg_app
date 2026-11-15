"""The agreements module's job handlers (ADR 0070), registered in app/jobs.py.

The booking module announces a booking's confirmation and its end through the outbox; the rent
agreement follows each: made once the booking is confirmed, voided if it ends early before both
sides have signed. One handler serves both, as it brings the agreement in step with the booking
as it is now, so neither the order the jobs run in nor a second run changes the outcome.
"""

import uuid
from typing import TYPE_CHECKING

from app.modules.agreements.service import RentAgreements
from app.modules.booking.service import CONFIRMED, ENDED

if TYPE_CHECKING:
    from app.core.outbox import JobContext, JobHandler, JobPayload
    from app.modules.agreements.templates import Templates

__all__ = ["CONFIRMED", "ENDED", "follow_booking_handler"]


def follow_booking_handler(templates: Templates) -> JobHandler:
    async def handle(context: JobContext, payload: JobPayload) -> None:
        await RentAgreements(context.session, context.clock, templates=templates).sync(
            uuid.UUID(str(payload["booking"]))
        )

    return handle
