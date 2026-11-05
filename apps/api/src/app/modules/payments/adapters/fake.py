"""A gateway that moves no money, for tests, local development and the test site (ARCHITECTURE
§9.1, ADR 0056). Settings refuse it in production.

It signs exactly as Razorpay does, so everything downstream of it is the real path: the signature
check, the fetch, the amount check and the booking's move. Everything it knows is in its ids, so
it needs no memory, and works across processes and restarts. A payment it hasn't been told about
is captured.

``checkout`` is the test bank's page: what a browser gets back from a checkout that went through.
Tests can also make it say something else about a payment, or be out of reach, and get signed
webhooks from it.
"""

import hashlib
import json
import re
import secrets
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

from app.modules.payments.adapters.razorpay import read_razorpay_webhook
from app.modules.payments.domain.payments import (
    INR,
    GatewayOrder,
    GatewayPayment,
    GatewayStatus,
    Provider,
)
from app.modules.payments.domain.refunds import GatewayRefund, GatewayRefundStatus
from app.modules.payments.domain.signatures import checkout_signature, same, webhook_signature
from app.modules.payments.errors import (
    PaymentGatewayRefusedError,
    PaymentGatewayUnavailableError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from app.modules.payments.domain.webhooks import GatewayEvent

_KEY_SECRET: Final = "fake-gateway-key-secret"  # noqa: S105 - not a secret: it signs fake payments
_WEBHOOK_SECRET: Final = "fake-gateway-webhook-secret"  # noqa: S105 - as above
_PAYMENT_ID: Final = re.compile(r"pay_fake_(?P<amount>[0-9]+)_(?P<digest>[0-9a-f]+)")


@dataclass(frozen=True, slots=True)
class CheckoutProof:
    """What a checkout that went through hands the browser."""

    payment_id: str
    signature: str


@dataclass(frozen=True, slots=True)
class SignedWebhook:
    """A webhook as Razorpay would send it: the body, and its two headers."""

    raw_body: bytes
    signature: str
    event_id: str


class FakeGateway:
    name: Provider = "fake"
    key_id = "fake_key"

    def __init__(self) -> None:
        self.unreachable = False
        self.orders_made = 0
        self.refunds_made = 0
        self.refund_status = GatewayRefundStatus.PROCESSED
        self.refuses_refunds = False
        self._said: dict[str, GatewayPayment] = {}

    async def create_order(
        self, *, amount_paise: int, receipt: str, notes: Mapping[str, str]
    ) -> GatewayOrder:
        _ = notes
        self._check_reachable()
        self.orders_made += 1
        digest = hashlib.sha256(receipt.encode()).hexdigest()[:16]
        return GatewayOrder(f"order_fake_{amount_paise}_{digest}", amount_paise, INR)

    def verify_checkout_signature(self, *, order_id: str, payment_id: str, signature: str) -> bool:
        expected = checkout_signature(_KEY_SECRET, order_id=order_id, payment_id=payment_id)
        return same(expected, signature)

    def verify_webhook(self, *, raw_body: bytes, signature: str) -> bool:
        return same(webhook_signature(_WEBHOOK_SECRET, raw_body), signature)

    def read_webhook(self, raw_body: bytes) -> GatewayEvent | None:
        return read_razorpay_webhook(raw_body)

    async def fetch_payment(self, payment_id: str) -> GatewayPayment:
        self._check_reachable()
        said = self._said.get(payment_id)
        if said is not None:
            return said
        return self._captured(payment_id)

    async def refund(
        self, *, payment_id: str, amount_paise: int, receipt: str, notes: Mapping[str, str]
    ) -> GatewayRefund:
        _ = notes
        self._check_reachable()
        if self.refuses_refunds:
            msg = "The test bank refuses this refund."
            raise PaymentGatewayRefusedError(msg)
        self.refunds_made += 1
        return GatewayRefund(
            id=f"rfnd_fake_{hashlib.sha256(receipt.encode()).hexdigest()[:16]}",
            payment_id=payment_id,
            amount_paise=amount_paise,
            status=self.refund_status,
            receipt=receipt,
            reference="ARN-FAKE-0001",
        )

    def checkout(self, order_id: str) -> CheckoutProof:
        """The test bank says yes: the same order always gets the same payment."""
        _, _, amount, digest = order_id.split("_")
        payment_id = f"pay_fake_{amount}_{digest}"
        signature = checkout_signature(_KEY_SECRET, order_id=order_id, payment_id=payment_id)
        return CheckoutProof(payment_id, signature)

    def say(
        self,
        payment_id: str,
        *,
        status: GatewayStatus = GatewayStatus.CAPTURED,
        amount_paise: int | None = None,
        order_id: str | None = None,
        currency: str = INR,
    ) -> None:
        """For tests: what the gateway says about this payment from now on."""
        found = self._captured(payment_id)
        self._said[payment_id] = replace(
            found,
            status=status,
            amount_paise=found.amount_paise if amount_paise is None else amount_paise,
            order_id=found.order_id if order_id is None else order_id,
            currency=currency,
        )

    def webhook(
        self, event: str, payment: GatewayPayment, *, at: datetime, event_id: str = ""
    ) -> SignedWebhook:
        """A signed webhook about ``payment``, in the shape of Razorpay's, with what a real one
        holds that we mustn't keep."""
        return self.signed(
            {
                "entity": "event",
                "account_id": "acc_fake",
                "event": event,
                "contains": ["payment"],
                "created_at": int(at.timestamp()),
                "payload": {
                    "payment": {
                        "entity": {
                            "id": payment.id,
                            "entity": "payment",
                            "amount": payment.amount_paise,
                            "currency": payment.currency,
                            "status": payment.status,
                            "order_id": payment.order_id,
                            "method": "upi",
                            "vpa": "a.student@fakebank",
                            "email": "a.student@example.com",
                            "contact": "+919000000000",
                        }
                    }
                },
            },
            event_id=event_id,
        )

    def refund_webhook(
        self,
        event: str,
        refund: GatewayRefund,
        *,
        at: datetime,
        order_id: str | None = None,
        event_id: str = "",
    ) -> SignedWebhook:
        """A signed webhook about ``refund``, in the shape of Razorpay's."""
        return self.signed(
            {
                "entity": "event",
                "event": event,
                "contains": ["refund", "payment"],
                "created_at": int(at.timestamp()),
                "payload": {
                    "refund": {
                        "entity": {
                            "id": refund.id,
                            "entity": "refund",
                            "amount": refund.amount_paise,
                            "currency": INR,
                            "payment_id": refund.payment_id,
                            "receipt": refund.receipt,
                            "acquirer_data": {"arn": refund.reference},
                            "status": refund.status,
                        }
                    },
                    "payment": {
                        "entity": {
                            "id": refund.payment_id,
                            "amount": refund.amount_paise,
                            "currency": INR,
                            "status": "refunded",
                            "order_id": order_id,
                            "contact": "+919000000000",
                        }
                    },
                },
            },
            event_id=event_id,
        )

    def signed(self, body: Mapping[str, object], *, event_id: str = "") -> SignedWebhook:
        """Any body, signed as the gateway signs its webhooks."""
        raw_body = json.dumps(body).encode()
        return SignedWebhook(
            raw_body=raw_body,
            signature=webhook_signature(_WEBHOOK_SECRET, raw_body),
            event_id=event_id or f"evt_fake_{secrets.token_hex(8)}",
        )

    def _captured(self, payment_id: str) -> GatewayPayment:
        match = _PAYMENT_ID.fullmatch(payment_id)
        if match is None:
            raise PaymentGatewayUnavailableError
        amount, digest = match["amount"], match["digest"]
        return GatewayPayment(
            id=payment_id,
            order_id=f"order_fake_{amount}_{digest}",
            amount_paise=int(amount),
            currency=INR,
            status=GatewayStatus.CAPTURED,
        )

    def _check_reachable(self) -> None:
        if self.unreachable:
            raise PaymentGatewayUnavailableError
