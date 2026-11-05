"""Razorpay's Orders and Payments APIs (https://razorpay.com/docs/api/; read on 2026-11-05), over
the shared HTTP client, with no SDK: two calls and two HMACs don't need a dependency.

- An order's receipt must be unique, and Razorpay refuses a second order with the same one. So an
  answer that got lost can't make two orders: asking again finds the first by its receipt.
- Fetching a payment changes nothing, so it's tried again on a failure that may pass. Making an
  order isn't: the student's next tap is the retry.
- Nothing about a person is logged: only the HTTP status and Razorpay's error code.
"""

import asyncio
from typing import TYPE_CHECKING, Final

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, ValidationError

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

    from pydantic import SecretStr

API: Final = "https://api.razorpay.com/v1"
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


class _ErrorBody(_Answer):
    code: str = ""
    description: str = ""


class _Error(_Answer):
    error: _ErrorBody


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
        webhook_secret: SecretStr | None,
        retry_delay_s: float = 0.2,
    ) -> None:
        self._http = http
        self.key_id = key_id
        self._key_secret = key_secret
        self._webhook_secret = webhook_secret
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
        if self._webhook_secret is None:
            return False
        expected = webhook_signature(self._webhook_secret.get_secret_value(), raw_body)
        return same(expected, signature)

    async def fetch_payment(self, payment_id: str) -> GatewayPayment:
        response = await self._fetch(f"/payments/{payment_id}")
        if not response.is_success:
            raise self._refused("fetch_payment", response)
        try:
            found = _Payment.model_validate_json(response.content)
        except ValidationError as error:
            raise self._malformed("fetch_payment") from error
        return GatewayPayment(
            id=found.id,
            order_id=found.order_id,
            amount_paise=found.amount,
            currency=found.currency,
            status=found.status,
        )

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
                passing = (
                    response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR
                    or response.status_code == httpx.codes.TOO_MANY_REQUESTS
                )
                if not passing or attempt == FETCH_ATTEMPTS:
                    return response
            await asyncio.sleep(self._retry_delay_s * 2 ** (attempt - 1))
        raise PaymentGatewayUnavailableError  # pragma: no cover - the loop always returns or raises

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
