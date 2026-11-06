"""UPI one-time mandates: a token blocked in the student's own bank account, not taken
(PRODUCT_CONTEXT §3 "Block, don't take"; ARCHITECTURE §9.2; step 6.7, ADR 0064). Pure.

The student authorises a block of exactly the token. Nothing moves until the booking settles, after
move-in and its 24 hours to check the room (rule 8): then the token is debited, once, after the
notice the rules ask for. A booking that ends before that gives the block back, all of it, or the
part the late-cancel rule doesn't keep. A mandate has to last until the debit, so a move-in too far
off is taken as a normal payment instead.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Final

from app.core.calendar import india_start

# NPCI asks for a day's notice before a mandate is debited, and Razorpay debits 25 hours after it
# sends one: an hour more, so the debit never comes before its time.
PRE_DEBIT_NOTICE: Final = timedelta(hours=26)
# Room for a job that runs late, or a debit that has to be tried again.
EXPIRY_MARGIN: Final = timedelta(days=1)
MANDATE_EVENTS: Final = frozenset(
    {"token.confirmed", "token.rejected", "token.cancelled", "token.paused"}
)


class TokenMode(StrEnum):
    """How a token is taken (the ``token_mode`` flag)."""

    PAYMENT = "payment"
    UPI_MANDATE = "upi_mandate"


class MandateStatus(StrEnum):
    """A mandate as the gateway reports it, in Razorpay's words for its token."""

    INITIATED = "initiated"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass(frozen=True, slots=True)
class GatewayMandate:
    id: str
    status: MandateStatus
    customer_id: str | None = None


@dataclass(frozen=True, slots=True)
class MandateOrder:
    """The order a student authorises a block on, and the gateway's record of them."""

    order_id: str
    customer_id: str
    amount_paise: int


@dataclass(frozen=True, slots=True)
class MandatePayer:
    """Who a mandate is from, as the gateway needs them to authorise and to debit it."""

    name: str | None
    contact: str


def mandate_expiry(move_in: date, *, no_show_days: int, check_window_hours: int) -> datetime:
    """When the mandate may lapse: after the last day the student may still move in, their hours to
    check the room, the debit's notice, and a margin."""
    last_day_ends = india_start(move_in + timedelta(days=no_show_days + 1))
    return last_day_ends + timedelta(hours=check_window_hours) + PRE_DEBIT_NOTICE + EXPIRY_MARGIN


def mandate_fits(now: datetime, expires_at: datetime, *, max_days: int) -> bool:
    """Whether a mandate lasting until ``expires_at`` is one banks will take: no longer than
    ``max_days`` from now."""
    return now < expires_at <= now + timedelta(days=max_days)


def kept_on_release(token_paise: int, refund_paise: int) -> int:
    """What a booking that ends keeps of a blocked token, to debit: the token less what goes back.
    Nothing, and the whole block is released, when all of it goes back."""
    return max(0, token_paise - max(0, refund_paise))
