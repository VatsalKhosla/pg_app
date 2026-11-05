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

from app.modules.payments.domain.payments import (
    INR,
    GatewayOrder,
    GatewayPayment,
    GatewayStatus,
    Provider,
)
from app.modules.payments.domain.refunds import GatewayRefund, GatewayRefundStatus
from app.modules.payments.domain.signatures import checkout_signature, same, webhook_signature
from app.modules.payments.domain.webhooks import PAYMENT_EVENTS, REFUND_EVENTS, GatewayEvent
from app.modules.payments.errors import (
    PaymentGatewayRefusedError,
    PaymentGatewayUnavailableError,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic import SecretStr

API: Final = "https://api.razorpay.com/v1"
# The two headers of a webhook. The signature covers the body only, not the event's id.
SIGNATURE_HEADER: Final = "X-Razorpay-Signature"
EVENT_ID_HEADER: Final = "X-Razorpay-Event-Id"
FETCH_ATTEMPTS: Final = 3
# Razorpay answers every error, a repeated receipt included, with a code and these words.
_DUPLICATE: Final = "duplicate"

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
    )


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
    if found.event in REFUND_EVENTS:
        return _refund_event(found, created_at)
    if found.event not in PAYMENT_EVENTS:
        return GatewayEvent(found.event, created_at, None)
    try:
        payment = _WithPayment.model_validate(found.payload).payment.entity
    except ValidationError:
        return GatewayEvent(found.event, created_at, None, unreadable=True)
    return GatewayEvent(found.event, created_at, _as_payment(payment))


def _error_of(response: httpx.Response) -> _ErrorBody:
    try:
        return _Error.model_validate_json(response.content).error
    except ValidationError:
        return _ErrorBody()


class RazorpayGateway:
    name: Provider = "razorpay"

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
        response = await self._fetch(f"/payments/{payment_id}/refunds", params={"count": "100"})
        if not response.is_success:
            raise self._refused("find_refund", response)
        try:
            refunds = _Refunds.model_validate_json(response.content).items
        except ValidationError as error:
            raise self._malformed("find_refund") from error
        for refund in refunds:
            if refund.receipt == receipt:
                return _as_refund(refund)
        logger.error("razorpay has no refund for a receipt it called a duplicate")
        raise PaymentGatewayUnavailableError

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
