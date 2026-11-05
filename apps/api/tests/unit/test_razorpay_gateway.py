"""The Razorpay adapter against Razorpay's documented requests and answers (read on 2026-11-05),
with no network: an order for the exact token, a lost answer finding the same order, what a fetched
payment says, and every way the gateway can fail."""

import asyncio
import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.modules.payments.adapters.fake import FakeGateway
from app.modules.payments.adapters.razorpay import API, FETCH_ATTEMPTS, RazorpayGateway
from app.modules.payments.domain.payments import GatewayOrder, GatewayPayment, GatewayStatus
from app.modules.payments.domain.signatures import checkout_signature, webhook_signature
from app.modules.payments.domain.webhooks import GatewayEvent
from app.modules.payments.errors import PaymentGatewayUnavailableError
from app.modules.payments.ports import PaymentGateway

KEY_ID = "rzp_test_1DP5mmOlF5G5ag"
KEY_SECRET = "a-test-key-secret"
WEBHOOK_SECRET = "a-test-webhook-secret"
TOKEN = 200_000
RECEIPT = "token-BK-7F3K2Q9M"
# The documented answers, trimmed of nothing: the adapter must ignore what it doesn't read.
ORDER = {
    "id": "order_RB58MiP5SPFYyM",
    "entity": "order",
    "amount": TOKEN,
    "amount_paid": 0,
    "amount_due": TOKEN,
    "currency": "INR",
    "receipt": RECEIPT,
    "status": "created",
    "attempts": 0,
    "notes": {"booking": "BK-7F3K2Q9M", "purpose": "token"},
    "offer_id": None,
    "created_at": 1756455561,
}
PAYMENT = {
    "id": "pay_DG4ZdRK8ZnXC3k",
    "entity": "payment",
    "amount": TOKEN,
    "currency": "INR",
    "status": "captured",
    "order_id": ORDER["id"],
    "invoice_id": None,
    "international": False,
    "method": "upi",
    "amount_refunded": 0,
    "refund_status": None,
    "captured": True,
    "description": None,
    "card_id": None,
    "bank": None,
    "wallet": None,
    "vpa": "success@razorpay",
    "email": "void@razorpay.com",
    "contact": "+919000090000",
    "notes": [],
    "fee": 4720,
    "tax": 720,
    "error_code": None,
    "error_description": None,
    "error_source": None,
    "error_step": None,
    "error_reason": None,
    "created_at": 1756455600,
}
DUPLICATE = {"error": {"code": "BAD_REQUEST_ERROR", "description": "Duplicate request"}}
UNKNOWN = {"error": {"code": "BAD_REQUEST_ERROR", "description": "The id provided does not exist"}}

type Handler = Callable[[httpx.Request], httpx.Response]


def _gateway(handler: Handler) -> RazorpayGateway:
    return RazorpayGateway(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        key_id=KEY_ID,
        key_secret=SecretStr(KEY_SECRET),
        webhook_secret=SecretStr(WEBHOOK_SECRET),
        retry_delay_s=0,
    )


def _nothing(request: httpx.Request) -> httpx.Response:
    raise AssertionError(request.url)


def _answering(status: int, body: Any) -> Handler:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return handler


def test_an_order_is_for_the_exact_amount_in_paise_signed_with_the_key() -> None:
    async def scenario() -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=ORDER)

        order = await _gateway(handler).create_order(
            amount_paise=TOKEN, receipt=RECEIPT, notes={"booking": "BK-7F3K2Q9M"}
        )

        assert order == GatewayOrder("order_RB58MiP5SPFYyM", TOKEN, "INR")
        request = seen[0]
        assert (request.method, str(request.url)) == ("POST", f"{API}/orders")
        assert request.url.host == "api.razorpay.com"
        expected = base64.b64encode(f"{KEY_ID}:{KEY_SECRET}".encode()).decode()
        assert request.headers["authorization"] == f"Basic {expected}"
        # A JSON integer, as Razorpay insists: never a string or a float.
        body = json.loads(request.content)
        assert body == {
            "amount": TOKEN,
            "currency": "INR",
            "receipt": RECEIPT,
            "notes": {"booking": "BK-7F3K2Q9M"},
        }
        assert isinstance(body["amount"], int)

    asyncio.run(scenario())


