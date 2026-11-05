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

from app.modules.payments.domain.payments import (
    INR,
    GatewayOrder,
    GatewayPayment,
    GatewayStatus,
    Provider,
)
from app.modules.payments.domain.signatures import checkout_signature, same, webhook_signature
from app.modules.payments.errors import PaymentGatewayUnavailableError

if TYPE_CHECKING:
    from collections.abc import Mapping

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

    async def fetch_payment(self, payment_id: str) -> GatewayPayment:
        self._check_reachable()
        said = self._said.get(payment_id)
        if said is not None:
            return said
        return self._captured(payment_id)

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

    def webhook(self, event: str, payment: GatewayPayment, *, event_id: str = "") -> SignedWebhook:
        """A signed webhook about ``payment``, in the shape of Razorpay's."""
        body = json.dumps(
            {
                "entity": "event",
                "account_id": "acc_fake",
                "event": event,
                "contains": ["payment"],
                "payload": {
                    "payment": {
                        "entity": {
                            "id": payment.id,
                            "entity": "payment",
                            "amount": payment.amount_paise,
                            "currency": payment.currency,
                            "status": payment.status,
                            "order_id": payment.order_id,
                        }
                    }
                },
            }
        ).encode()
        return SignedWebhook(
            raw_body=body,
            signature=webhook_signature(_WEBHOOK_SECRET, body),
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
