"""Tokens blocked by a UPI one-time mandate (step 6.7, ADR 0064): blocked, not taken, at
reservation; debited once, after the notice, when the booking settles; released when it ends first,
or debited for only what a late cancellation keeps. A move-in too far off, or the flag off, takes a
normal payment."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.config import Settings
from app.core.outbox import enqueue
from app.modules.booking.jobs import CHECK_WINDOWS
from app.modules.identity.domain.sessions import SessionKind
from app.modules.payments.domain.mandates import MandateStatus
from app.modules.payments.domain.payments import INR, GatewayPayment, GatewayStatus
from app.modules.payments.models import ReconciliationIssue
from app.modules.payments.service import Mandates
from tests.flags import FixedFlags
from tests.integration.test_booking_check_in import MOVED_IN
from tests.integration.test_booking_student import _again
from tests.integration.test_ledger import REASON, _balances, _kinds
from tests.integration.test_payment_webhooks import _send
from tests.integration.test_payments_checkout import (
    TOKEN,
    _bank_says_yes,
    _callback,
    _gateway,
    _held_booking,
    _payment,
    _start,
)
from tests.jobs import run_due_jobs
from tests.staff_api import Staff, run_as_staff

pytestmark = pytest.mark.integration


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Any], *, mode: str = "upi_mandate") -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)

        async def mandates(ops: Staff) -> Any:
            ops.app.state.flags = FixedFlags(remote_booking_enabled=True, token_mode=mode)
            await run_due_jobs(ops.app)  # what other tests left waiting
            return await scenario(ops)

        return run_as_staff(settings, mandates)

    return run_scenario


async def _blocked(ops: Staff) -> tuple[Staff, str, dict[str, Any]]:
    """A held booking whose student authorised the block at the test bank."""
    student, code = await _held_booking(ops)
    start = await _start(student, code)
    answer = await _callback(student, start, await _bank_says_yes(student, start))
    assert answer.status_code == 200, answer.text
    assert answer.json()["outcome"] == "paid"
    return student, code, start


async def _issues(ops: Staff, booking: str) -> list[str]:
    async with ops.app.state.sessionmaker() as db:
        rows = await db.scalars(
            select(ReconciliationIssue.kind).where(ReconciliationIssue.booking_code == booking)
        )
        return list(rows)


def test_a_token_is_blocked_at_reservation_and_debited_once_the_booking_settles(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code, start = await _blocked(ops)
        seen: dict[str, Any] = {
            "start": (start["mode"], start["customerId"] is not None),
            "blocked": (await _payment(ops, start)).status,
            "booking": (await student.ok("GET", f"/v1/bookings/{code}"))["status"],
            "books while blocked": await _balances(ops, code),
        }
        # Confirmed, moved in, and the 24 hours over: the booking settles.
        await ops.ok("POST", f"/v1/ops/bookings/{code}/confirm", json=REASON)
        ops.app.state.clock.set(MOVED_IN)
        student = await _again(student)
        await student.ok("POST", f"/v1/bookings/{code}/check-in")
        ops.app.state.clock.advance(timedelta(hours=24))
        async with ops.app.state.sessionmaker() as db, db.begin():
            await enqueue(db, CHECK_WINDOWS, {}, clock=ops.app.state.clock)
        await run_due_jobs(ops.app)
        due = await _payment(ops, start)
        seen["notice"] = (due.debit_amount_paise, due.provider_debit_order_id is not None)
        seen["debited during the notice"] = list(_gateway(ops).debits_made)
        ops.app.state.clock.advance(timedelta(hours=27))
        await run_due_jobs(ops.app)
        sent = await _payment(ops, start)
        assert sent.provider_payment_id is not None
        seen["debited after it"] = list(_gateway(ops).debits_made)
        debit = await _gateway(ops).fetch_payment(sent.provider_payment_id)
        ops = await _again(ops, kind=SessionKind.STAFF)
        answer = await _send(
            ops, _gateway(ops).webhook("payment.captured", debit, at=ops.app.state.clock.now())
        )
        assert answer.status_code == 200, answer.text
        await run_due_jobs(ops.app)
        seen["captured"] = (await _payment(ops, start)).status
        seen["kinds"] = await _kinds(ops, code)
        return seen

    seen = run(scenario)

    assert seen["start"] == ("upi_mandate", True)
    assert seen["blocked"] == "blocked"
    assert seen["booking"] == "token_secured"
    # Nothing moved while it was only blocked.
    assert seen["books while blocked"] == {}
    assert seen["notice"] == (TOKEN, True)
    assert seen["debited during the notice"] == []
    assert len(seen["debited after it"]) == 1
    assert seen["captured"] == "captured"
    assert "token_received" in seen["kinds"]


def test_a_booking_that_ends_first_gives_the_whole_block_back(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code, start = await _blocked(ops)
        mandate = (await _payment(ops, start)).provider_mandate_id
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": TOKEN})
        await run_due_jobs(ops.app)
        payment = await _payment(ops, start)
        return {
            "status": payment.status,
            "released": mandate in _gateway(ops).released,
            "debited": _gateway(ops).debits_made,
            "books": await _balances(ops, code),
        }

    assert run(scenario) == {"status": "released", "released": True, "debited": [], "books": {}}


def test_a_late_cancellation_debits_only_what_it_keeps(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        _, _, start = await _blocked(ops)
        async with ops.app.state.sessionmaker() as db, db.begin():
            payment = await _locked(db, start)
            await Mandates(db, ops.app.state.clock).give_back(
                payment, refund_paise=50_000, reason="cancel_late"
            )
        found = await _payment(ops, start)
        return {"status": found.status, "debit": found.debit_amount_paise}

    assert run(scenario) == {"status": "blocked", "debit": TOKEN - 50_000}


async def _locked(db: Any, start: dict[str, Any]) -> Any:
    from app.modules.payments.models import Payment  # noqa: PLC0415 - a test's own lookup

    return await db.scalar(
        select(Payment).where(Payment.public_id == start["id"]).with_for_update()
    )


def test_a_move_in_too_far_off_or_the_flag_off_takes_a_normal_payment(
    run: Callable[..., Any],
) -> None:
    async def too_far(ops: Staff) -> str:
        ops.app.state.upi_mandate_max_days = 1
        student, code = await _held_booking(ops)
        return str((await _start(student, code))["mode"])

    async def flag_off(ops: Staff) -> str:
        student, code = await _held_booking(ops)
        return str((await _start(student, code))["mode"])

    assert run(too_far) == "payment"
    assert run(flag_off, mode="payment") == "payment"


def test_the_gateways_word_alone_blocks_in_whichever_order_its_webhooks_come(
    run: Callable[..., Any],
) -> None:
    async def blocked(ops: Staff, *, mandate_first: bool) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        gateway = _gateway(ops)
        proof = gateway.checkout(start["orderId"])
        token = (await gateway.fetch_payment(proof.payment_id)).token_id
        assert token is not None
        now = ops.app.state.clock.now
        check = f"/v1/payments/{start['id']}/mandate-check"
        seen: dict[str, Any] = {"check before": (await student.ok("POST", check))["outcome"]}
        # The authorisation's own event names the mandate; the mandate's event confirms it.
        dummy = GatewayPayment(
            proof.payment_id, start["orderId"], TOKEN, INR, GatewayStatus.FAILED, token_id=token
        )
        named = gateway.webhook("payment.failed", dummy, at=now())
        confirmed = gateway.mandate_webhook(
            "token.confirmed", token, MandateStatus.CONFIRMED, at=now()
        )
        if mandate_first:
            # Nothing names this mandate yet; once its payment's event does, the gateway is asked.
            await _send(ops, confirmed)
            await run_due_jobs(ops.app)
            seen["one in"] = (await _payment(ops, start)).status
            await _send(ops, named)
        else:
            # Named while the student is still approving: the confirmation moves it.
            gateway.mandates_said[token] = MandateStatus.INITIATED
            await _send(ops, named)
            await run_due_jobs(ops.app)
            seen["one in"] = (await _payment(ops, start)).status
            gateway.mandates_said[token] = MandateStatus.CONFIRMED
            await _send(ops, confirmed)
        await run_due_jobs(ops.app)
        seen["both in"] = (await _payment(ops, start)).status
        seen["booking"] = (await student.ok("GET", f"/v1/bookings/{code}"))["status"]
        gateway.order_attempts[start["orderId"]] = [dummy]
        seen["check after"] = (await student.ok("POST", check))["outcome"]
        return seen

    async def scenario(ops: Staff) -> list[dict[str, Any]]:
        return [
            await blocked(ops, mandate_first=True),
            await blocked(ops, mandate_first=False),
        ]

    expected = {
        "check before": "waiting",
        "one in": "created",
        "both in": "blocked",
        "booking": "token_secured",
        "check after": "paid",
    }
    assert run(scenario) == [expected, expected]


def test_a_mandate_cancelled_before_its_debit_or_a_refused_debit_is_an_issue(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        _, code, start = await _blocked(ops)
        token = (await _payment(ops, start)).provider_mandate_id
        assert token is not None
        gateway = _gateway(ops)
        await _send(
            ops,
            gateway.mandate_webhook(
                "token.cancelled", token, MandateStatus.CANCELLED, at=ops.app.state.clock.now()
            ),
        )
        await run_due_jobs(ops.app)
        _, other, second = await _blocked(ops)
        async with ops.app.state.sessionmaker() as db, db.begin():
            await Mandates(db, ops.app.state.clock).give_back(
                await _locked(db, second), refund_paise=0, reason="cancel_late"
            )
        gateway.refuses_debits = True
        ops.app.state.clock.advance(timedelta(hours=27))
        await run_due_jobs(ops.app)
        return {"cancelled": await _issues(ops, code), "refused": await _issues(ops, other)}

    assert run(scenario) == {
        "cancelled": ["mandate_cancelled"],
        "refused": ["mandate_debit_failed"],
    }
