"""What a refund is, and how much of a payment can go back (ARCHITECTURE §9; step 6.3, ADR 0059).
Pure.

A refund only moves forward. A gateway's answer can come late or twice, and whichever way it comes
a refund that's done stays done. Money already on its way back can't go back twice, so anything but
a failed or declined refund counts against the payment.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable

_RECEIPT_PREFIX: Final = "refund-"


class RefundKind(StrEnum):
    # A booking's change gave money back, or a token came in after its booking had moved on.
    AUTOMATIC = "automatic"
    # Ops, with a reason.
    MANUAL = "manual"
    # It happened at the gateway without us: its own refund of a payment nobody captured, say.
    GATEWAY = "gateway"


class RefundStatus(StrEnum):
    # Ops' refund above the threshold, waiting for a second person.
    AWAITING_APPROVAL = "awaiting_approval"
    # Ours, on its way to the gateway.
    REQUESTED = "requested"
    # The gateway has it.
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"
    # The second person said no.
    DECLINED = "declined"


class GatewayRefundStatus(StrEnum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class GatewayRefund:
    id: str
    payment_id: str
    amount_paise: int
    status: GatewayRefundStatus
    receipt: str | None = None
    # What a student can quote to their bank, when there is one.
    reference: str | None = None


# None of these takes money back.
_NO_MONEY: Final = frozenset({RefundStatus.FAILED, RefundStatus.DECLINED})
_ORDER: Final = (
    RefundStatus.REQUESTED,
    RefundStatus.PENDING,
    RefundStatus.FAILED,
    RefundStatus.PROCESSED,
)
_REACHES: Final = {
    GatewayRefundStatus.PENDING: RefundStatus.PENDING,
    GatewayRefundStatus.PROCESSED: RefundStatus.PROCESSED,
    GatewayRefundStatus.FAILED: RefundStatus.FAILED,
}


def from_gateway(seen: GatewayRefundStatus) -> RefundStatus:
    return _REACHES[seen]


def refund_progress(status: RefundStatus, seen: GatewayRefundStatus) -> RefundStatus:
    """Our status after the gateway says ``seen``: further along, or as it was. A gateway has no
    say over a refund that never reached it."""
    if status not in _ORDER:
        return status
    return max(status, _REACHES[seen], key=_ORDER.index)


def refundable(amount_paise: int, refunds: Iterable[tuple[int, RefundStatus]]) -> int:
    """What can still go back of a payment of ``amount_paise``."""
    taken = sum(amount for amount, status in refunds if status not in _NO_MONEY)
    return max(0, amount_paise - taken)


def needs_second_person(amount_paise: int, above_paise: int) -> bool:
    return amount_paise > above_paise


def refund_receipt(public_id: uuid.UUID) -> str:
    """Unique to the refund, so a lost answer can't refund twice, and at most 40 characters."""
    return f"{_RECEIPT_PREFIX}{public_id.hex}"


def refund_of_receipt(receipt: str | None) -> uuid.UUID | None:
    """The refund a receipt is ours for, if it's one of ours."""
    if receipt is None or not receipt.startswith(_RECEIPT_PREFIX):
        return None
    try:
        return uuid.UUID(hex=receipt.removeprefix(_RECEIPT_PREFIX))
    except ValueError:
        return None
