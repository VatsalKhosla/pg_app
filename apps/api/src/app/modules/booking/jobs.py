"""The booking module's job handlers (steps 5.4 to 5.8, ADRs 0048 and 0052), registered in
app/jobs.py with the texts sender they use.

The scheduled ones (§7.5) each move a batch of due bookings through the state machine, so a
second run straight after changes nothing. Each says how many it moved, in the log and in the
``booking.job.changes`` metric; the outbox measures their runs, failures and lag.
"""

import uuid
from typing import TYPE_CHECKING, Final

import structlog
from opentelemetry import metrics

from app.modules.booking.domain.state_machine import BookingEvent, BookingStatus, Party
from app.modules.booking.service import NOTIFY, BookingNotices, BookingSystem

if TYPE_CHECKING:
    from app.core.outbox import JobContext, JobHandler, JobPayload
    from app.core.texts import Texts

__all__ = [
    "CHECK_WINDOWS",
    "CONFIRMATION_TIMEOUTS",
    "EXPIRE_HOLDS",
    "NOTIFY",
    "NO_SHOWS",
    "expire_holds",
    "mark_no_shows",
    "notify_handler",
    "settle_check_windows",
    "time_out_confirmations",
]

# §7.5: every minute, holds whose time is up end...
EXPIRE_HOLDS: Final = "booking.expire_holds"
# ...every five minutes, the bookings whose owners didn't confirm in time are rejected...
CONFIRMATION_TIMEOUTS: Final = "booking.confirmation_timeouts"
# ...and the ones whose 24 hours to check the room are over are settled...
CHECK_WINDOWS: Final = "booking.check_windows"
# ...and every morning, confirmed bookings whose student never moved in end.
NO_SHOWS: Final = "booking.no_shows"

logger = structlog.stdlib.get_logger(__name__)
_changes = metrics.get_meter("app.booking").create_counter(
    "booking.job.changes", unit="{booking}", description="Bookings a scheduled job moved"
)


def _moved(job: str, count: int, message: str) -> None:
    _changes.add(count, {"job": job})
    if count:
        logger.info(message, count=count)


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


async def expire_holds(context: JobContext, _payload: JobPayload) -> None:
    expired = await BookingSystem(context.session, context.clock).expire_holds()
    _moved(EXPIRE_HOLDS, expired, "holds whose time was up ended")


async def time_out_confirmations(context: JobContext, _payload: JobPayload) -> None:
    rejected = await BookingSystem(context.session, context.clock).time_out_confirmations()
    _moved(CONFIRMATION_TIMEOUTS, rejected, "bookings not confirmed in time were rejected")


async def settle_check_windows(context: JobContext, _payload: JobPayload) -> None:
    settled = await BookingSystem(context.session, context.clock).settle_check_windows()
    _moved(CHECK_WINDOWS, settled, "bookings whose check window ended were settled")


async def mark_no_shows(context: JobContext, _payload: JobPayload) -> None:
    ended = await BookingSystem(context.session, context.clock).mark_no_shows()
    _moved(NO_SHOWS, ended, "bookings whose student never moved in ended")
