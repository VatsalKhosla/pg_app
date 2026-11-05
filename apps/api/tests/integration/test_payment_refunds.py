"""Giving money back (step 6.3, ADR 0059). Done when every refund path is tested and visible to the
student with a status: a booking's every way of giving a token back, a token after its booking moved
on, ops' own refunds with a second person above the threshold, and the gateway's word on each."""

import uuid
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, cast

import httpx
import pytest
from sqlalchemy import select

from app.config import Settings
from app.core.actor import Role
from app.core.audit import AuditLog
from app.core.outbox import OutboxJob
from app.modules.booking.service import BookingSystem
from app.modules.identity.domain.sessions import SessionKind
from app.modules.payments.domain.refunds import (
    GatewayRefund,
    GatewayRefundStatus,
    refund_receipt,
)
from app.modules.payments.models import Payment, PaymentEvent, Refund
from app.modules.payments.service import Refunds, payments_part
from tests.flags import FixedFlags
from tests.integration.test_booking_check_in import MOVED_IN
from tests.integration.test_booking_confirmation import _held, _owner_of, _secure
from tests.integration.test_booking_disputes import REPORT
from tests.integration.test_booking_holds import _category_of, _hold, _listing, _quote, _student
from tests.integration.test_booking_student import _again
from tests.integration.test_payment_webhooks import _expired, _money_in, _send, _webhook
from tests.integration.test_payments_checkout import (
    TOKEN,
    _bank_says_yes,
    _callback,
    _gateway,
    _held_booking,
    _payment,
    _start,
)
from tests.jobs import RecordedTexts, run_due_jobs
from tests.metrics import totals
from tests.staff_api import NOW, Staff, run_as_staff

pytestmark = pytest.mark.integration

REASON = {"reason": "Spoke to the owner on the phone."}
# Above the ₹5,000 threshold, a payment larger than a token: only tests make one.
LARGE = 2_000_000


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Awaitable[Any]], **overrides: Any) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url, **overrides)

        async def remote_booking(ops: Staff) -> Any:
            ops.app.state.flags = FixedFlags(remote_booking_enabled=True)
            # What other tests left waiting, so the gateway here counts only this test's refunds.
            await run_due_jobs(ops.app)
            _gateway(ops).refunds_made = 0
            return await scenario(ops)

        return run_as_staff(settings, remote_booking)

    return run_scenario


async def _paid(
    ops: Staff, listing: dict[str, Any] | None = None
) -> tuple[Staff, str, dict[str, Any]]:
    """A student who has paid their token: them, the booking's code, and how checkout started."""
    student, held = await _held(ops, listing or await _listing(ops, beds=1))
    code: str = held["code"]
    start = await _start(student, code)
    answer = await _callback(student, start, await _bank_says_yes(student, start))
    assert answer.json()["outcome"] == "paid", answer.text
    return student, code, start


async def _refunds(ops: Staff, start: dict[str, Any]) -> list[Refund]:
    payment = await _payment(ops, start)
    async with ops.app.state.sessionmaker() as db:
        rows = await db.scalars(
            select(Refund).where(Refund.payment_id == payment.id).order_by(Refund.id)
        )
        return list(rows)


async def _mine(student: Staff, code: str) -> list[dict[str, Any]]:
    found = await student.ok("GET", f"/v1/bookings/{code}/payments")
    refunds: list[dict[str, Any]] = found["items"][0]["refunds"]
    return refunds


async def _audited(ops: Staff, refund: Refund) -> list[str]:
    async with ops.app.state.sessionmaker() as db:
        rows = await db.scalars(
            select(AuditLog.action)
            .where(AuditLog.entity_type == "refund", AuditLog.entity_id == str(refund.public_id))
            .order_by(AuditLog.id)
        )
        return list(rows)


async def _ask(
    ops: Staff, payment: dict[str, Any] | str, amount: int, *, key: str = ""
) -> httpx.Response:
    payment_id = payment if isinstance(payment, str) else payment["id"]
    return await ops.call(
        "POST",
        f"/v1/ops/payments/{payment_id}/refunds",
        json={"amountPaise": amount, "reason": "The owner asked us to."},
        headers={"Idempotency-Key": key or f"refund-{payment_id}-{amount}"},
    )


