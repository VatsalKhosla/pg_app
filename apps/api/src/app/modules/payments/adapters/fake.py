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
from app.modules.payments.domain.links import GatewayLink, LinkStatus
from app.modules.payments.domain.mandates import (
    GatewayMandate,
    MandateOrder,
    MandatePayer,
    MandateStatus,
)
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
    from datetime import date, datetime

    from app.modules.payments.domain.reconciliation import SettlementItem
    from app.modules.payments.domain.webhooks import GatewayEvent

_KEY_SECRET: Final = "fake-gateway-key-secret"  # noqa: S105 - not a secret: it signs fake payments
_WEBHOOK_SECRET: Final = "fake-gateway-webhook-secret"  # noqa: S105 - as above
# A mandate's order, and so its payment, ends in ``_otm`` (step 6.7): the fake keeps nothing.
_ORDER_ID: Final = re.compile(r"order_fake_(?P<amount>[0-9]+)_(?P<digest>[0-9a-f]+)(?P<otm>_otm)?")
_PAYMENT_ID: Final = re.compile(r"pay_fake_(?P<amount>[0-9]+)_(?P<digest>[0-9a-f]+)(?P<otm>_otm)?")
_LINK_ID: Final = re.compile(r"plink_fake_(?P<amount>[0-9]+)_(?P<digest>[0-9a-f]+)")


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
        # It pays no bank; a test can make it say it does.
        self.settles = False
        # It takes mandates (step 6.7): a block it hasn't been told about is confirmed.
        self.supports_mandates = True
        self.mandates_said: dict[str, MandateStatus] = {}
        self.debits_made: list[str] = []
        self.released: list[str] = []
        self.refuses_debits = False
        self.orders_made = 0
        self.refunds_made = 0
        # Each refund asked for, by its receipt: a test can count its own among others'.
        self.refund_receipts: list[str] = []
        self.links_made = 0
        self.refuses_links = False
        # What tests make the gateway say: about a link, an order's attempts, a payment's refunds,
        # and a day's settlement report. It says nothing about anything else: on the test site, an
        # abandoned checkout stays unpaid.
        self.links: dict[str, GatewayLink] = {}
        self.order_attempts: dict[str, list[GatewayPayment]] = {}
        self.refunds_said: dict[str, list[GatewayRefund]] = {}
        self.settlements: dict[date, list[SettlementItem]] = {}
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
        self.refund_receipts.append(receipt)
        return GatewayRefund(
            id=f"rfnd_fake_{hashlib.sha256(receipt.encode()).hexdigest()[:16]}",
            payment_id=payment_id,
            amount_paise=amount_paise,
            status=self.refund_status,
            receipt=receipt,
            reference="ARN-FAKE-0001",
        )

    async def create_payment_link(
        self, *, amount_paise: int, reference: str, description: str, notes: Mapping[str, str]
    ) -> GatewayLink:
        _ = description, notes
        self._check_reachable()
        if self.refuses_links:
            msg = "The test bank won't make this link."
            raise PaymentGatewayRefusedError(msg)
        self.links_made += 1
        digest = hashlib.sha256(reference.encode()).hexdigest()[:16]
        return _new_link(f"plink_fake_{amount_paise}_{digest}", reference)

    async def fetch_payment_link(self, link_id: str) -> GatewayLink:
        self._check_reachable()
        said = self.links.get(link_id)
        return said if said is not None else _new_link(link_id, None)

    async def order_payments(self, order_id: str) -> list[GatewayPayment]:
        self._check_reachable()
        return list(self.order_attempts.get(order_id, []))

    async def payment_refunds(self, payment_id: str) -> list[GatewayRefund]:
        self._check_reachable()
        return list(self.refunds_said.get(payment_id, []))

    async def settlement_items(self, on: date) -> list[SettlementItem]:
        self._check_reachable()
        return list(self.settlements.get(on, []))

    def link_paid(self, link_id: str, *, reference: str | None, at: datetime) -> SignedWebhook:
        """The test bank pays a link in full: Razorpay's ``payment_link.paid``, signed. The same
        link always gets the same payment."""
        found = _LINK_ID.fullmatch(link_id)
        if found is None:
            raise PaymentGatewayUnavailableError
        amount, digest = int(found["amount"]), found["digest"]
        paid = GatewayLink(
            id=link_id,
            reference=reference,
            amount_paise=amount,
            amount_paid_paise=amount,
            status=LinkStatus.PAID,
            url=_link_url(link_id),
        )
        payment = GatewayPayment(
            id=f"pay_fake_{amount}_{digest}",
            order_id=f"order_fake_{amount}_{digest}",
            amount_paise=amount,
            currency=INR,
            status=GatewayStatus.CAPTURED,
        )
        return self.link_webhook("payment_link.paid", paid, at=at, payment=payment)

    def link_webhook(
        self,
        event: str,
        link: GatewayLink,
        *,
        at: datetime,
        payment: GatewayPayment | None = None,
        event_id: str = "",
    ) -> SignedWebhook:
        """A signed webhook about ``link``, in the shape of Razorpay's."""
        payload: dict[str, object] = {
            "payment_link": {
                "entity": {
                    "id": link.id,
                    "entity": "payment_link",
                    "reference_id": link.reference,
                    "amount": link.amount_paise,
                    "amount_paid": link.amount_paid_paise,
                    "currency": INR,
                    "status": link.status,
                    "short_url": link.url,
                    "order_id": None if payment is None else payment.order_id,
                }
            }
        }
        if payment is not None:
            payload["payment"] = {
                "entity": {
                    "id": payment.id,
                    "entity": "payment",
                    "amount": payment.amount_paise,
                    "currency": payment.currency,
                    "status": payment.status,
                    "order_id": payment.order_id,
                    "method": "upi",
                    "contact": "+919000000001",
                    "fee": 0,
                    "tax": 0,
                }
            }
        return self.signed(
            {
                "entity": "event",
                "event": event,
                "contains": list(payload),
                "created_at": int(at.timestamp()),
                "payload": payload,
            },
            event_id=event_id,
        )

    def checkout(self, order_id: str) -> CheckoutProof:
        """The test bank says yes: the same order always gets the same payment."""
        if _ORDER_ID.fullmatch(order_id) is None:
            raise PaymentGatewayUnavailableError
        payment_id = f"pay_{order_id.removeprefix('order_')}"
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
                            # Only a mandate's payments name one.
                            **({} if payment.token_id is None else {"token_id": payment.token_id}),
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
        amount, digest, otm = match["amount"], match["digest"], match["otm"] or ""
        return GatewayPayment(
            id=payment_id,
            order_id=f"order_fake_{amount}_{digest}{otm}",
            amount_paise=int(amount),
            currency=INR,
            status=GatewayStatus.CAPTURED,
            # A mandate's order authorises the mandate its digest names.
            token_id=f"token_fake_{digest}" if otm else None,
        )

    def _check_reachable(self) -> None:
        if self.unreachable:
            raise PaymentGatewayUnavailableError

    # UPI one-time mandates (step 6.7). Everything is in the ids again: a mandate order's payment,
    # its token and its customer all come from the order's digest.

    async def create_mandate(
        self,
        *,
        amount_paise: int,
        expires_at: datetime,
        receipt: str,
        payer: MandatePayer,
        notes: Mapping[str, str],
    ) -> MandateOrder:
        _ = expires_at, payer, notes
        order = await self.create_order(amount_paise=amount_paise, receipt=receipt, notes={})
        digest = order.id.rsplit("_", 1)[-1]
        return MandateOrder(f"{order.id}_otm", f"cust_fake_{digest}", amount_paise)

    async def fetch_mandate(self, *, customer_id: str, mandate_id: str) -> GatewayMandate:
        self._check_reachable()
        return GatewayMandate(
            mandate_id, self.mandates_said.get(mandate_id, MandateStatus.CONFIRMED), customer_id
        )

    async def order_debit(
        self,
        *,
        mandate_id: str,
        amount_paise: int,
        receipt: str,
        after: datetime,
        notes: Mapping[str, str],
    ) -> GatewayOrder:
        _ = mandate_id, after
        return await self.create_order(amount_paise=amount_paise, receipt=receipt, notes=notes)

    async def debit(
        self,
        *,
        order_id: str,
        customer_id: str,
        mandate_id: str,
        amount_paise: int,
        payer: MandatePayer,
        notes: Mapping[str, str],
    ) -> str:
        _ = customer_id, amount_paise, payer, notes
        self._check_reachable()
        if self.refuses_debits:
            msg = "The test bank won't debit this mandate."
            raise PaymentGatewayRefusedError(msg)
        self.debits_made.append(mandate_id)
        return self.checkout(order_id).payment_id

    async def release_mandate(self, *, customer_id: str, mandate_id: str) -> None:
        _ = customer_id
        self._check_reachable()
        self.released.append(mandate_id)
        self.mandates_said[mandate_id] = MandateStatus.CANCELLED

    def mandate_webhook(
        self,
        event: str,
        mandate_id: str,
        status: MandateStatus,
        *,
        at: datetime,
        event_id: str = "",
    ) -> SignedWebhook:
        """A signed webhook about a mandate, in the shape of Razorpay's token events."""
        return self.signed(
            {
                "entity": "event",
                "event": event,
                "contains": ["token"],
                "created_at": int(at.timestamp()),
                "payload": {
                    "token": {
                        "entity": {
                            "id": mandate_id,
                            "entity": "token",
                            "method": "upi",
                            "recurring": True,
                            "recurring_details": {"status": status, "failure_reason": None},
                            "vpa": {"username": "a.student", "handle": "fakebank"},
                        }
                    }
                },
            },
            event_id=event_id,
        )


def _link_url(link_id: str) -> str:
    return f"https://pay.fake.test/{link_id}"


def _new_link(link_id: str, reference: str | None) -> GatewayLink:
    found = _LINK_ID.fullmatch(link_id)
    if found is None:
        raise PaymentGatewayUnavailableError
    return GatewayLink(
        id=link_id,
        reference=reference,
        amount_paise=int(found["amount"]),
        amount_paid_paise=0,
        status=LinkStatus.CREATED,
        url=_link_url(link_id),
    )
