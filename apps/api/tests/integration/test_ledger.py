"""The books (step 6.4, ADR 0060). Done when a test replays a full booking life cycle and the trial
balance is zero: every money event posts in the transaction it happens in, once, and the database
itself refuses anything that doesn't balance or changes what's posted."""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import event, func, insert, select, text
from sqlalchemy.exc import DBAPIError

from app.config import Settings
from app.core.outbox import enqueue
from app.modules.booking.jobs import CHECK_WINDOWS
from app.modules.identity.domain.sessions import SessionKind
from app.modules.ledger.domain.ledger import CHART, Direction, PostingKind, token_received
from app.modules.ledger.models import LedgerAccount, LedgerEntry, LedgerTransaction
from app.modules.ledger.service import Ledger
from app.modules.payments.domain.refunds import GatewayRefund, GatewayRefundStatus
from tests.flags import FixedFlags
from tests.integration.test_booking_check_in import MOVED_IN
from tests.integration.test_booking_confirmation import _held
from tests.integration.test_booking_holds import _category_of, _hold, _listing, _quote, _student
from tests.integration.test_booking_student import _again
from tests.integration.test_payment_refunds import _ask, _paid, _refunds
from tests.integration.test_payment_webhooks import _expired, _money_in, _send, _webhook
from tests.integration.test_payments_checkout import (
    TOKEN,
    _bank_says_yes,
    _callback,
    _gateway,
    _held_booking,
    _start,
)
from tests.jobs import run_due_jobs
from tests.staff_api import Staff, run_as_staff

pytestmark = pytest.mark.integration

BOOKS = "/v1/ops/ledger"
# The fee and GST on the ₹10,000 rooms these tests book.
FEE = 300_000
GST = 54_000
REASON = {"reason": "Spoke to the owner on the phone."}


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


async def _balances(ops: Staff, code: str) -> dict[str, int]:
    """What one booking did to each account: debits less credits, leaving out what's nothing."""
    found = await ops.ok("GET", f"{BOOKS}/trial-balance", params={"booking": code})
    assert found["totalDebitPaise"] == found["totalCreditPaise"]
    return {
        line["account"]: line["balancePaise"] for line in found["lines"] if line["balancePaise"]
    }


async def _kinds(ops: Staff, code: str) -> list[str]:
    page = await ops.ok("GET", f"{BOOKS}/transactions", params={"booking": code})
    return [item["kind"] for item in reversed(page["items"])]


async def _settled(ops: Staff, student: Staff, code: str) -> tuple[Staff, Staff]:
    """From the token in to living there: confirmed, moved in, and the 24 hours over."""
    await ops.ok("POST", f"/v1/ops/bookings/{code}/confirm", json=REASON)
    ops.app.state.clock.set(MOVED_IN)
    student = await _again(student)
    await student.ok("POST", f"/v1/bookings/{code}/check-in")
    ops.app.state.clock.advance(timedelta(hours=24))
    async with ops.app.state.sessionmaker() as db, db.begin():
        await enqueue(db, CHECK_WINDOWS, {}, clock=ops.app.state.clock)
    await run_due_jobs(ops.app)
    return await _again(ops, kind=SessionKind.STAFF), student


