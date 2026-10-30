"""The booking module's job handlers (step 5.4, ADR 0048), registered in app/jobs.py with the
texts sender they use."""

import uuid
from typing import TYPE_CHECKING, Final

import structlog

from app.modules.booking.domain.state_machine import BookingEvent, BookingStatus, Party
from app.modules.booking.service import NOTIFY, BookingNotices, BookingSystem

if TYPE_CHECKING:
    from app.core.outbox import JobContext, JobHandler, JobPayload
    from app.core.texts import Texts

__all__ = ["CONFIRMATION_TIMEOUTS", "NOTIFY", "notify_handler", "time_out_confirmations"]

# §7.5: every five minutes, the bookings whose owners didn't confirm in time are rejected.
CONFIRMATION_TIMEOUTS: Final = "booking.confirmation_timeouts"

logger = structlog.stdlib.get_logger(__name__)


def notify_handler(texts: Texts) -> JobHandler:
    """A text about a booking, unless it has moved on since, or that party gets none for that
    change (ops see theirs on the bookings board)."""

    async def handle(context: JobContext, payload: JobPayload) -> None:
        event, who = BookingEvent(str(payload["event"])), Party(str(payload["who"]))
        found = await BookingNotices(context.session).message(
            uuid.UUID(str(payload["booking"])),
            event,
            who,
            BookingStatus(str(payload["status"])),
            instant=payload.get("instant") is True,
        )
        if found is None:
            logger.info("no booking text to send", booking_event=event, to=who)
            return
        phone, template, values = found
        await texts.send(phone, template, values)

    return handle


async def time_out_confirmations(context: JobContext, _payload: JobPayload) -> None:
    rejected = await BookingSystem(context.session, context.clock).time_out_confirmations()
    if rejected:
        logger.info("bookings not confirmed in time were rejected", count=rejected)
