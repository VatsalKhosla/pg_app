"""Razorpay's Orders and Payments APIs (https://razorpay.com/docs/api/; read on 2026-11-05), over
the shared HTTP client, with no SDK: two calls and two HMACs don't need a dependency.

- An order's receipt must be unique, and Razorpay refuses a second order with the same one. So an
  answer that got lost can't make two orders: asking again finds the first by its receipt.
- Fetching a payment changes nothing, so it's tried again on a failure that may pass. Making an
  order isn't: the student's next tap is the retry.
- Nothing about a person is logged: only the HTTP status and Razorpay's error code.
"""

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.modules.payments.domain.links import LINK_EVENTS, GatewayLink, LinkStatus
from app.modules.payments.domain.mandates import (
    MANDATE_EVENTS,
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
from app.modules.payments.domain.reconciliation import SettlementItem
from app.modules.payments.domain.refunds import GatewayRefund, GatewayRefundStatus
from app.modules.payments.domain.signatures import checkout_signature, same, webhook_signature
from app.modules.payments.domain.webhooks import PAYMENT_EVENTS, REFUND_EVENTS, GatewayEvent
from app.modules.payments.errors import (
    PaymentGatewayRefusedError,
    PaymentGatewayUnavailableError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from datetime import date

    from pydantic import SecretStr

API: Final = "https://api.razorpay.com/v1"
# The two headers of a webhook. The signature covers the body only, not the event's id.
SIGNATURE_HEADER: Final = "X-Razorpay-Signature"
EVENT_ID_HEADER: Final = "X-Razorpay-Event-Id"
FETCH_ATTEMPTS: Final = 3
# Razorpay answers every error, a repeated receipt included, with a code and these words.
_DUPLICATE: Final = "duplicate"
# ...and a payment link's reference used before with these.
_ATTEMPTED: Final = "already attempted"
# The most report items Razorpay gives in one answer.
_REPORT_PAGE: Final = 1000
# Razorpay asks a mandate's debit for an email; students sign in by phone, and this is Razorpay's
# own address for a customer who gave none.
_NO_EMAIL: Final = "void@razorpay.com"

logger = structlog.stdlib.get_logger(__name__)


class _Answer(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _Order(_Answer):
    id: str
    amount: int
    currency: str
    receipt: str | None = None


class _Orders(_Answer):
    items: list[_Order]


class _Payment(_Answer):
    id: str
    order_id: str | None = None
    amount: int
    currency: str
    status: GatewayStatus
    token_id: str | None = None


class _Acquirer(_Answer):
    arn: str | None = None
    rrn: str | None = None
    utr: str | None = None


class _Refund(_Answer):
    id: str
    payment_id: str
    amount: int
    status: GatewayRefundStatus
    receipt: str | None = None
    acquirer_data: _Acquirer | None = None


class _Refunds(_Answer):
    items: list[_Refund]


class _Payments(_Answer):
    items: list[_Payment]


class _LinkPayment(_Answer):
    payment_id: str
    status: str = ""


class _Link(_Answer):
    id: str
    reference_id: str | None = None
    amount: int
    amount_paid: int = 0
    status: LinkStatus
    short_url: str = ""
    payments: list[_LinkPayment] | None = None


class _Links(_Answer):
    payment_links: list[_Link]


class _ReportItem(_Answer):
    entity_id: str
    type: str
    amount: int
    fee: int | None = None
    tax: int | None = None
    credit: int = 0
    debit: int = 0
    currency: str = INR
    settled: bool = False
    settlement_id: str | None = None
    payment_id: str | None = None


class _Report(_Answer):
    items: list[_ReportItem]


class _Customer(_Answer):
    id: str


class _RecurringDetails(_Answer):
    status: MandateStatus


class _Token(_Answer):
    id: str
    recurring_details: _RecurringDetails
    customer_id: str | None = None


class _Tokens(_Answer):
    items: list[_Token]


class _TokenEntity(_Answer):
    entity: _Token


class _WithToken(_Answer):
    token: _TokenEntity


class _RecurringPayment(_Answer):
    razorpay_payment_id: str


class _ErrorBody(_Answer):
    code: str = ""
    description: str = ""


class _Error(_Answer):
    error: _ErrorBody


class _Webhook(_Answer):
    event: str
    created_at: int
    payload: dict[str, object] = Field(default_factory=dict)


class _PaymentEntity(_Answer):
    entity: _Payment


class _WithPayment(_Answer):
    payment: _PaymentEntity


class _LinkEntity(_Answer):
    entity: _Link


class _WithLink(_Answer):
    payment_link: _LinkEntity


class _RefundEntity(_Answer):
    entity: _Refund


class _WithRefund(_Answer):
    refund: _RefundEntity


def _as_payment(found: _Payment) -> GatewayPayment:
    return GatewayPayment(
        id=found.id,
        order_id=found.order_id,
        amount_paise=found.amount,
        currency=found.currency,
        status=found.status,
        token_id=found.token_id,
    )


def _as_mandate(found: _Token) -> GatewayMandate:
    return GatewayMandate(
        id=found.id, status=found.recurring_details.status, customer_id=found.customer_id
    )


def _mandate_event(found: _Webhook, created_at: datetime) -> GatewayEvent:
    try:
        token = _WithToken.model_validate(found.payload).token.entity
    except ValidationError:
        return GatewayEvent(found.event, created_at, None, unreadable=True)
    return GatewayEvent(found.event, created_at, None, mandate=_as_mandate(token))


def _as_refund(found: _Refund) -> GatewayRefund:
    bank = found.acquirer_data
    return GatewayRefund(
        id=found.id,
        payment_id=found.payment_id,
        amount_paise=found.amount,
        status=found.status,
        receipt=found.receipt,
        reference=None if bank is None else bank.arn or bank.rrn or bank.utr,
    )


def _as_link(found: _Link, *, paid_by: str | None = None) -> GatewayLink:
    captured = [each.payment_id for each in found.payments or [] if each.status == "captured"]
    return GatewayLink(
        id=found.id,
        reference=found.reference_id or None,
        amount_paise=found.amount,
        amount_paid_paise=found.amount_paid,
        status=found.status,
        url=found.short_url,
        payment_id=captured[0] if captured else paid_by,
    )


def _as_item(found: _ReportItem) -> SettlementItem:
    return SettlementItem(
        entity_id=found.entity_id,
        kind=found.type,
        amount_paise=found.amount,
        fee_paise=found.fee or 0,
        tax_paise=found.tax or 0,
        credit_paise=found.credit,
        debit_paise=found.debit,
        currency=found.currency,
        settled=found.settled,
        settlement_id=found.settlement_id,
        payment_id=found.payment_id,
    )


def _link_event(found: _Webhook, created_at: datetime) -> GatewayEvent:
    try:
        link = _WithLink.model_validate(found.payload).payment_link.entity
    except ValidationError:
        return GatewayEvent(found.event, created_at, None, unreadable=True)
    try:
        payment = _as_payment(_WithPayment.model_validate(found.payload).payment.entity)
    except ValidationError:
        payment = None  # an expired or cancelled link has none
    paid_by = None if payment is None else payment.id
    return GatewayEvent(found.event, created_at, payment, link=_as_link(link, paid_by=paid_by))


def _refund_event(found: _Webhook, created_at: datetime) -> GatewayEvent:
    try:
        refund = _WithRefund.model_validate(found.payload).refund.entity
    except ValidationError:
        return GatewayEvent(found.event, created_at, None, unreadable=True)
    try:
        payment = _as_payment(_WithPayment.model_validate(found.payload).payment.entity)
    except ValidationError:
        payment = None  # the refund's own payment id is enough to go on
    return GatewayEvent(found.event, created_at, payment, refund=_as_refund(refund))


def read_razorpay_webhook(raw_body: bytes) -> GatewayEvent | None:
    """A webhook in Razorpay's shape, which the fake gateway's share: an event of any kind, with
    the payment it's about if it's one acted on. A kind we don't know, or a payment that doesn't
    make sense, is still an event: it's kept, and answered, so Razorpay doesn't keep retrying and
    in the end turn the webhook off."""
    try:
        found = _Webhook.model_validate_json(raw_body)
    except ValidationError:
        return None
    created_at = datetime.fromtimestamp(found.created_at, tz=UTC)
    reader = _READERS.get(found.event)
    if reader is not None:
        return reader(found, created_at)
    if found.event not in PAYMENT_EVENTS:
        return GatewayEvent(found.event, created_at, None)
    try:
        payment = _WithPayment.model_validate(found.payload).payment.entity
    except ValidationError:
        return GatewayEvent(found.event, created_at, None, unreadable=True)
    return GatewayEvent(found.event, created_at, _as_payment(payment))


# The events that are about something other than a payment, each with its reader.
_READERS: Final[dict[str, Callable[[_Webhook, datetime], GatewayEvent]]] = {
    **dict.fromkeys(REFUND_EVENTS, _refund_event),
    **dict.fromkeys(LINK_EVENTS, _link_event),
    **dict.fromkeys(MANDATE_EVENTS, _mandate_event),
}


def _error_of(response: httpx.Response) -> _ErrorBody:
    try:
        return _Error.model_validate_json(response.content).error
    except ValidationError:
        return _ErrorBody()


class RazorpayGateway:
    name: Provider = "razorpay"
    settles = True
    # Razorpay enables them per account; the token_mode flag says whether we use them.
    supports_mandates = True

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        key_id: str,
        key_secret: SecretStr,
        webhook_secret: SecretStr,
        refund_speed: str = "normal",
        retry_delay_s: float = 0.2,
    ) -> None:
        self._http = http
        self.key_id = key_id
        self._key_secret = key_secret
        self._webhook_secret = webhook_secret
        self._refund_speed = refund_speed
        self._retry_delay_s = retry_delay_s

    async def create_order(
        self, *, amount_paise: int, receipt: str, notes: Mapping[str, str]
    ) -> GatewayOrder:
        response = await self._send(
            "POST",
            "/orders",
            json={
                "amount": amount_paise,
                "currency": INR,
                "receipt": receipt,
                "notes": dict(notes),
            },
        )
        if response.is_success:
            return self._order(_Order, response)
        if _DUPLICATE in _error_of(response).description.lower():
            return await self._order_with_receipt(receipt)
        raise self._refused("create_order", response)

    def verify_checkout_signature(self, *, order_id: str, payment_id: str, signature: str) -> bool:
        expected = checkout_signature(
            self._key_secret.get_secret_value(), order_id=order_id, payment_id=payment_id
        )
        return same(expected, signature)

    def verify_webhook(self, *, raw_body: bytes, signature: str) -> bool:
        expected = webhook_signature(self._webhook_secret.get_secret_value(), raw_body)
        return same(expected, signature)

    def read_webhook(self, raw_body: bytes) -> GatewayEvent | None:
        return read_razorpay_webhook(raw_body)

    async def fetch_payment(self, payment_id: str) -> GatewayPayment:
        response = await self._fetch(f"/payments/{payment_id}")
        if not response.is_success:
            raise self._refused("fetch_payment", response)
        try:
            found = _Payment.model_validate_json(response.content)
        except ValidationError as error:
            raise self._malformed("fetch_payment") from error
        return _as_payment(found)

    async def refund(
        self, *, payment_id: str, amount_paise: int, receipt: str, notes: Mapping[str, str]
    ) -> GatewayRefund:
        response = await self._send(
            "POST",
            f"/payments/{payment_id}/refund",
            json={
                "amount": amount_paise,
                "speed": self._refund_speed,
                "receipt": receipt,
                "notes": dict(notes),
            },
        )
        if response.is_success:
            try:
                return _as_refund(_Refund.model_validate_json(response.content))
            except ValidationError as error:
                raise self._malformed("refund") from error
        said = _error_of(response)
        if _DUPLICATE in said.description.lower():
            return await self._refund_with_receipt(payment_id, receipt)
        if self._may_pass(response):
            raise self._refused("refund", response)
        logger.error("razorpay won't refund", status=response.status_code, code=said.code)
        raise PaymentGatewayRefusedError(said.description or "Razorpay refused this refund.")

    async def _refund_with_receipt(self, payment_id: str, receipt: str) -> GatewayRefund:
        for refund in await self.payment_refunds(payment_id):
            if refund.receipt == receipt:
                return refund
        logger.error("razorpay has no refund for a receipt it called a duplicate")
        raise PaymentGatewayUnavailableError

    async def create_payment_link(
        self, *, amount_paise: int, reference: str, description: str, notes: Mapping[str, str]
    ) -> GatewayLink:
        response = await self._send(
            "POST",
            "/payment_links",
            json={
                "amount": amount_paise,
                "currency": INR,
                "accept_partial": False,
                "reference_id": reference,
                "description": description,
                # We tell the owner ourselves (step 6.5).
                "notify": {"sms": False, "email": False},
                "reminder_enable": False,
                "notes": dict(notes),
            },
        )
        if response.is_success:
            return self._link(response, "create_payment_link")
        said = _error_of(response)
        words = said.description.lower()
        if _ATTEMPTED in words or _DUPLICATE in words:
            return await self._link_with_reference(reference)
        if self._may_pass(response):
            raise self._refused("create_payment_link", response)
        logger.error(
            "razorpay won't make a payment link", status=response.status_code, code=said.code
        )
        raise PaymentGatewayRefusedError(said.description or "Razorpay refused this payment link.")

    async def fetch_payment_link(self, link_id: str) -> GatewayLink:
        response = await self._fetch(f"/payment_links/{link_id}")
        if not response.is_success:
            raise self._refused("fetch_payment_link", response)
        return self._link(response, "fetch_payment_link")

    async def order_payments(self, order_id: str) -> list[GatewayPayment]:
        response = await self._fetch(f"/orders/{order_id}/payments")
        if not response.is_success:
            raise self._refused("order_payments", response)
        try:
            payments = _Payments.model_validate_json(response.content).items
        except ValidationError as error:
            raise self._malformed("order_payments") from error
        return [_as_payment(payment) for payment in payments]

    async def payment_refunds(self, payment_id: str) -> list[GatewayRefund]:
        response = await self._fetch(f"/payments/{payment_id}/refunds", params={"count": "100"})
        if not response.is_success:
            raise self._refused("payment_refunds", response)
        try:
            refunds = _Refunds.model_validate_json(response.content).items
        except ValidationError as error:
            raise self._malformed("payment_refunds") from error
        return [_as_refund(refund) for refund in refunds]

    async def settlement_items(self, on: date) -> list[SettlementItem]:
        items: list[SettlementItem] = []
        while True:
            response = await self._fetch(
                "/settlements/recon/combined",
                params={
                    "year": str(on.year),
                    "month": f"{on.month:02d}",
                    "day": f"{on.day:02d}",
                    "count": str(_REPORT_PAGE),
                    "skip": str(len(items)),
                },
            )
            if not response.is_success:
                raise self._refused("settlement_items", response)
            try:
                page = _Report.model_validate_json(response.content).items
            except ValidationError as error:
                raise self._malformed("settlement_items") from error
            items += [_as_item(item) for item in page]
            if len(page) < _REPORT_PAGE:
                return items

    async def create_mandate(
        self,
        *,
        amount_paise: int,
        expires_at: datetime,
        receipt: str,
        payer: MandatePayer,
        notes: Mapping[str, str],
    ) -> MandateOrder:
        customer = await self._customer(payer)
        response = await self._send(
            "POST",
            "/orders",
            json={
                "amount": amount_paise,
                "currency": INR,
                "customer_id": customer,
                "method": "upi",
                "token": {
                    "max_amount": amount_paise,
                    "expire_at": int(expires_at.timestamp()),
                    "frequency": "one_time",
                },
                "receipt": receipt,
                "notes": dict(notes),
            },
        )
        if response.is_success:
            order = self._order(_Order, response)
        elif _DUPLICATE in _error_of(response).description.lower():
            order = await self._order_with_receipt(receipt)
        else:
            raise self._refused("create_mandate", response)
        return MandateOrder(order.id, customer, order.amount_paise)

    async def fetch_mandate(self, *, customer_id: str, mandate_id: str) -> GatewayMandate:
        response = await self._fetch(f"/customers/{customer_id}/tokens")
        if not response.is_success:
            raise self._refused("fetch_mandate", response)
        try:
            tokens = _Tokens.model_validate_json(response.content).items
        except ValidationError as error:
            raise self._malformed("fetch_mandate") from error
        for token in tokens:
            if token.id == mandate_id:
                return _as_mandate(token)
        # Razorpay leaves out tokens that lapsed unused, and ones already debited.
        return GatewayMandate(mandate_id, MandateStatus.CANCELLED, customer_id)

    async def order_debit(
        self,
        *,
        mandate_id: str,
        amount_paise: int,
        receipt: str,
        after: datetime,
        notes: Mapping[str, str],
    ) -> GatewayOrder:
        response = await self._send(
            "POST",
            "/orders",
            json={
                "amount": amount_paise,
                "currency": INR,
                "payment_capture": True,
                "receipt": receipt,
                # Razorpay sends the student the notice, and doesn't debit by itself: we do,
                # from ``after``.
                "notification": {"token_id": mandate_id, "payment_after": int(after.timestamp())},
                "notes": dict(notes),
            },
        )
        if response.is_success:
            return self._order(_Order, response)
        if _DUPLICATE in _error_of(response).description.lower():
            return await self._order_with_receipt(receipt)
        raise self._refused("order_debit", response)

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
        response = await self._send(
            "POST",
            "/payments/create/recurring",
            json={
                "email": _NO_EMAIL,
                "contact": payer.contact,
                "amount": amount_paise,
                "currency": INR,
                "order_id": order_id,
                "customer_id": customer_id,
                "token": mandate_id,
                "recurring": True,
                "notes": dict(notes),
            },
        )
        if response.is_success:
            try:
                return _RecurringPayment.model_validate_json(response.content).razorpay_payment_id
            except ValidationError as error:
                raise self._malformed("debit") from error
        if self._may_pass(response):
            raise self._refused("debit", response)
        said = _error_of(response)
        logger.error("razorpay won't debit a mandate", status=response.status_code, code=said.code)
        raise PaymentGatewayRefusedError(said.description or "Razorpay refused this debit.")

    async def release_mandate(self, *, customer_id: str, mandate_id: str) -> None:
        response = await self._send("PUT", f"/customers/{customer_id}/tokens/{mandate_id}/cancel")
        if response.is_success:
            return
        if self._may_pass(response):
            raise self._refused("release_mandate", response)
        # One already cancelled, used or lapsed has nothing left blocked.
        logger.warning("razorpay wouldn't cancel a mandate", status=response.status_code)

    async def _customer(self, payer: MandatePayer) -> str:
        """The student as Razorpay's customer: the same one each time (``fail_existing`` 0)."""
        response = await self._send(
            "POST",
            "/customers",
            json={
                "name": payer.name or "Student",
                "contact": payer.contact,
                "fail_existing": "0",
            },
        )
        if not response.is_success:
            raise self._refused("create_customer", response)
        try:
            return _Customer.model_validate_json(response.content).id
        except ValidationError as error:
            raise self._malformed("create_customer") from error

    def _link(self, response: httpx.Response, call: str) -> GatewayLink:
        try:
            return _as_link(_Link.model_validate_json(response.content))
        except ValidationError as error:
            raise self._malformed(call) from error

    async def _link_with_reference(self, reference: str) -> GatewayLink:
        response = await self._fetch("/payment_links", params={"reference_id": reference})
        if not response.is_success:
            raise self._refused("find_payment_link", response)
        try:
            links = _Links.model_validate_json(response.content).payment_links
        except ValidationError as error:
            raise self._malformed("find_payment_link") from error
        for link in links:
            if link.reference_id == reference:
                return _as_link(link)
        # The reference was spent on an attempt that made nothing: the next try needs another.
        logger.error("razorpay has no payment link for a reference it called used")
        raise PaymentGatewayRefusedError("Razorpay has no payment link for this reference.")

    async def _order_with_receipt(self, receipt: str) -> GatewayOrder:
        response = await self._fetch("/orders", params={"receipt": receipt})
        if not response.is_success:
            raise self._refused("find_order", response)
        try:
            orders = _Orders.model_validate_json(response.content).items
        except ValidationError as error:
            raise self._malformed("find_order") from error
        # The filter matches any receipt that contains this one.
        for order in orders:
            if order.receipt == receipt:
                return GatewayOrder(order.id, order.amount, order.currency)
        logger.error("razorpay has no order for a receipt it called a duplicate")
        raise PaymentGatewayUnavailableError

    def _order(self, shape: type[_Order], response: httpx.Response) -> GatewayOrder:
        try:
            order = shape.model_validate_json(response.content)
        except ValidationError as error:
            raise self._malformed("create_order") from error
        return GatewayOrder(order.id, order.amount, order.currency)

    async def _fetch(self, path: str, *, params: Mapping[str, str] | None = None) -> httpx.Response:
        """A read, tried again when the failure may pass."""
        for attempt in range(1, FETCH_ATTEMPTS + 1):
            try:
                response = await self._send("GET", path, params=params)
            except PaymentGatewayUnavailableError:
                if attempt == FETCH_ATTEMPTS:
                    raise
            else:
                if not self._may_pass(response) or attempt == FETCH_ATTEMPTS:
                    return response
            await asyncio.sleep(self._retry_delay_s * 2 ** (attempt - 1))
        raise PaymentGatewayUnavailableError  # pragma: no cover - the loop always returns or raises

    @staticmethod
    def _may_pass(response: httpx.Response) -> bool:
        return (
            response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR
            or response.status_code == httpx.codes.TOO_MANY_REQUESTS
        )

    async def _send(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, object] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        try:
            return await self._http.request(
                method,
                f"{API}{path}",
                json=json,
                params=params,
                auth=(self.key_id, self._key_secret.get_secret_value()),
            )
        except httpx.HTTPError as error:
            logger.warning("razorpay can't be reached", error=type(error).__name__)
            raise PaymentGatewayUnavailableError from error

    def _refused(self, call: str, response: httpx.Response) -> PaymentGatewayUnavailableError:
        logger.error(
            "razorpay refused",
            call=call,
            status=response.status_code,
            code=_error_of(response).code,
        )
        return PaymentGatewayUnavailableError()

    def _malformed(self, call: str) -> PaymentGatewayUnavailableError:
        logger.error("razorpay answered something unexpected", call=call)
        return PaymentGatewayUnavailableError()
