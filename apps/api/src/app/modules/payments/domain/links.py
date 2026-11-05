"""Payment links: how an owner pays what's left of an invoice (ARCHITECTURE §9.5; step 6.5, ADR
0061). Pure.

A link is made by a job for exactly the invoice's balance, and only the gateway's word that it was
paid, for exactly that, marks the invoice paid. A link that expires or is cancelled can't be paid,
and an expired one is replaced.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from app.modules.payments.domain.payments import INR, GatewayStatus

if TYPE_CHECKING:
    import uuid

    from app.modules.payments.domain.payments import GatewayPayment

# Razorpay's smallest link: ₹1.
MIN_LINK_PAISE: Final = 100
_REFERENCE_PREFIX: Final = "inv-"
LINK_EVENTS: Final = frozenset(
    {"payment_link.paid", "payment_link.expired", "payment_link.cancelled"}
)


class LinkStatus(StrEnum):
    CREATED = "created"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


ENDED: Final = frozenset({LinkStatus.EXPIRED, LinkStatus.CANCELLED})


@dataclass(frozen=True, slots=True)
class GatewayLink:
    id: str
    # Ours, unique to the link: asking for it again finds the same one.
    reference: str | None
    amount_paise: int
    amount_paid_paise: int
    status: LinkStatus
    url: str
    # The payment that paid it, once one has.
    payment_id: str | None = None


def link_reference(payment_id: uuid.UUID) -> str:
    """Razorpay allows 40 characters; this is 36."""
    return f"{_REFERENCE_PREFIX}{payment_id.hex}"


class LinkReading(StrEnum):
    """What the gateway's word about a link comes to."""

    PAID = "paid"
    # It says paid, but not for exactly what was asked, in rupees, captured: someone must look.
    MISMATCH = "mismatch"
    ENDED = "ended"
    NOTHING_YET = "nothing_yet"


def read_link(
    link: GatewayLink, payment: GatewayPayment | None, *, amount_paise: int
) -> LinkReading:
    if link.status in ENDED:
        return LinkReading.ENDED
    if link.status is not LinkStatus.PAID:
        return LinkReading.NOTHING_YET
    if (
        payment is None
        or link.amount_paid_paise != amount_paise
        or payment.amount_paise != amount_paise
        or payment.currency != INR
        or payment.status is not GatewayStatus.CAPTURED
    ):
        return LinkReading.MISMATCH
    return LinkReading.PAID