def test_a_whole_booking_posts_as_the_architecture_says_and_the_books_balance(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code, _ = await _paid(ops)
        seen: dict[str, Any] = {"token in": await _balances(ops, code)}
        ops, student = await _settled(ops, student, code)
        booking = await student.ok("GET", f"/v1/bookings/{code}")
        page = await ops.ok("GET", f"{BOOKS}/transactions", params={"booking": code})
        return seen | {
            "status": booking["status"],
            "settled": await _balances(ops, code),
            "kinds": [item["kind"] for item in reversed(page["items"])],
            "one entry": page["items"][0]["entries"][0]["name"],
            "booking": page["items"][0]["booking"] == code,
        }

    seen = run(scenario)

    assert seen["token in"] == {"gateway_clearing": TOKEN, "student_tokens_held": -TOKEN}
    assert seen["status"] == "active"
    # The gateway holds the token; the owner owes the rest of the fee; the fee is earned, and the
    # GST is owed. Nothing is held for the student any more.
    assert seen["settled"] == {
        "gateway_clearing": TOKEN,
        "owner_receivable": FEE + GST - TOKEN,
        "placement_fee_revenue": -FEE,
        "gst_payable": -GST,
    }
    assert sum(seen["settled"].values()) == 0
    assert sorted(seen["kinds"]) == sorted(
        [PostingKind.TOKEN_RECEIVED, PostingKind.TOKEN_APPLIED, PostingKind.OWNER_INVOICED]
    )
    assert seen["kinds"][0] == PostingKind.TOKEN_RECEIVED
    assert isinstance(seen["one entry"], str)
    assert seen["booking"] is True


def test_a_token_that_goes_back_leaves_the_books_as_they_were(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code, _ = await _paid(ops)
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": TOKEN})
        before = await _balances(ops, code)
        await run_due_jobs(ops.app)
        return {
            "until the refund goes through": before,
            "after": await _balances(ops, code),
            "kinds": await _kinds(ops, code),
        }

    assert run(scenario) == {
        "until the refund goes through": {"gateway_clearing": TOKEN, "student_tokens_held": -TOKEN},
        "after": {},
        "kinds": [PostingKind.TOKEN_RECEIVED, PostingKind.TOKEN_REFUNDED],
    }


def test_a_refund_that_fails_or_waits_posts_nothing(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code, _ = await _paid(ops)
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": TOKEN})
        _gateway(ops).refund_status = GatewayRefundStatus.PENDING
        await run_due_jobs(ops.app)
        pending = await _kinds(ops, code)
        other, other_code, _ = await _paid(ops)
        await other.ok("POST", f"/v1/bookings/{other_code}/cancel", json={"refundPaise": TOKEN})
        _gateway(ops).refuses_refunds = True
        await run_due_jobs(ops.app)
        return {"pending": pending, "refused": await _kinds(ops, other_code)}

    assert run(scenario) == {
        "pending": [PostingKind.TOKEN_RECEIVED],
        "refused": [PostingKind.TOKEN_RECEIVED],
    }


def test_part_of_a_token_going_back_leaves_the_rest_held(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, int]:
        _, code, start = await _paid(ops)
        await _ask(ops, start, 50_000, key=f"refund-part-{code}")
        await run_due_jobs(ops.app)
        return await _balances(ops, code)

    assert run(scenario) == {
        "gateway_clearing": TOKEN - 50_000,
        "student_tokens_held": -(TOKEN - 50_000),
    }


def test_the_same_money_reported_again_and_again_posts_once(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        money = await _money_in(ops, start)
        proof = await _bank_says_yes(student, start)
        await _callback(student, start, proof)
        await _send(ops, _webhook(ops, "payment.captured", money))
        await _send(ops, _webhook(ops, "order.paid", money))
        await run_due_jobs(ops.app)
        await _callback(student, start, proof)
        return {"kinds": await _kinds(ops, code), "balances": await _balances(ops, code)}

    assert run(scenario) == {
        "kinds": [PostingKind.TOKEN_RECEIVED],
        "balances": {"gateway_clearing": TOKEN, "student_tokens_held": -TOKEN},
    }


def test_a_late_token_is_on_the_books_whichever_way_it_goes(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        # The bed is free, so the booking takes it back.
        revived, code = await _held_booking(ops)
        start = await _start(revived, code)
        money = await _money_in(ops, start)
        await _expired(ops, revived, code)
        await _send(ops, _webhook(ops, "payment.captured", money))
        await run_due_jobs(ops.app)
        # The bed has gone, so the token goes back.
        listing = await _listing(ops, beds=1)
        late, held = await _held(ops, listing)
        gone = held["code"]
        late_start = await _start(late, gone)
        late_money = await _money_in(ops, late_start)
        await _expired(ops, late, gone)
        other = await _student(ops)
        taken = await _hold(other, (await _quote(other, _category_of(listing)))["id"])
        assert taken.status_code == 201, taken.text
        await _send(ops, _webhook(ops, "payment.captured", late_money))
        await run_due_jobs(ops.app)
        return {
            "revived": await _balances(ops, code),
            "gone": await _balances(ops, gone),
            "gone, kinds": await _kinds(ops, gone),
        }

    assert run(scenario) == {
        "revived": {"gateway_clearing": TOKEN, "student_tokens_held": -TOKEN},
        "gone": {},
        "gone, kinds": [PostingKind.TOKEN_RECEIVED, PostingKind.TOKEN_REFUNDED],
    }


def test_a_gateways_refund_of_money_never_captured_posts_nothing(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        await _send(
            ops,
            _gateway(ops).refund_webhook(
                "refund.processed",
                GatewayRefund(
                    "rfnd_auto_ledger", "pay_never_seen", TOKEN, GatewayRefundStatus.PROCESSED
                ),
                at=ops.app.state.clock.now(),
                order_id=start["orderId"],
            ),
        )
        await run_due_jobs(ops.app)
        return {
            "refund": [(row.kind, row.status) for row in await _refunds(ops, start)],
            "kinds": await _kinds(ops, code),
        }

    assert run(scenario) == {"refund": [("gateway", "processed")], "kinds": []}


def test_a_gateways_refund_of_money_that_came_in_posts_as_any_refund_does(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, int]:
        _, code, start = await _paid(ops)
        payment = await _money_in(ops, start)
        await _send(
            ops,
            _gateway(ops).refund_webhook(
                "refund.processed",
                GatewayRefund(
                    f"rfnd_dashboard_{code}", payment.id, 50_000, GatewayRefundStatus.PROCESSED
                ),
                at=ops.app.state.clock.now(),
            ),
        )
        await run_due_jobs(ops.app)
        return await _balances(ops, code)

    assert run(scenario) == {
        "gateway_clearing": TOKEN - 50_000,
        "student_tokens_held": -(TOKEN - 50_000),
    }


def test_the_database_refuses_a_transaction_that_doesnt_balance(run: Callable[..., Any]) -> None:
    async def lopsided(ops: Staff) -> None:
        async with ops.app.state.sessionmaker() as db, db.begin():
            account = await db.scalar(select(LedgerAccount.id).where(LedgerAccount.code == "bank"))
            transaction = await db.scalar(
                insert(LedgerTransaction)
                .values(
                    kind=PostingKind.TOKEN_RECEIVED,
                    key="a-lopsided-one",
                    posted_at=ops.app.state.clock.now(),
                )
                .returning(LedgerTransaction.id)
            )
            await db.execute(
                insert(LedgerEntry).values(
                    transaction_id=transaction,
                    account_id=account,
                    direction=Direction.DEBIT,
                    amount_paise=100,
                )
            )

    async def scenario(ops: Staff) -> str:
        with pytest.raises(DBAPIError) as refused:
            await lopsided(ops)
        return str(refused.value.orig)

    assert "is out by 100 paise" in run(scenario)


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE ledger_entries SET amount_paise = amount_paise + 1",
        "DELETE FROM ledger_entries",
        "TRUNCATE ledger_entries CASCADE",
        "UPDATE ledger_transactions SET memo = 'changed'",
        "DELETE FROM ledger_transactions",
    ],
)
def test_nothing_posted_can_be_changed_or_removed(run: Callable[..., Any], statement: str) -> None:
    async def scenario(ops: Staff) -> str:
        await _paid(ops)
        async with ops.app.state.sessionmaker() as db:
            with pytest.raises(DBAPIError) as refused:
                async with db.begin():
                    await db.execute(text(statement))
            return str(refused.value.orig)

    assert "is append-only" in run(scenario)


def test_a_key_posts_once_and_says_so(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> list[bool]:
        clock = ops.app.state.clock
        answers = []
        for _ in range(2):
            async with ops.app.state.sessionmaker() as db, db.begin():
                answers.append(
                    await Ledger(db, clock).post(token_received(100), key=f"once-{clock.now()}")
                )
        return answers

    assert run(scenario) == [True, False]


def test_the_chart_is_the_codes_and_the_whole_books_balance(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        await _paid(ops)
        whole = await ops.ok("GET", f"{BOOKS}/trial-balance")
        async with ops.app.state.sessionmaker() as db:
            rows = await db.execute(
                select(LedgerAccount.code, LedgerAccount.type, LedgerAccount.name)
            )
            accounts = {row.code: (row.type, row.name) for row in rows}
        return {
            "accounts": accounts,
            "balanced": whole["totalDebitPaise"] == whole["totalCreditPaise"],
            "lines": len(whole["lines"]),
            "someone": whole["totalDebitPaise"] > 0,
            "booking": whole["booking"],
            "nobody's": await _balances(ops, "BK-00000000"),
        }

    seen = run(scenario)

    assert seen["accounts"] == {
        account.value: (kind.value, name) for account, (kind, name) in CHART.items()
    }
    assert seen["balanced"] is True
    assert seen["lines"] == len(CHART)
    assert seen["someone"] is True
    assert seen["booking"] is None
    assert seen["nobody's"] == {}


def test_transactions_page_newest_first_in_the_same_few_queries(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        for _ in range(3):
            await _paid(ops)
        engine = ops.app.state.engine
        statements: list[str] = []

        def count(_conn: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
            if "ledger" in statement:
                statements.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", count)
        short = await ops.ok("GET", f"{BOOKS}/transactions", params={"limit": 1})
        short_count = len(statements)
        statements.clear()
        long = await ops.ok("GET", f"{BOOKS}/transactions", params={"limit": 3})
        event.remove(engine.sync_engine, "before_cursor_execute", count)
        following = await ops.ok(
            "GET", f"{BOOKS}/transactions", params={"limit": 1, "cursor": short["nextCursor"]}
        )
        ids = [item["id"] for item in long["items"]]
        async with ops.app.state.sessionmaker() as db:
            total = await db.scalar(select(func.count()).select_from(LedgerTransaction))
        return {
            "same queries": short_count == len(statements),
            "newest first": ids == sorted(ids, reverse=True),
            "next page": following["items"][0]["id"] == ids[1],
            "some": (total or 0) >= 3,
        }

    assert run(scenario) == {
        "same queries": True,
        "newest first": True,
        "next page": True,
        "some": True,
    }


def test_settling_a_booking_twice_posts_it_once(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> list[str]:
        student, code, _ = await _paid(ops)
        ops, student = await _settled(ops, student, code)
        async with ops.app.state.sessionmaker() as db, db.begin():
            await enqueue(db, CHECK_WINDOWS, {}, clock=ops.app.state.clock)
        await run_due_jobs(ops.app)
        return await _kinds(ops, code)

    assert sorted(run(scenario)) == sorted(
        [PostingKind.TOKEN_RECEIVED, PostingKind.TOKEN_APPLIED, PostingKind.OWNER_INVOICED]
    )