async def _make_large(ops: Staff, start: dict[str, Any]) -> None:
    """The payment as one above the threshold, for what ops' refunds do then: no token is."""
    async with ops.app.state.sessionmaker() as db, db.begin():
        found = await db.scalar(select(Payment).where(Payment.public_id == start["id"]))
        assert found is not None
        found.amount_paise = LARGE


@pytest.mark.parametrize(
    "ending",
    ["student_cancels", "owner_rejects", "ops_reject", "ops_cancel_for_owner", "timeout"],
)
def test_every_way_a_booking_ends_gives_the_token_back(
    run: Callable[..., Any], ending: str
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=1)
        student, code, start = await _paid(ops, listing)
        match ending:
            case "student_cancels":
                await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": TOKEN})
            case "owner_rejects":
                owner = await _owner_of(ops, listing)
                await owner.ok("POST", f"/v1/owner/bookings/{code}/reject", json=REASON)
            case "ops_reject":
                await ops.ok("POST", f"/v1/ops/bookings/{code}/reject", json=REASON)
            case "ops_cancel_for_owner":
                await ops.ok("POST", f"/v1/ops/bookings/{code}/owner-cancel", json=REASON)
            case _:
                # The owner never answers.
                ops.app.state.clock.advance(timedelta(hours=13))
                await _time_out(ops)
        texts = RecordedTexts()
        await run_due_jobs(ops.app, texts=texts)
        refund = (await _refunds(ops, start))[0]
        student = await _again(student)
        return {
            "refunds": len(await _refunds(ops, start)),
            "refund": (
                refund.kind,
                refund.status,
                refund.amount_paise,
                refund.provider_refund_id is not None,
                refund.reference,
                refund.processed_at is not None,
            ),
            "the student sees": [
                (each["amountPaise"], each["status"], each["reference"])
                for each in await _mine(student, code)
            ],
            # Moving the clock times out other tests' bookings too: count this one's alone.
            "made": _gateway(ops).refund_receipts.count(refund_receipt(refund.public_id)),
            "audit": await _audited(ops, refund),
            "text": [
                (template, values["amount"])
                for _, template, values in texts.sent
                if template == "payment_refund_processed" and values["code"] == code
            ],
        }

    assert run(scenario) == {
        "refunds": 1,
        "refund": ("automatic", "processed", TOKEN, True, "ARN-FAKE-0001", True),
        "the student sees": [(TOKEN, "processed", "ARN-FAKE-0001")],
        "made": 1,
        "audit": ["refund.requested", "refund.processed"],
        "text": [("payment_refund_processed", "₹2,000.00")],
    }


async def _time_out(ops: Staff) -> None:
    async with ops.app.state.sessionmaker() as db, db.begin():
        system = BookingSystem(db, ops.app.state.clock)
        while await system.time_out_confirmations():
            pass


