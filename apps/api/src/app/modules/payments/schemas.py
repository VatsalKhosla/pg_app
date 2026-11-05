"""What the payments API takes and gives (step 6.1, ADR 0056). The browser never says how much:
the amount is the booking's, fixed by its quote (rule 12's server-side money)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Final

from pydantic import Field

from app.core.schemas import ApiModel
from app.modules.payments.domain.payments import PaymentStatus, Provider
from app.modules.payments.domain.refunds import RefundKind, RefundStatus

GATEWAY_ID_MAX_LENGTH: Final = 64
_GATEWAY_PAYMENT_ID: Final = r"^pay_[A-Za-z0-9_]+$"
_SIGNATURE: Final = r"^[0-9a-f]{64}$"
REASON_MAX_LENGTH: Final = 500


class CheckoutOutcome(StrEnum):
    """What the gateway's answer meant for the student's booking."""

    PAID = "paid"
    # The bank hasn't finished, or the gateway can't say yet.
    WAITING = "waiting"
    # The gateway says this attempt didn't go through.
    NOT_PAID = "not_paid"
    # The money came in, but the booking had moved on: its hold ended, say.
    LATE = "late"


class CheckoutPrefill(ApiModel):
    name: str | None
    contact: str


class PaymentStart(ApiModel):
    """What the browser's checkout opens with."""

    id: uuid.UUID
    provider: Provider
    key_id: str
    order_id: str
    booking: str
    amount_paise: int
    currency: str
    # The hold's time left: checkout closes itself by then.
    expires_in_seconds: int
    prefill: CheckoutPrefill


class CheckoutCallback(ApiModel):
    """What checkout handed the browser. The order is ours, so it isn't taken from here."""

    provider_payment_id: Annotated[
        str, Field(max_length=GATEWAY_ID_MAX_LENGTH, pattern=_GATEWAY_PAYMENT_ID)
    ]
    signature: Annotated[str, Field(pattern=_SIGNATURE)]


class CheckoutResult(ApiModel):
    outcome: CheckoutOutcome
    booking: str


class WebhookReceipt(ApiModel):
    """Whether this event is new: Razorpay gets a 200 either way, and stops sending it."""

    new: bool


class StudentRefund(ApiModel):
    amount_paise: int
    status: RefundStatus
    # What they can quote to their bank, once there is one.
    reference: str | None
    requested_at: datetime
    processed_at: datetime | None


class StudentPayment(ApiModel):
    amount_paise: int
    status: PaymentStatus
    captured_at: datetime | None
    refunds: list[StudentRefund]


class StudentPayments(ApiModel):
    items: list[StudentPayment]


class OpsRefund(ApiModel):
    id: uuid.UUID
    booking: str
    kind: RefundKind
    status: RefundStatus
    amount_paise: int
    reason: str
    provider_refund_id: str | None
    reference: str | None
    # Names, when these people have them; both empty for an automatic refund.
    requested_by: str | None
    approved_by: str | None
    requested_at: datetime
    processed_at: datetime | None
    # Why it failed, or why it was declined.
    failure: str | None


class OpsRefundPage(ApiModel):
    items: list[OpsRefund]
    next_cursor: uuid.UUID | None


class OpsPayment(ApiModel):
    id: uuid.UUID
    purpose: str
    provider: str
    provider_order_id: str | None
    provider_payment_id: str | None
    amount_paise: int
    status: PaymentStatus
    captured_at: datetime | None
    # What can still go back of it.
    refundable_paise: int
    refunds: list[OpsRefund]


class OpsPayments(ApiModel):
    items: list[OpsPayment]


class RefundRequest(ApiModel):
    amount_paise: Annotated[int, Field(gt=0)]
    reason: Annotated[str, Field(min_length=1, max_length=REASON_MAX_LENGTH)]


class RefundDecline(ApiModel):
    reason: Annotated[str, Field(min_length=1, max_length=REASON_MAX_LENGTH)]
