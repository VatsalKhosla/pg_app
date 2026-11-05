"""What a gateway's webhook says (ARCHITECTURE §9.3; step 6.2, ADR 0057). Pure.

Webhooks arrive at least once and in any order. A signature proves who sent one, but a body can be
sent again, so an event's age is checked too, and what it says only ever moves a payment forward.

Only what the rules need is kept. A gateway's own copy of a payment holds the student's phone,
email, UPI id and card details, and none of that is ours to keep twice.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Final, cast

from app.modules.payments.domain.payments import GatewayPayment, GatewayStatus

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

# Razorpay retries for 24 hours after an event is created, so anything much older is a replay.
WEBHOOK_MAX_AGE: Final = timedelta(hours=48)
# What's acted on. Any other event is kept and ignored. Refund events join these in step 6.3.
PAYMENT_EVENTS: Final = frozenset(
    {"payment.authorized", "payment.captured", "payment.failed", "order.paid"}
)


@dataclass(frozen=True, slots=True)
class GatewayEvent:
    kind: str
    created_at: datetime
    # The payment it's about, if it's one acted on and could be read.
    payment: GatewayPayment | None
    # Whether it should have held a payment, but its didn't make sense: someone has to look.
    unreadable: bool = False


def too_old(event: GatewayEvent, now: datetime) -> bool:
    return now - event.created_at > WEBHOOK_MAX_AGE


def kept_payload(event: GatewayEvent) -> dict[str, object]:
    """All that's stored of an event."""
    payment = event.payment
    return {
        "createdAt": event.created_at.isoformat(),
        **({"unreadable": True} if event.unreadable else {}),
        **(
            {}
            if payment is None
            else {
                "payment": {
                    "id": payment.id,
                    "orderId": payment.order_id,
                    "amountPaise": payment.amount_paise,
                    "currency": payment.currency,
                    "status": payment.status,
                }
            }
        ),
    }


def payment_in(payload: Mapping[str, object]) -> GatewayPayment | None:
    """The payment a stored event is about, if any."""
    found = payload.get("payment")
    if found is None:
        return None
    stored = cast("Mapping[str, object]", found)
    return GatewayPayment(
        id=str(stored["id"]),
        order_id=None if stored["orderId"] is None else str(stored["orderId"]),
        amount_paise=int(str(stored["amountPaise"])),
        currency=str(stored["currency"]),
        status=GatewayStatus(str(stored["status"])),
    )
