"""Reconciliation (step 6.6, ADR 0062): what hasn't come back is asked about at the gateway and goes
the way a webhook would; the settlement reports are matched line by line, posting what the gateway
kept, paid out and took back, once; what doesn't match is an issue that ops close."""

import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.config import Settings
from app.core.calendar import india_date
from app.core.outbox import enqueue
from app.modules.identity.domain.sessions import SessionKind
from app.modules.payments.domain.payments import INR, GatewayPayment, GatewayStatus
from app.modules.payments.domain.reconciliation import SettlementItem
from app.modules.payments.domain.refunds import GatewayRefund, GatewayRefundStatus
from app.modules.payments.models import ReconciliationIssue
from app.modules.payments.service import CHECK_STUCK, MATCH_SETTLEMENTS
from tests.flags import FixedFlags
from tests.integration.test_booking_confirmation import _held
from tests.integration.test_booking_holds import _listing
from tests.integration.test_booking_student import _again
from tests.integration.test_ledger import _balances
from tests.integration.test_payment_refunds import _paid, _refunds
from tests.integration.test_payments_checkout import TOKEN, _gateway, _payment, _start
from tests.jobs import run_due_jobs
from tests.staff_api import Staff, run_as_staff

pytestmark = pytest.mark.integration

ISSUES = "/v1/ops/reconciliation/issues"
FEE = 4_720