def test_a_room_not_as_shown_gives_the_token_back_when_ops_refund_the_dispute(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, _, code = await _confirmed_paid(ops)
        ops.app.state.clock.set(MOVED_IN)
        student = await _again(student)
        ops = await _again(ops, kind=SessionKind.STAFF)
        await student.ok("POST", f"/v1/bookings/{code}/check-in")
        await student.ok("POST", f"/v1/bookings/{code}/disputes", json=REPORT)
        queue = await ops.ok("GET", "/v1/ops/disputes", params={"status": "open", "limit": 50})
        dispute = next(item for item in queue["items"] if item["booking"] == code)
        await ops.ok(
            "POST",
            f"/v1/ops/disputes/{dispute['id']}/resolve",
            json={"outcome": "refund", "notes": "The room wasn't as shown."},
        )
        await run_due_jobs(ops.app)
        return {"sees": [each["status"] for each in await _mine(student, code)]}

    assert run(scenario) == {"sees": ["processed"]}


async def _confirmed_paid(ops: Staff) -> tuple[Staff, dict[str, Any], str]:
    listing = await _listing(ops, beds=1)
    student, code, start = await _paid(ops, listing)
    await ops.ok("POST", f"/v1/ops/bookings/{code}/confirm", json=REASON)
    return student, start, code


def test_a_held_booking_with_no_money_in_gives_nothing_back(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": 0})
        await run_due_jobs(ops.app)
        return {"refunds": len(await _refunds(ops, start)), "made": _gateway(ops).refunds_made}

    assert run(scenario) == {"refunds": 0, "made": 0}


def test_a_booking_whose_token_never_came_through_a_payment_has_nothing_to_give_back(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> int:
        student, code = await _held_booking(ops)
        await _secure(ops, code)
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": TOKEN})
        await run_due_jobs(ops.app)
        made: int = _gateway(ops).refunds_made
        return made

    assert run(scenario) == 0


def test_a_late_token_goes_back_when_the_bed_has_gone(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=1)
        late, held = await _held(ops, listing)
        code = held["code"]
        start = await _start(late, code)
        money = await _money_in(ops, start)
        late = await _expired(ops, late, code)
        other = await _student(ops)
        taken = await _hold(other, (await _quote(other, _category_of(listing)))["id"])
        assert taken.status_code == 201, taken.text
        await _send(ops, _webhook(ops, "payment.captured", money))
        await run_due_jobs(ops.app)
        refunds = await _refunds(ops, start)
        return {
            "refunds": [(row.kind, row.status, row.reason) for row in refunds],
            "sees": [each["status"] for each in await _mine(late, code)],
        }

    assert run(scenario) == {
        "refunds": [("automatic", "processed", "late_payment_refund")],
        "sees": ["processed"],
    }


def test_a_token_after_the_student_cancelled_goes_back_too(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        money = await _money_in(ops, start)
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": 0})
        await _send(ops, _webhook(ops, "payment.captured", money))
        await run_due_jobs(ops.app)
        again = await _send(ops, _webhook(ops, "order.paid", money))
        await run_due_jobs(ops.app)
        return {
            "refunds": [
                (row.kind, row.status, row.reason, row.amount_paise)
                for row in await _refunds(ops, start)
            ],
            "again": again.status_code,
            "made": _gateway(ops).refunds_made,
        }

    assert run(scenario) == {
        "refunds": [("automatic", "processed", "moved_on", TOKEN)],
        "again": 200,
        "made": 1,
    }


def test_a_gateway_out_of_reach_is_tried_again_and_refunds_once(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code, start = await _paid(ops)
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": TOKEN})
        gateway = _gateway(ops)
        gateway.unreachable = True
        await run_due_jobs(ops.app)
        waiting = (await _refunds(ops, start))[0].status
        seen = await _mine(student, code)
        gateway.unreachable = False
        async with ops.app.state.sessionmaker() as db:
            job = await db.scalar(
                select(OutboxJob).where(
                    OutboxJob.kind == "payments.send_refund",
                    OutboxJob.payload["refund"].as_string()
                    == str((await _refunds(ops, start))[0].public_id),
                )
            )
            assert job is not None
            assert job.run_at is not None
            ops.app.state.clock.set(job.run_at + timedelta(seconds=1))
        await run_due_jobs(ops.app)
        return {
            "while out of reach": waiting,
            "the student sees": [each["status"] for each in seen],
            "after": (await _refunds(ops, start))[0].status,
            "made": gateway.refunds_made,
        }

    assert run(scenario) == {
        "while out of reach": "requested",
        "the student sees": ["requested"],
        "after": "processed",
        "made": 1,
    }


def test_a_refund_the_gateway_refuses_is_marked_and_leaves_the_money_refundable(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code, start = await _paid(ops)
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": TOKEN})
        _gateway(ops).refuses_refunds = True
        await run_due_jobs(ops.app)
        refund = (await _refunds(ops, start))[0]
        payments = await ops.ok("GET", f"/v1/ops/bookings/{code}/payments")
        return {
            "refund": (refund.status, refund.failure),
            "audit": await _audited(ops, refund),
            "the student sees": [each["status"] for each in await _mine(student, code)],
            "ops can still give back": payments["items"][0]["refundablePaise"],
        }

    assert run(scenario) == {
        "refund": ("failed", "The test bank refuses this refund."),
        "audit": ["refund.requested", "refund.failed"],
        "the student sees": ["failed"],
        "ops can still give back": TOKEN,
    }


def test_a_refund_that_waits_on_the_bank_moves_on_its_webhook_once(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code, start = await _paid(ops)
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": TOKEN})
        gateway = _gateway(ops)
        gateway.refund_status = GatewayRefundStatus.PENDING
        await run_due_jobs(ops.app)
        refund = (await _refunds(ops, start))[0]
        pending = refund.status
        at = ops.app.state.clock.now()
        found = GatewayRefund(
            refund.provider_refund_id or "",
            (await _payment(ops, start)).provider_payment_id or "",
            TOKEN,
            GatewayRefundStatus.PROCESSED,
            reference="ARN-LATER",
        )
        processed = gateway.refund_webhook("refund.processed", found, at=at)
        texts = RecordedTexts()
        await _send(ops, processed)
        await _send(ops, processed)
        await run_due_jobs(ops.app, texts=texts)
        # A slower word about it changes nothing, even with a new event id.
        await _send(
            ops,
            gateway.refund_webhook(
                "refund.failed",
                GatewayRefund(found.id, found.payment_id, TOKEN, GatewayRefundStatus.FAILED),
                at=at,
            ),
        )
        await run_due_jobs(ops.app, texts=texts)
        after = (await _refunds(ops, start))[0]
        return {
            "pending": pending,
            "after": (after.status, after.reference, after.processed_at == at),
            "texts": [
                template for _, template, values in texts.sent if values.get("code") == code
            ].count("payment_refund_processed"),
        }

    assert run(scenario) == {
        "pending": "pending",
        "after": ("processed", "ARN-LATER", True),
        "texts": 1,
    }


def test_a_webhook_can_arrive_before_the_answer_and_finds_its_refund_by_receipt(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code, start = await _paid(ops)
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": TOKEN})
        gateway = _gateway(ops)
        gateway.unreachable = True
        await run_due_jobs(ops.app)
        gateway.unreachable = False
        refund = (await _refunds(ops, start))[0]
        await _send(
            ops,
            gateway.refund_webhook(
                "refund.processed",
                GatewayRefund(
                    "rfnd_from_a_lost_answer",
                    (await _payment(ops, start)).provider_payment_id or "",
                    TOKEN,
                    GatewayRefundStatus.PROCESSED,
                    receipt=f"refund-{refund.public_id.hex}",
                ),
                at=ops.app.state.clock.now(),
            ),
        )
        await run_due_jobs(ops.app)
        after = await _refunds(ops, start)
        return {
            "rows": len(after),
            "refund": (after[0].status, after[0].provider_refund_id),
        }

    assert run(scenario) == {
        "rows": 1,
        "refund": ("processed", "rfnd_from_a_lost_answer"),
    }


def test_a_refund_nobody_here_asked_for_is_recorded_once_and_counts(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code, start = await _paid(ops)
        gateway = _gateway(ops)
        payment = await _payment(ops, start)
        found = GatewayRefund(
            "rfnd_from_the_dashboard",
            payment.provider_payment_id or "",
            50_000,
            GatewayRefundStatus.PROCESSED,
        )
        sent = gateway.refund_webhook("refund.processed", found, at=ops.app.state.clock.now())
        await _send(ops, sent)
        await run_due_jobs(ops.app)
        again = gateway.refund_webhook("refund.processed", found, at=ops.app.state.clock.now())
        await _send(ops, again)
        await run_due_jobs(ops.app)
        refunds = await _refunds(ops, start)
        payments = await ops.ok("GET", f"/v1/ops/bookings/{code}/payments")
        return {
            "refunds": [(row.kind, row.status, row.amount_paise) for row in refunds],
            "left": payments["items"][0]["refundablePaise"],
            "sees": [each["amountPaise"] for each in await _mine(student, code)],
        }

    assert run(scenario) == {
        "refunds": [("gateway", "processed", 50_000)],
        "left": TOKEN - 50_000,
        "sees": [50_000],
    }


def test_a_gateway_refund_of_a_payment_never_captured_finds_it_by_its_order(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        found = GatewayRefund("rfnd_auto", "pay_we_never_saw", TOKEN, GatewayRefundStatus.PENDING)
        await _send(
            ops,
            _gateway(ops).refund_webhook(
                "refund.created", found, at=ops.app.state.clock.now(), order_id=start["orderId"]
            ),
        )
        await run_due_jobs(ops.app)
        return {"refunds": [(row.kind, row.status) for row in await _refunds(ops, start)]}

    assert run(scenario) == {"refunds": [("gateway", "pending")]}


def test_a_refund_of_a_payment_that_isnt_ours_is_kept_and_goes_no_further(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> str | None:
        found = GatewayRefund("rfnd_x", "pay_not_ours", 1, GatewayRefundStatus.PROCESSED)
        sent = _gateway(ops).refund_webhook(
            "refund.processed", found, at=ops.app.state.clock.now(), event_id="evt_not_ours_refund"
        )
        await _send(ops, sent)
        await run_due_jobs(ops.app)
        async with ops.app.state.sessionmaker() as db:
            error: str | None = await db.scalar(
                select(PaymentEvent.error).where(
                    PaymentEvent.provider_event_id == "evt_not_ours_refund"
                )
            )
            return error

    assert run(scenario) == "unknown_payment"


def test_ops_give_money_back_with_a_reason_and_only_what_is_left(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code, start = await _paid(ops)
        before = totals("payments.refunds")
        first = await _ask(ops, start, 50_000, key="refund-key-first")
        replayed = await _ask(ops, start, 50_000, key="refund-key-first")
        too_much = await _ask(ops, start, TOKEN - 50_000 + 1, key="refund-key-too-much")
        blank = await ops.call(
            "POST",
            f"/v1/ops/payments/{start['id']}/refunds",
            json={"amountPaise": 100, "reason": ""},
            headers={"Idempotency-Key": "refund-key-blank"},
        )
        zero = await _ask(ops, start, 0, key="refund-key-zero")
        await run_due_jobs(ops.app)
        rest = await _ask(ops, start, TOKEN - 50_000, key="refund-key-rest")
        await run_due_jobs(ops.app)
        nothing = await _ask(ops, start, 1, key="refund-key-nothing")
        missing = await _ask(ops, "01933b1e-0000-7000-8000-000000000000", 1, key="refund-key-none")
        rows = await _refunds(ops, start)
        payments = await ops.ok("GET", f"/v1/ops/bookings/{code}/payments")
        return {
            "first": (first.status_code, first.json()["status"], first.json()["requestedBy"]),
            "replayed": (replayed.status_code, replayed.headers["Idempotent-Replayed"]),
            "too much": (too_much.status_code, too_much.json()["code"]),
            "detail": too_much.json()["detail"],
            "invalid": [blank.status_code, zero.status_code],
            "rest": rest.status_code,
            "nothing": (nothing.status_code, nothing.json()["code"]),
            "missing": missing.status_code,
            "rows": [(row.kind, row.status, row.amount_paise, row.reason) for row in rows],
            "left": payments["items"][0]["refundablePaise"],
            "sees": [each["amountPaise"] for each in await _mine(student, code)],
            "audit": await _audited(ops, rows[0]),
            "processed": totals("payments.refunds").get(
                frozenset({("status", "processed"), ("kind", "manual")}), 0
            )
            - before.get(frozenset({("status", "processed"), ("kind", "manual")}), 0),
        }

    seen = run(scenario)

    reason = "The owner asked us to."
    assert seen["first"][:2] == (201, "requested")
    assert seen["replayed"] == (201, "true")
    assert seen["too much"] == (409, "REFUND_TOO_MUCH")
    assert seen["detail"] == "At most ₹1,500.00 of this payment can go back."
    assert seen["invalid"] == [422, 422]
    assert seen["rest"] == 201
    assert seen["nothing"] == (409, "REFUND_TOO_MUCH")
    assert seen["missing"] == 404
    assert seen["rows"] == [
        ("manual", "processed", 50_000, reason),
        ("manual", "processed", TOKEN - 50_000, reason),
    ]
    assert seen["left"] == 0
    assert seen["sees"] == [50_000, TOKEN - 50_000]
    assert seen["audit"] == ["refund.requested", "refund.processed"]
    assert seen["processed"] == 2


def test_only_money_that_came_in_can_go_back(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> tuple[int, str]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        answer = await _ask(ops, start, 100)
        return answer.status_code, answer.json()["code"]

    assert run(scenario) == (409, "INVALID_TRANSITION")


def test_above_the_threshold_a_second_person_has_to_agree(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code, start = await _paid(ops)
        await _make_large(ops, start)
        at_it = await _ask(ops, start, 500_000, key="refund-at-threshold")
        over = await _ask(ops, start, 500_001, key="refund-over-threshold")
        refund_id = over.json()["id"]
        await run_due_jobs(ops.app)
        made_while_waiting = _gateway(ops).refunds_made
        queue = await ops.ok("GET", "/v1/ops/refunds", params={"status": "awaiting_approval"})
        hidden = await _mine(student, code)
        same_person = await ops.call("POST", f"/v1/ops/refunds/{refund_id}/approve")
        second = await _second_ops(ops)
        approved = await second.ok("POST", f"/v1/ops/refunds/{refund_id}/approve")
        again = await second.call("POST", f"/v1/ops/refunds/{refund_id}/approve")
        await run_due_jobs(ops.app)
        rows = await _refunds(ops, start)
        return {
            "at the threshold": at_it.json()["status"],
            "over": over.json()["status"],
            "made while waiting": made_while_waiting,
            "queued": refund_id in [item["id"] for item in queue["items"]],
            "student sees while waiting": [each["amountPaise"] for each in hidden],
            "same person": (same_person.status_code, same_person.json()["code"]),
            "approved": approved["status"],
            "made in all": _gateway(ops).refunds_made,
            "again": (again.status_code, again.json()["code"]),
            "after": [row.status for row in rows],
            "two people": rows[1].requested_by != rows[1].approved_by,
            "audit": await _audited(ops, rows[1]),
        }

    assert run(scenario) == {
        "at the threshold": "requested",
        "over": "awaiting_approval",
        "made while waiting": 1,
        "queued": True,
        "student sees while waiting": [500_000],
        "same person": (409, "REFUND_NEEDS_SECOND_PERSON"),
        "approved": "requested",
        "made in all": 2,
        "again": (409, "INVALID_TRANSITION"),
        "after": ["processed", "processed"],
        "two people": True,
        "audit": ["refund.requested", "refund.approved", "refund.processed"],
    }


async def _second_ops(ops: Staff) -> Staff:
    """Another ops member, signed in to staff tools."""
    from tests.staff_api import sign_in  # noqa: PLC0415

    return await sign_in(ops.app, ops.client, Role.OPS)


def test_a_refund_declined_gives_nothing_back_and_frees_what_it_spoke_for(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code, start = await _paid(ops)
        await _make_large(ops, start)
        over = await _ask(ops, start, 1_900_000, key="refund-to-decline")
        refund_id = over.json()["id"]
        too_much = await _ask(ops, start, 200_000, key="refund-while-spoken-for")
        declined = await ops.ok(
            "POST", f"/v1/ops/refunds/{refund_id}/decline", json={"reason": "Not ours to refund."}
        )
        again = await ops.call(
            "POST", f"/v1/ops/refunds/{refund_id}/decline", json={"reason": "Again."}
        )
        await run_due_jobs(ops.app)
        payments = await ops.ok("GET", f"/v1/ops/bookings/{code}/payments")
        rows = await _refunds(ops, start)
        return {
            "while spoken for": too_much.json()["code"],
            "declined": (declined["status"], declined["failure"]),
            "again": again.status_code,
            "made": _gateway(ops).refunds_made,
            "left": payments["items"][0]["refundablePaise"],
            "sees": await _mine(student, code),
            "audit": await _audited(ops, rows[0]),
        }

    assert run(scenario) == {
        "while spoken for": "REFUND_TOO_MUCH",
        "declined": ("declined", "Not ours to refund."),
        "again": 409,
        "made": 0,
        "left": LARGE,
        "sees": [],
        "audit": ["refund.requested", "refund.declined"],
    }


def test_an_approval_cant_give_back_more_than_is_left_by_then(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> tuple[int, str]:
        _, _, start = await _paid(ops)
        await _make_large(ops, start)
        over = await _ask(ops, start, 800_000, key="refund-waits-first")
        # Meanwhile ops give back less than the threshold, which goes straight away; then the money
        # the first spoke for is taken by the gateway itself.
        async with ops.app.state.sessionmaker() as db, db.begin():
            found = await db.scalar(select(Payment).where(Payment.public_id == start["id"]))
            assert found is not None
            found.amount_paise = 700_000
        second = await _second_ops(ops)
        answer = await second.call("POST", f"/v1/ops/refunds/{over.json()['id']}/approve")
        return answer.status_code, answer.json()["code"]

    assert run(scenario) == (409, "REFUND_TOO_MUCH")


def test_the_queue_pages_oldest_first_and_in_the_same_few_queries(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        made = []
        for _ in range(3):
            _, _, start = await _paid(ops)
            made.append((await _ask(ops, start, 100)).json()["id"])
        first = await ops.ok("GET", "/v1/ops/refunds", params={"status": "requested", "limit": 2})
        ids = [item["id"] for item in first["items"]]
        all_of_them = []
        cursor = None
        while True:
            params: dict[str, Any] = {"status": "requested", "limit": 50}
            if cursor is not None:
                params["cursor"] = cursor
            page = await ops.ok("GET", "/v1/ops/refunds", params=params)
            all_of_them += [item["id"] for item in page["items"]]
            cursor = page["nextCursor"]
            if cursor is None:
                break
        await run_due_jobs(ops.app)
        return {
            "paged": first["nextCursor"] is not None and len(ids) == 2,
            "ordered": all_of_them == sorted(all_of_them),
            "found": set(made) <= set(all_of_them),
            "booking": first["items"][0]["booking"].startswith("BK-"),
        }

    assert run(scenario) == {"paged": True, "ordered": True, "found": True, "booking": True}


def test_a_refund_that_has_moved_on_isnt_sent_and_sending_twice_is_safe(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code, start = await _paid(ops)
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": TOKEN})
        await run_due_jobs(ops.app)
        refund = (await _refunds(ops, start))[0]
        gateway = _gateway(ops)
        clock = ops.app.state.clock
        async with ops.app.state.sessionmaker() as db, db.begin():
            await Refunds(db, clock).send(gateway, refund.public_id)
            await Refunds(db, clock).send(gateway, uuid.uuid7())
        async with ops.app.state.sessionmaker() as db, db.begin():
            text = await Refunds(db, clock).text_for(uuid.uuid7())
        return {"made": gateway.refunds_made, "text": text}

    assert run(scenario) == {"made": 1, "text": None}


def test_a_refund_taken_at_another_gateway_isnt_sent_to_this_one(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code, start = await _paid(ops)
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": TOKEN})
        async with ops.app.state.sessionmaker() as db, db.begin():
            found = await db.scalar(select(Payment).where(Payment.public_id == start["id"]))
            assert found is not None
            found.provider = "razorpay"
        await run_due_jobs(ops.app)
        refund = (await _refunds(ops, start))[0]
        return {"refund": (refund.status, refund.failure), "made": _gateway(ops).refunds_made}

    assert run(scenario) == {
        "refund": ("failed", "The payment was taken at another gateway."),
        "made": 0,
    }


def test_a_student_sees_their_own_payments_and_no_one_elses(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code, _ = await _paid(ops)
        other = await _student(ops)
        mine = await student.ok("GET", f"/v1/bookings/{code}/payments")
        return {
            "mine": (mine["items"][0]["amountPaise"], mine["items"][0]["status"]),
            "captured": mine["items"][0]["capturedAt"] is not None,
            "theirs": (await other.call("GET", f"/v1/bookings/{code}/payments")).status_code,
            "no booking": (await ops.call("GET", "/v1/ops/bookings/nonsense/payments")).status_code,
        }

    assert run(scenario) == {
        "mine": (TOKEN, "captured"),
        "captured": True,
        "theirs": 404,
        "no booking": 404,
    }


def test_a_students_refunds_are_in_their_data_export(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> list[dict[str, Any]]:
        student, code, _ = await _paid(ops)
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": TOKEN})
        await run_due_jobs(ops.app)
        async with ops.app.state.sessionmaker() as db:
            part = await payments_part(db, student.user_id)
        found: list[dict[str, Any]] = cast("Any", part)["payments"][0]["refunds"]
        return found

    assert run(scenario) == [
        {
            "amountPaise": TOKEN,
            "status": "processed",
            "reference": "ARN-FAKE-0001",
            "requestedAt": NOW.isoformat(),
            "processedAt": NOW.isoformat(),
        }
    ]
