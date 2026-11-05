"""What the payments API takes and gives (step 6.1, ADR 0056). The browser never says how much:
the amount is the booking's, fixed by its quote (rule 12's server-side money)."""

import uuid
from enum import StrEnum
from typing import Annotated, Final

from pydantic import Field

from app.core.schemas import ApiModel
from app.modules.payments.domain.payments import Provider

GATEWAY_ID_MAX_LENGTH: Final = 64
_GATEWAY_PAYMENT_ID: Final = r"^pay_[A-Za-z0-9_]+$"
_SIGNATURE: Final = r"^[0-9a-f]{64}$"


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