def test_a_repeated_receipt_finds_the_first_order_instead_of_making_another() -> None:
    async def scenario() -> None:
        other = {**ORDER, "id": "order_other", "receipt": f"{RECEIPT}-longer"}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(400, json=DUPLICATE)
            assert request.url.params["receipt"] == RECEIPT
            return httpx.Response(
                200, json={"entity": "collection", "count": 2, "items": [other, ORDER]}
            )

        order = await _gateway(handler).create_order(amount_paise=TOKEN, receipt=RECEIPT, notes={})

        assert order.id == ORDER["id"]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "found",
    [
        httpx.Response(200, json={"entity": "collection", "count": 0, "items": []}),
        httpx.Response(200, content=b"not json"),
        httpx.Response(401, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "no"}}),
    ],
)
def test_a_repeated_receipt_that_cant_be_found_is_a_failure(found: httpx.Response) -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json=DUPLICATE) if request.method == "POST" else found

        with pytest.raises(PaymentGatewayUnavailableError):
            await _gateway(handler).create_order(amount_paise=TOKEN, receipt=RECEIPT, notes={})

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(
            401, json={"error": {"code": "BAD_REQUEST_ERROR", "description": "bad key"}}
        ),
        httpx.Response(500, json={"error": {"code": "SERVER_ERROR", "description": "oops"}}),
        httpx.Response(502, content=b"<html>bad gateway</html>"),
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json={"id": "order_without_an_amount"}),
    ],
)
def test_an_order_the_gateway_wont_make_is_a_failure(answer: httpx.Response) -> None:
    async def scenario() -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return answer

        with pytest.raises(PaymentGatewayUnavailableError):
            await _gateway(handler).create_order(amount_paise=TOKEN, receipt=RECEIPT, notes={})

    asyncio.run(scenario())


def test_a_lost_connection_is_a_failure_and_making_an_order_isnt_tried_again() -> None:
    async def scenario() -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ConnectTimeout("no answer", request=request)

        with pytest.raises(PaymentGatewayUnavailableError):
            await _gateway(handler).create_order(amount_paise=TOKEN, receipt=RECEIPT, notes={})
        assert calls == 1

    asyncio.run(scenario())


def test_a_fetched_payment_says_what_the_gateway_said() -> None:
    async def scenario() -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=PAYMENT)

        found = await _gateway(handler).fetch_payment("pay_DG4ZdRK8ZnXC3k")

        assert found == GatewayPayment(
            "pay_DG4ZdRK8ZnXC3k", "order_RB58MiP5SPFYyM", TOKEN, "INR", GatewayStatus.CAPTURED
        )
        assert (seen[0].method, str(seen[0].url)) == ("GET", f"{API}/payments/pay_DG4ZdRK8ZnXC3k")

    asyncio.run(scenario())


def test_a_payment_with_no_order_has_none() -> None:
    async def scenario() -> None:
        answer = {**PAYMENT, "order_id": None}
        found = await _gateway(_answering(200, answer)).fetch_payment("pay_1")
        assert found.order_id is None

    asyncio.run(scenario())


@pytest.mark.parametrize("failing", [500, 503, 429])
def test_a_fetch_is_tried_again_when_the_failure_may_pass(failing: int) -> None:
    async def scenario() -> None:
        answers = [httpx.Response(failing, json={}), httpx.Response(200, json=PAYMENT)]

        def handler(_request: httpx.Request) -> httpx.Response:
            return answers.pop(0)

        assert (await _gateway(handler).fetch_payment("pay_1")).status is GatewayStatus.CAPTURED
        assert not answers

    asyncio.run(scenario())


def test_a_fetch_is_tried_again_after_a_lost_connection_then_gives_up() -> None:
    async def scenario() -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ReadTimeout("no answer", request=request)

        with pytest.raises(PaymentGatewayUnavailableError):
            await _gateway(handler).fetch_payment("pay_1")
        assert calls == FETCH_ATTEMPTS

    asyncio.run(scenario())


