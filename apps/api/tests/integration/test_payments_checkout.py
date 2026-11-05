"""Paying a booking's token through checkout (step 6.1, ADR 0056): an order for exactly the token,
made when the student asks and only once; a signature that proves where checkout's answer came
from; and only the gateway's own word that the money is in moving the booking, once."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.config import Settings
from app.core.audit import AuditLog
from app.modules.identity.domain.sessions import SessionKind
from app.modules.payments.adapters.fake import FakeGateway
from app.modules.payments.adapters.razorpay import RazorpayGateway
from app.modules.payments.domain.payments import GatewayStatus
from app.modules.payments.domain.signatures import checkout_signature
from app.modules.payments.models import Payment
from app.modules.payments.router import CHECKOUTS_PER_USER, STARTS_PER_USER
from app.modules.payments.service import payments_part
from tests.flags import FixedFlags
from tests.integration.test_booking_confirmation import _about, _booking, _held, _history
from tests.integration.test_booking_holds import _listing, _student
from tests.integration.test_booking_student import _again
from tests.jobs import RecordedTexts, run_due_jobs
from tests.metrics import totals
from tests.staff_api import NOW, Staff, run_as_staff

pytestmark = pytest.mark.integration

TOKEN = 200_000
HOLD = timedelta(minutes=15)


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)

        async def remote_booking(ops: Staff) -> Any:
            ops.app.state.flags = FixedFlags(remote_booking_enabled=True)
            return await scenario(ops)

        return run_as_staff(settings, remote_booking)

    return run_scenario


def _gateway(ops: Staff) -> FakeGateway:
    gateway: FakeGateway = ops.app.state.payment_gateway
    return gateway


async def _start(student: Staff, code: str) -> dict[str, Any]:
    return await student.ok("POST", f"/v1/bookings/{code}/payment")


async def _bank_says_yes(student: Staff, start: dict[str, Any]) -> dict[str, Any]:
    return await student.ok("POST", f"/v1/payments/{start['id']}/test-checkout")


async def _callback(student: Staff, start: dict[str, Any], proof: dict[str, Any]) -> httpx.Response:
    return await student.call("POST", f"/v1/payments/{start['id']}/checkout-callback", json=proof)


async def _pay(student: Staff, start: dict[str, Any]) -> dict[str, Any]:
    response = await _callback(student, start, await _bank_says_yes(student, start))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _held_booking(ops: Staff) -> tuple[Staff, str]:
    student, held = await _held(ops, await _listing(ops, beds=1))
    code: str = held["code"]
    return student, code


async def _payment(ops: Staff, start: dict[str, Any]) -> Payment:
    async with ops.app.state.sessionmaker() as db:
        found: Payment | None = await db.scalar(
            select(Payment).where(Payment.public_id == start["id"])
        )
        assert found is not None
        return found


async def _audited(ops: Staff, start: dict[str, Any]) -> list[str]:
    async with ops.app.state.sessionmaker() as db:
        rows = await db.scalars(
            select(AuditLog.action)
            .where(AuditLog.entity_type == "payment", AuditLog.entity_id == start["id"])
            .order_by(AuditLog.id)
        )
        return list(rows)


def test_a_student_pays_their_token_and_the_booking_waits_for_the_owner(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        before = {
            "orders": totals("payments.orders"),
            "checkouts": totals("payments.checkouts"),
        }
        seen: dict[str, Any] = {"before": await student.ok("GET", f"/v1/bookings/{code}")}
        start = await _start(student, code)
        seen["start"] = start
        seen["waiting"] = await _payment(ops, start)
        seen["paid"] = await _pay(student, start)
        seen["after"] = await student.ok("GET", f"/v1/bookings/{code}")
        seen["payment"] = await _payment(ops, start)
        seen["audit"] = await _audited(ops, start)
        seen["history"] = await _history(ops, code)
        seen["again"] = await student.call("POST", f"/v1/bookings/{code}/payment")
        texts = RecordedTexts()
        await run_due_jobs(ops.app, texts=texts)
        seen["texts"] = [template for template, _ in _about(texts, code)]
        seen["code"] = code
        seen["metrics"] = (
            before,
            {"orders": totals("payments.orders"), "checkouts": totals("payments.checkouts")},
        )
        return seen

    seen = run(scenario)

    code, start = seen["code"], seen["start"]
    assert seen["before"]["canPay"] is True
    # Exactly the booking's token, and the server's word for it.
    assert seen["before"]["tokenPaise"] == TOKEN
    assert start["amountPaise"] == TOKEN
    assert start["currency"] == "INR"
    assert start["booking"] == code
    assert start["provider"] == "fake"
    assert start["keyId"] == "fake_key"
    assert start["orderId"].startswith("order_fake_")
    # Checkout closes itself when the hold ends.
    assert start["expiresInSeconds"] == HOLD.total_seconds()
    assert start["prefill"]["contact"].startswith("+91")
    waiting = seen["waiting"]
    assert (waiting.status, waiting.amount_paise, waiting.provider) == ("created", TOKEN, "fake")
    assert (waiting.provider_payment_id, waiting.captured_at) == (None, None)
    assert (waiting.purpose, waiting.mode) == ("token", "payment")
    assert seen["paid"] == {"outcome": "paid", "booking": code}
    assert seen["after"]["status"] == "token_secured"
    assert seen["after"]["canPay"] is False
    payment = seen["payment"]
    assert payment.status == "captured"
    assert payment.captured_at == NOW
    assert payment.provider_payment_id.startswith("pay_fake_")
    assert seen["audit"] == ["payment.order_created", "payment.captured"]
    assert seen["history"] == [("hold", "student"), ("token_secured", "system")]
    assert seen["again"].json()["code"] == "INVALID_TRANSITION"
    assert seen["texts"] == ["booking_token_in"]
    before, after = seen["metrics"]
    orders = frozenset({("provider", "fake")})
    assert after["orders"][orders] - before["orders"].get(orders, 0) == 1
    paid = frozenset({("outcome", "paid")})
    assert after["checkouts"][paid] - before["checkouts"].get(paid, 0) == 1


def test_a_pg_that_confirms_itself_confirms_as_the_token_comes_in(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=1)
        await ops.ok("PATCH", f"/v1/ops/properties/{listing['id']}", json={"instantConfirm": True})
        student, held = await _held(ops, listing)
        await _pay(student, await _start(student, held["code"]))
        booking = await student.ok("GET", f"/v1/bookings/{held['code']}")
        return {"status": booking["status"], "history": await _history(ops, held["code"])}

    assert run(scenario) == {
        "status": "confirmed",
        "history": [("hold", "student"), ("token_secured", "system"), ("confirm", "system")],
    }


def test_asking_again_gets_the_same_order_even_at_once(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        at_once = await asyncio.gather(*[_start(student, code) for _ in range(4)])
        made = _gateway(ops).orders_made
        again = await _start(student, code)
        async with ops.app.state.sessionmaker() as db:
            rows = await db.scalars(select(Payment).where(Payment.public_id == again["id"]))
            found = list(rows)
        return {
            "at once": at_once,
            "again": again,
            "calls after the first": _gateway(ops).orders_made - made,
            "rows": len(found),
            "audit": await _audited(ops, again),
        }

    seen = run(scenario)

    assert {start["id"] for start in seen["at once"]} == {seen["again"]["id"]}
    assert {start["orderId"] for start in seen["at once"]} == {seen["again"]["orderId"]}
    assert seen["calls after the first"] == 0
    assert seen["rows"] == 1
    assert seen["audit"] == ["payment.order_created"]


def test_what_checkout_handed_over_can_be_sent_again_and_moves_the_booking_once(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        proof = await _bank_says_yes(student, start)
        at_once = await asyncio.gather(*[_callback(student, start, proof) for _ in range(4)])
        later = await _callback(student, start, proof)
        return {
            "at once": [response.json()["outcome"] for response in at_once],
            "later": later.json()["outcome"],
            "history": await _history(ops, code),
            "audit": await _audited(ops, start),
        }

    assert run(scenario) == {
        "at once": ["paid"] * 4,
        "later": "paid",
        "history": [("hold", "student"), ("token_secured", "system")],
        "audit": ["payment.order_created", "payment.captured"],
    }


def test_a_signature_the_gateway_didnt_make_moves_nothing(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        good = await _bank_says_yes(student, start)
        # Another booking's real proof, against this payment.
        other, other_code = await _held_booking(ops)
        theirs = await _bank_says_yes(other, await _start(other, other_code))
        answers = [
            await _callback(student, start, {**good, "signature": "a" * 64}),
            await _callback(student, start, {**good, "providerPaymentId": "pay_fake_1_0"}),
            await _callback(student, start, theirs),
        ]
        malformed = [
            await _callback(student, start, {**good, "signature": "not hex"}),
            await _callback(student, start, {**good, "providerPaymentId": "../../orders"}),
            await _callback(student, start, {**good, "amountPaise": 1}),
        ]
        return {
            "answers": [(answer.status_code, answer.json()["code"]) for answer in answers],
            "malformed": [answer.status_code for answer in malformed],
            "status": (await student.ok("GET", f"/v1/bookings/{code}"))["status"],
            "payment": (await _payment(ops, start)).status,
        }

    assert run(scenario) == {
        "answers": [(400, "PAYMENT_SIGNATURE_INVALID")] * 3,
        "malformed": [422, 422, 422],
        "status": "held",
        "payment": "created",
    }


def test_a_payment_that_isnt_this_orders_token_moves_nothing(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        proof = await _bank_says_yes(student, start)
        answers = []
        for change in (
            {"amount_paise": TOKEN - 1},
            {"amount_paise": TOKEN + 1},
            {"order_id": "order_someone_elses"},
            {"currency": "USD"},
        ):
            _gateway(ops).say(proof["providerPaymentId"], **change)
            answer = await _callback(student, start, proof)
            answers.append((answer.status_code, answer.json()["code"]))
        return {
            "answers": answers,
            "status": (await student.ok("GET", f"/v1/bookings/{code}"))["status"],
            "payment": (await _payment(ops, start)).status,
            "audit": await _audited(ops, start),
        }

    assert run(scenario) == {
        "answers": [(409, "PAYMENT_MISMATCH")] * 4,
        "status": "held",
        "payment": "created",
        "audit": ["payment.order_created", *["payment.mismatch"] * 4],
    }


def test_only_money_in_moves_a_booking(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        proof = await _bank_says_yes(student, start)
        payment_id = proof["providerPaymentId"]
        gateway = _gateway(ops)

        async def status() -> str:
            booking = await student.ok("GET", f"/v1/bookings/{code}")
            found: str = booking["status"]
            return found

        async def outcome(*, say: GatewayStatus | None) -> str:
            if say is not None:
                gateway.say(payment_id, status=say)
            answer = await _callback(student, start, proof)
            assert answer.status_code == 200, answer.text
            found: str = answer.json()["outcome"]
            return found

        seen: dict[str, Any] = {}
        seen["failed"] = (await outcome(say=GatewayStatus.FAILED), await status())
        seen["failed, ours"] = (await _payment(ops, start)).status
        seen["refunded"] = (await outcome(say=GatewayStatus.REFUNDED), await status())
        seen["authorized"] = (await outcome(say=GatewayStatus.AUTHORIZED), await status())
        authorized = await _payment(ops, start)
        seen["authorized, ours"] = (authorized.status, authorized.provider_payment_id == payment_id)
        gateway.unreachable = True
        seen["out of reach"] = (await outcome(say=None), await status())
        gateway.unreachable = False
        # A slower answer can't take it back.
        seen["created"] = (await outcome(say=GatewayStatus.CREATED), await status())
        seen["created, ours"] = (await _payment(ops, start)).status
        seen["captured"] = (await outcome(say=GatewayStatus.CAPTURED), await status())
        seen["captured, ours"] = (await _payment(ops, start)).status
        return seen

    assert run(scenario) == {
        "failed": ("not_paid", "held"),
        "failed, ours": "created",
        "refunded": ("not_paid", "held"),
        "authorized": ("waiting", "held"),
        "authorized, ours": ("authorized", True),
        "out of reach": ("waiting", "held"),
        "created": ("waiting", "held"),
        "created, ours": "authorized",
        "captured": ("paid", "token_secured"),
        "captured, ours": "captured",
    }


def test_a_gateway_out_of_reach_leaves_a_hold_to_try_again(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        _gateway(ops).unreachable = True
        down = await student.call("POST", f"/v1/bookings/{code}/payment")
        held = await student.ok("GET", f"/v1/bookings/{code}")
        _gateway(ops).unreachable = False
        start = await _start(student, code)
        paid = await _pay(student, start)
        return {
            "down": (down.status_code, down.json()["code"]),
            "held": held["status"],
            "paid": paid["outcome"],
        }

    assert run(scenario) == {
        "down": (503, "PAYMENT_GATEWAY_UNAVAILABLE"),
        "held": "held",
        "paid": "paid",
    }


def test_a_hold_with_no_time_left_takes_no_new_payment(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        clock = ops.app.state.clock
        clock.advance(HOLD - timedelta(seconds=90))
        late = await _start(student, code)
        clock.advance(timedelta(seconds=90))
        student = await _again(student)
        over = await student.call("POST", f"/v1/bookings/{code}/payment")
        booking = await student.ok("GET", f"/v1/bookings/{code}")
        return {
            "seconds left": late["expiresInSeconds"],
            "over": (over.status_code, over.json()["code"]),
            "status": booking["status"],
            "can pay": booking["canPay"],
        }

    assert run(scenario) == {
        "seconds left": 90,
        "over": (409, "INVALID_TRANSITION"),
        # The job hasn't ended it yet, but its time is up.
        "status": "held",
        "can pay": False,
    }


def test_a_payment_under_way_when_the_hold_runs_out_still_counts_while_its_held(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        proof = await _bank_says_yes(student, start)
        ops.app.state.clock.advance(HOLD + timedelta(seconds=1))
        student = await _again(student)
        answer = await _callback(student, start, proof)
        return {
            "outcome": answer.json()["outcome"],
            "status": (await student.ok("GET", f"/v1/bookings/{code}"))["status"],
        }

    assert run(scenario) == {"outcome": "paid", "status": "token_secured"}


def test_a_token_after_the_booking_moved_on_is_kept_and_moves_nothing(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        proof = await _bank_says_yes(student, start)
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": 0})
        first = await _callback(student, start, proof)
        again = await _callback(student, start, proof)
        return {
            "outcomes": [first.json()["outcome"], again.json()["outcome"]],
            "status": (await student.ok("GET", f"/v1/bookings/{code}"))["status"],
            "payment": (await _payment(ops, start)).status,
            "audit": await _audited(ops, start),
            "history": await _history(ops, code),
        }

    assert run(scenario) == {
        "outcomes": ["late", "late"],
        "status": "cancelled",
        # Step 6.2 takes it from here: revive the booking, or refund the money (§7.4).
        "payment": "captured",
        "audit": ["payment.order_created", "payment.captured", "payment.late"],
        "history": [("hold", "student"), ("cancel", "student")],
    }


def test_a_replayed_checkout_says_paid_after_the_booking_has_moved_on_with_the_token(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        proof = await _bank_says_yes(student, start)
        await _callback(student, start, proof)
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": TOKEN})
        answer = await _callback(student, start, proof)
        return {
            "outcome": answer.json()["outcome"],
            "status": (await student.ok("GET", f"/v1/bookings/{code}"))["status"],
        }

    assert run(scenario) == {"outcome": "paid", "status": "cancelled"}


def test_someone_elses_payment_is_a_404(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> list[int]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        proof = await _bank_says_yes(student, start)
        other = await _student(ops)
        return [
            (await other.call("POST", f"/v1/bookings/{code}/payment")).status_code,
            (await other.call("POST", f"/v1/payments/{start['id']}/test-checkout")).status_code,
            (await _callback(other, start, proof)).status_code,
            (await ops.call("POST", f"/v1/bookings/{code}/payment")).status_code,
        ]

    assert run(scenario) == [404, 404, 404, 403]


def test_a_payment_with_no_order_yet_has_nothing_to_pay_or_verify(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        _gateway(ops).unreachable = True
        await student.call("POST", f"/v1/bookings/{code}/payment")
        _gateway(ops).unreachable = False
        async with ops.app.state.sessionmaker() as db:
            booking = await _booking(ops, code)
            found = await db.scalar(select(Payment).where(Payment.booking_id == booking.id))
            assert found is not None
            public_id = str(found.public_id)
        pending = {"id": public_id}
        test_bank = await student.call("POST", f"/v1/payments/{public_id}/test-checkout")
        callback = await _callback(
            student, pending, {"providerPaymentId": "pay_fake_1_0", "signature": "a" * 64}
        )
        return {
            "test bank": (test_bank.status_code, test_bank.json()["code"]),
            "callback": (callback.status_code, callback.json()["code"]),
        }

    assert run(scenario) == {
        "test bank": (409, "INVALID_TRANSITION"),
        "callback": (400, "PAYMENT_SIGNATURE_INVALID"),
    }


def test_the_limits_on_starting_and_finishing(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        proof = await _bank_says_yes(student, start)
        limiter = ops.app.state.rate_limiter
        subject = f"user:{student.user_id}"
        for _ in range(STARTS_PER_USER.limit - 1):
            await limiter.hit(STARTS_PER_USER, subject)
        for _ in range(CHECKOUTS_PER_USER.limit):
            await limiter.hit(CHECKOUTS_PER_USER, subject)
        started = await student.call("POST", f"/v1/bookings/{code}/payment")
        finished = await _callback(student, start, proof)
        return {
            "starting": (started.status_code, started.json()["code"]),
            "finishing": (finished.status_code, finished.json()["code"]),
        }

    assert run(scenario) == {
        "starting": (429, "RATE_LIMITED"),
        "finishing": (429, "RATE_LIMITED"),
    }


def test_the_whole_way_with_razorpays_adapter_and_no_test_bank(run: Callable[..., Any]) -> None:
    """Razorpay's own requests and answers, over a stand-in for its API: what staging will do once
    it has test keys. A booking that had a fake order gets a new one at the real gateway."""
    key_secret = "a-test-key-secret"
    orders: list[dict[str, Any]] = []
    payment_id = "pay_DG4ZdRK8ZnXC3k"

    def razorpay(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = httpx.Response(200, content=request.content).json()
            order = {"id": "order_RB58MiP5SPFYyM", "currency": "INR", **body}
            orders.append(order)
            return httpx.Response(200, json=order)
        return httpx.Response(
            200,
            json={
                "id": payment_id,
                "order_id": orders[-1]["id"],
                "amount": orders[-1]["amount"],
                "currency": "INR",
                "status": "captured",
            },
        )

    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        fake_start = await _start(student, code)
        fake_proof = await _bank_says_yes(student, fake_start)
        ops.app.state.payment_gateway = RazorpayGateway(
            httpx.AsyncClient(transport=httpx.MockTransport(razorpay)),
            key_id="rzp_test_1DP5mmOlF5G5ag",
            key_secret=SecretStr(key_secret),
            webhook_secret=None,
            retry_delay_s=0,
        )
        start = await _start(student, code)
        test_bank = await student.call("POST", f"/v1/payments/{start['id']}/test-checkout")
        old_proof = await _callback(student, fake_start, fake_proof)
        answer = await _callback(
            student,
            start,
            {
                "providerPaymentId": payment_id,
                "signature": checkout_signature(
                    key_secret, order_id=start["orderId"], payment_id=payment_id
                ),
            },
        )
        return {
            "new payment": start["id"] != fake_start["id"],
            "start": (start["provider"], start["keyId"], start["orderId"], start["amountPaise"]),
            "order": {
                key: orders[0].get(key) for key in ("amount", "currency", "receipt", "notes")
            },
            "no test bank": test_bank.status_code,
            "a fake proof": old_proof.json()["code"],
            "answer": answer.json(),
            "status": (await student.ok("GET", f"/v1/bookings/{code}"))["status"],
            "code": code,
        }

    seen = run(scenario)

    code = seen["code"]
    assert seen["new payment"] is True
    assert seen["start"] == ("razorpay", "rzp_test_1DP5mmOlF5G5ag", "order_RB58MiP5SPFYyM", TOKEN)
    assert seen["order"] == {
        "amount": TOKEN,
        "currency": "INR",
        "receipt": f"token-{code}",
        "notes": {"booking": code, "purpose": "token"},
    }
    assert seen["no test bank"] == 404
    assert seen["a fake proof"] == "PAYMENT_SIGNATURE_INVALID"
    assert seen["answer"] == {"outcome": "paid", "booking": code}
    assert seen["status"] == "token_secured"


def test_a_students_payments_are_in_their_data_export(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        await _pay(student, start)
        other = await _student(ops)
        async with ops.app.state.sessionmaker() as db:
            return {
                "theirs": await payments_part(db, student.user_id),
                "nobody's": await payments_part(db, other.user_id),
                "code": code,
                "payment": (await _payment(ops, start)).provider_payment_id,
            }

    seen = run(scenario)

    assert seen["nobody's"] == {}
    assert seen["theirs"] == {
        "payments": [
            {
                "booking": seen["code"],
                "purpose": "token",
                "amountPaise": TOKEN,
                "status": "captured",
                "gateway": "fake",
                "gatewayPaymentId": seen["payment"],
                "madeAt": seen["theirs"]["payments"][0]["madeAt"],
                "capturedAt": NOW.isoformat(),
            }
        ]
    }


def test_staff_sessions_dont_pay(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> int:
        _, code = await _held_booking(ops)
        ops = await _again(ops, kind=SessionKind.STAFF)
        return (await ops.call("POST", f"/v1/bookings/{code}/payment")).status_code

    assert run(scenario) == 403
