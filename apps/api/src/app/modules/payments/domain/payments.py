"""What a payment means, whichever gateway took it (ARCHITECTURE §9; step 6.1, ADR 0056). Pure:
no HTTP, no database and no clock.

A payment is one order at the gateway, which may see several attempts before one goes through.
Only what the gateway itself says about a payment moves anything, and only forward (§7.4): a slow
or repeated answer never takes a payment back.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

# The gateways there are.
type Provider = Literal["razorpay", "fake"]
# Every amount is in Indian rupees, as integer paise (rule 12).
INR: Final = "INR"


class PaymentPurpose(StrEnum):
    TOKEN = "token"  # noqa: S105 - a booking's token, not a password


class PaymentMode(StrEnum):
    PAYMENT = "payment"


class PaymentStatus(StrEnum):
    """Our payment: an order waiting to be paid, the bank's yes, and the money in."""

    CREATED = "created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"


class GatewayStatus(StrEnum):
    """A payment as the gateway reports it, in Razorpay's words."""

    CREATED = "created"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    REFUNDED = "refunded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class GatewayOrder:
    id: str
    amount_paise: int
    currency: str


@dataclass(frozen=True, slots=True)
class GatewayPayment:
    id: str
    order_id: str | None
    amount_paise: int
    currency: str
    status: GatewayStatus


class Reading(StrEnum):
    """What a gateway's payment means for ours."""

    PAID = "paid"
    WAITING = "waiting"
    NOT_PAID = "not_paid"
    # Not this order's payment, or not its amount: it moves nothing, and someone has to look.
    MISMATCH = "mismatch"


def read_payment(found: GatewayPayment, *, order_id: str, amount_paise: int) -> Reading:
    """What ``found`` says about our order for exactly ``amount_paise``."""
    if found.order_id != order_id or found.amount_paise != amount_paise or found.currency != INR:
        return Reading.MISMATCH
    match found.status:
        case GatewayStatus.CAPTURED:
            return Reading.PAID
        case GatewayStatus.CREATED | GatewayStatus.AUTHORIZED:
            return Reading.WAITING
        case GatewayStatus.REFUNDED | GatewayStatus.FAILED:
            return Reading.NOT_PAID


_ORDER: Final = (PaymentStatus.CREATED, PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED)
_REACHES: Final = {
    GatewayStatus.AUTHORIZED: PaymentStatus.AUTHORIZED,
    GatewayStatus.CAPTURED: PaymentStatus.CAPTURED,
}


def advanced(status: PaymentStatus, seen: GatewayStatus) -> PaymentStatus:
    """Our status after the gateway says ``seen``: further along, or as it was."""
    reached = _REACHES.get(seen, PaymentStatus.CREATED)
    return max(status, reached, key=_ORDER.index)


def token_key(provider: str, code: str) -> str:
    """A booking has one token payment at each gateway, so asking again finds the same order."""
    return f"token:{provider}:{code}"


def token_receipt(code: str) -> str:
    """The order's receipt: unique per booking, and at most 40 ASCII characters, as Razorpay asks
    (a booking code is 11). Asking twice can never make two orders for one booking."""
    return f"token-{code}"