def test_a_fetch_that_keeps_failing_gives_up() -> None:
    async def scenario() -> None:
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(503, json={})

        with pytest.raises(PaymentGatewayUnavailableError):
            await _gateway(handler).fetch_payment("pay_1")
        assert calls == FETCH_ATTEMPTS

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(400, json=UNKNOWN),
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json={**PAYMENT, "status": "something_new"}),
    ],
)
def test_an_answer_that_cant_be_read_isnt_taken_as_anything(answer: httpx.Response) -> None:
    async def scenario() -> None:
        calls = 0

        def handler(_request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return answer

        with pytest.raises(PaymentGatewayUnavailableError):
            await _gateway(handler).fetch_payment("pay_1")
        assert calls == 1

    asyncio.run(scenario())


def test_a_checkout_signature_is_checked_against_the_keys_secret() -> None:
    gateway = _gateway(_nothing)
    good = checkout_signature(KEY_SECRET, order_id="order_1", payment_id="pay_1")

    assert gateway.verify_checkout_signature(order_id="order_1", payment_id="pay_1", signature=good)
    assert not gateway.verify_checkout_signature(
        order_id="order_2", payment_id="pay_1", signature=good
    )
    assert not gateway.verify_checkout_signature(
        order_id="order_1", payment_id="pay_2", signature=good
    )
    assert not gateway.verify_checkout_signature(
        order_id="order_1",
        payment_id="pay_1",
        signature=checkout_signature("another-secret", order_id="order_1", payment_id="pay_1"),
    )


def test_a_webhook_is_checked_on_its_raw_body_against_its_own_secret() -> None:
    gateway = _gateway(_nothing)
    body = b'{"event":"payment.captured"}'
    good = webhook_signature(WEBHOOK_SECRET, body)

    assert gateway.verify_webhook(raw_body=body, signature=good)
    assert not gateway.verify_webhook(raw_body=body + b" ", signature=good)
    assert not gateway.verify_webhook(raw_body=body, signature=webhook_signature(KEY_SECRET, body))


def test_the_fake_gateway_signs_like_the_real_one_and_needs_no_memory() -> None:
    async def scenario() -> None:
        gateway: PaymentGateway = FakeGateway()
        order = await gateway.create_order(amount_paise=TOKEN, receipt=RECEIPT, notes={})
        again = await FakeGateway().create_order(amount_paise=TOKEN, receipt=RECEIPT, notes={})
        assert order == again
        assert order == GatewayOrder(order.id, TOKEN, "INR")

        fake = FakeGateway()
        proof = fake.checkout(order.id)
        assert gateway.verify_checkout_signature(
            order_id=order.id, payment_id=proof.payment_id, signature=proof.signature
        )
        assert not gateway.verify_checkout_signature(
            order_id="order_fake_1_0", payment_id=proof.payment_id, signature=proof.signature
        )

        found = await gateway.fetch_payment(proof.payment_id)
        assert found == GatewayPayment(
            proof.payment_id, order.id, TOKEN, "INR", GatewayStatus.CAPTURED
        )

    asyncio.run(scenario())


def test_the_fake_gateway_says_what_a_test_tells_it_and_can_be_out_of_reach() -> None:
    async def scenario() -> None:
        fake = FakeGateway()
        order = await fake.create_order(amount_paise=TOKEN, receipt=RECEIPT, notes={})
        payment = fake.checkout(order.id).payment_id

        fake.say(payment, status=GatewayStatus.AUTHORIZED)
        assert (await fake.fetch_payment(payment)).status is GatewayStatus.AUTHORIZED
        fake.say(payment, amount_paise=1, order_id="order_other", currency="USD")
        found = await fake.fetch_payment(payment)
        assert (found.amount_paise, found.order_id, found.currency) == (1, "order_other", "USD")

        fake.unreachable = True
        with pytest.raises(PaymentGatewayUnavailableError):
            await fake.fetch_payment(payment)
        with pytest.raises(PaymentGatewayUnavailableError):
            await fake.create_order(amount_paise=TOKEN, receipt=RECEIPT, notes={})

    asyncio.run(scenario())


def test_the_fake_gateway_knows_no_payment_it_didnt_make() -> None:
    async def scenario() -> None:
        with pytest.raises(PaymentGatewayUnavailableError):
            await FakeGateway().fetch_payment("pay_DG4ZdRK8ZnXC3k")

    asyncio.run(scenario())


def test_the_fake_gateway_signs_webhooks_in_razorpays_shape() -> None:
    async def scenario() -> None:
        fake = FakeGateway()
        order = await fake.create_order(amount_paise=TOKEN, receipt=RECEIPT, notes={})
        payment = await fake.fetch_payment(fake.checkout(order.id).payment_id)

        at = datetime(2027, 7, 14, 10, 0, tzinfo=UTC)
        sent = fake.webhook("payment.captured", payment, at=at, event_id="evt_1")

        assert sent.event_id == "evt_1"
        assert fake.verify_webhook(raw_body=sent.raw_body, signature=sent.signature)
        assert not fake.verify_webhook(raw_body=sent.raw_body + b" ", signature=sent.signature)
        body = json.loads(sent.raw_body)
        assert body["event"] == "payment.captured"
        assert body["payload"]["payment"]["entity"] == {
            "id": payment.id,
            "entity": "payment",
            "amount": TOKEN,
            "currency": "INR",
            "status": "captured",
            "order_id": order.id,
            # What a real one holds, so tests can see it isn't kept.
            "method": "upi",
            "vpa": "a.student@fakebank",
            "email": "a.student@example.com",
            "contact": "+919000000000",
        }
        assert fake.webhook("payment.captured", payment, at=at).event_id.startswith("evt_fake_")
        assert fake.read_webhook(sent.raw_body) == GatewayEvent("payment.captured", at, payment)

    asyncio.run(scenario())