@pytest.fixture
def run(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> Callable[..., Any]:
    def run_scenario(scenario: Callable[[Staff], Any]) -> Any:
        settings = make_settings(database_url=database_url, redis_url=valkey_url)

        async def remote_booking(ops: Staff) -> Any:
            ops.app.state.flags = FixedFlags(remote_booking_enabled=True)
            await run_due_jobs(ops.app)  # what other tests left waiting
            return await scenario(ops)

        return run_as_staff(settings, remote_booking)

    return run_scenario


async def _job(ops: Staff, kind: str) -> None:
    """The worker's schedule, run once now."""
    async with ops.app.state.sessionmaker() as db, db.begin():
        await enqueue(db, kind, {}, clock=ops.app.state.clock)
    await run_due_jobs(ops.app)


async def _raised(ops: Staff, reference: str) -> list[tuple[str, str | None]]:
    """What was raised about this gateway reference, straight from the table: the shared
    database holds many more issues than one page shows."""
    async with ops.app.state.sessionmaker() as db:
        rows = await db.execute(
            select(ReconciliationIssue.kind, ReconciliationIssue.booking_code).where(
                ReconciliationIssue.reference == reference
            )
        )
        return [(kind, code) for kind, code in rows]


async def _issues(ops: Staff, references: set[str], *, open_only: bool = True) -> list[Any]:
    found = await ops.ok(
        "GET", ISSUES, params={"open": "true" if open_only else "false", "limit": 50}
    )
    return [item for item in found["items"] if item["reference"] in references]


def test_a_checkout_that_never_came_back_is_found_at_the_gateway(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, held = await _held(ops, await _listing(ops, beds=1))
        code = held["code"]
        start = await _start(student, code)
        gateway = _gateway(ops)
        order = start["orderId"]
        paid = gateway.checkout(order).payment_id
        gateway.order_attempts[order] = [
            GatewayPayment("pay_fake_failed", order, TOKEN, INR, GatewayStatus.FAILED),
            GatewayPayment(paid, order, TOKEN, INR, GatewayStatus.CAPTURED),
        ]
        ops.app.state.clock.advance(timedelta(minutes=2))
        await _job(ops, CHECK_STUCK)
        too_soon = (await _payment(ops, start)).status
        ops.app.state.clock.advance(timedelta(minutes=4))
        await _job(ops, CHECK_STUCK)
        payment = await _payment(ops, start)
        return {
            "too soon": too_soon,
            "found": (payment.status, payment.provider_payment_id == paid),
            "booking": (await student.ok("GET", f"/v1/bookings/{code}"))["status"],
            "books": await _balances(ops, code),
        }

    assert run(scenario) == {
        "too soon": "created",
        "found": ("captured", True),
        "booking": "token_secured",
        "books": {"gateway_clearing": TOKEN, "student_tokens_held": -TOKEN},
    }


def test_a_payment_the_bank_said_yes_to_and_nobody_captured_is_an_issue_once(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, held = await _held(ops, await _listing(ops, beds=1))
        start = await _start(student, held["code"])
        gateway = _gateway(ops)
        order = start["orderId"]
        paid = gateway.checkout(order).payment_id
        gateway.order_attempts[order] = [
            GatewayPayment(paid, order, TOKEN, INR, GatewayStatus.AUTHORIZED)
        ]
        ops.app.state.clock.advance(timedelta(minutes=70))
        await _job(ops, CHECK_STUCK)
        await _job(ops, CHECK_STUCK)
        return {
            "payment": (await _payment(ops, start)).status,
            "issues": [
                (item["kind"], item["booking"] == held["code"])
                for item in await _issues(ops, {paid})
            ],
        }

    assert run(scenario) == {
        "payment": "authorized",
        "issues": [("stuck_authorized", True)],
    }


def test_a_refund_still_with_the_bank_is_asked_about_until_it_arrives(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code, start = await _paid(ops, await _listing(ops, beds=1))
        gateway = _gateway(ops)
        gateway.refund_status = GatewayRefundStatus.PENDING
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": TOKEN})
        await run_due_jobs(ops.app)
        gateway.refund_status = GatewayRefundStatus.PROCESSED
        sent = (await _refunds(ops, start))[0]
        payment = await _payment(ops, start)
        assert sent.provider_refund_id is not None
        assert payment.provider_payment_id is not None
        gateway.refunds_said[payment.provider_payment_id] = [
            GatewayRefund(
                sent.provider_refund_id,
                payment.provider_payment_id,
                TOKEN,
                GatewayRefundStatus.PROCESSED,
                reference="ARN-FAKE-0002",
            )
        ]
        await _job(ops, CHECK_STUCK)
        arrived = (await _refunds(ops, start))[0]
        return {
            "sent": sent.status,
            "arrived": (arrived.status, arrived.reference),
            "books": await _balances(ops, code),
        }

    assert run(scenario) == {
        "sent": "pending",
        "arrived": ("processed", "ARN-FAKE-0002"),
        "books": {},
    }


def test_the_settlement_report_posts_the_fee_and_the_payout_once_and_ops_close_the_rest(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        _, code, start = await _paid(ops, await _listing(ops, beds=1))
        payment = await _payment(ops, start)
        assert payment.provider_payment_id is not None
        gateway = _gateway(ops)
        unknown, adjustment = f"pay_unknown_{uuid.uuid4().hex[:8]}", f"adj_{uuid.uuid4().hex[:8]}"
        yesterday = india_date(ops.app.state.clock.now()) - timedelta(days=1)

        def line(entity: str, kind: str, amount: int, fee: int) -> SettlementItem:
            return SettlementItem(
                entity, kind, amount, fee, 720, amount - fee, 0, INR, True, "setl_fake_1", None
            )

        gateway.settlements[yesterday] = [
            line(payment.provider_payment_id, "payment", TOKEN, FEE),
            line(unknown, "payment", 50_000, 1_180),
            line(adjustment, "adjustment", 1_000, 0),
        ]
        await _job(ops, MATCH_SETTLEMENTS)
        await _job(ops, MATCH_SETTLEMENTS)  # read again: nothing posts or is raised twice
        found = await _issues(ops, {unknown, adjustment})
        closing = next(item for item in found if item["reference"] == unknown)
        path = f"{ISSUES}/{closing['id']}/resolve"
        closed = await ops.ok("POST", path, json={"resolution": "Another account's payment."})
        again = await ops.call("POST", path, json={"resolution": "Twice."})
        summary = await ops.ok("GET", "/v1/ops/reconciliation")
        return {
            "books": await _balances(ops, code),
            "issues": sorted((item["kind"], item["reference"] == unknown) for item in found),
            "closed": (closed["resolution"], closed["resolvedAt"] is not None),
            "again": again.json()["code"],
            "still open": [item["kind"] for item in await _issues(ops, {unknown, adjustment})],
            "all": len(await _issues(ops, {unknown, adjustment}, open_only=False)),
            "summary": sorted(summary),
        }

    assert run(scenario) == {
        "books": {
            "bank": TOKEN - FEE,
            "payment_fees": FEE,
            "student_tokens_held": -TOKEN,
        },
        "issues": [("unexpected_item", False), ("unknown_payment", True)],
        "closed": ("Another account's payment.", True),
        "again": "INVALID_TRANSITION",
        "still open": ["unexpected_item"],
        "all": 2,
        "summary": ["linksOpen", "openIssues", "refundsWaiting", "tokensAuthorized"],
    }


def test_a_payment_no_report_has_settled_in_a_week_is_an_issue(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        _, code, start = await _paid(ops, await _listing(ops, beds=1))
        payment = await _payment(ops, start)
        assert payment.provider_payment_id is not None
        gateway = _gateway(ops)
        await _job(ops, MATCH_SETTLEMENTS)
        fresh = await _raised(ops, payment.provider_payment_id)
        gateway.settles = True
        ops.app.state.clock.advance(timedelta(days=8))
        ops = await _again(ops, kind=SessionKind.STAFF)
        await _job(ops, MATCH_SETTLEMENTS)
        return {
            "fresh": fresh,
            "late": await _raised(ops, payment.provider_payment_id),
            "code": code,
        }

    seen = run(scenario)

    assert seen["fresh"] == []
    # However many other payments the database holds: the check reads them all, a page at a time.
    assert seen["late"] == [("not_settled", seen["code"])]
