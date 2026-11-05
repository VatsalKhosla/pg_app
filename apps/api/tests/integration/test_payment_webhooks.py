"""A gateway's webhooks (step 6.2, ADR 0057). Done when duplicate, out-of-order and late webhooks
are all handled correctly: each event stored once and answered at once, a payment only moving
forward, and a token after its hold ended taking the bed back if it can, or going back if not."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.core.audit import AuditLog
from app.core.outbox import OutboxJob
from app.modules.booking.service import BookingSystem
from app.modules.inventory.models import InventoryAllocation
from app.modules.inventory.service import BedHolds
from app.modules.payments.adapters.fake import FakeGateway, SignedWebhook
from app.modules.payments.domain.payments import GatewayPayment, GatewayStatus
from app.modules.payments.models import PaymentEvent
from app.modules.payments.service import PROCESS_EVENT, PaymentWebhooks
from tests.flags import FixedFlags
from tests.integration.test_booking_confirmation import _about, _booking, _held, _history
from tests.integration.test_booking_holds import _category_of, _hold, _listing, _quote, _student
from tests.integration.test_booking_student import _again
from tests.integration.test_payments_checkout import (
    HOLD,
    TOKEN,
    _audited,
    _bank_says_yes,
    _callback,
    _gateway,
    _held_booking,
    _payment,
    _start,
)
from tests.jobs import RecordedTexts, run_due_jobs
from tests.metrics import totals
from tests.staff_api import Staff, run_as_staff

pytestmark = pytest.mark.integration

WEBHOOK = "/v1/webhooks/razorpay"


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


async def _send(ops: Staff, sent: SignedWebhook, *, signature: str | None = None) -> httpx.Response:
    """As Razorpay sends it: no cookies, no CSRF token, only its two headers."""
    return await ops.client.post(
        WEBHOOK,
        content=sent.raw_body,
        headers={
            "X-Razorpay-Signature": sent.signature if signature is None else signature,
            "X-Razorpay-Event-Id": sent.event_id,
            "Content-Type": "application/json",
        },
    )


async def _money_in(ops: Staff, start: dict[str, Any]) -> GatewayPayment:
    """The payment the gateway has for this order, once its bank has said yes."""
    gateway = _gateway(ops)
    return await gateway.fetch_payment(gateway.checkout(start["orderId"]).payment_id)


def _webhook(
    ops: Staff, kind: str, payment: GatewayPayment, *, event_id: str = "", **change: Any
) -> SignedWebhook:
    return _gateway(ops).webhook(
        kind,
        GatewayPayment(
            payment.id,
            change.get("order_id", payment.order_id),
            change.get("amount_paise", payment.amount_paise),
            payment.currency,
            change.get("status", payment.status),
        ),
        at=ops.app.state.clock.now(),
        event_id=event_id,
    )


async def _status(student: Staff, code: str) -> str:
    booking = await student.ok("GET", f"/v1/bookings/{code}")
    found: str = booking["status"]
    return found


async def _event(ops: Staff, sent: SignedWebhook) -> PaymentEvent:
    async with ops.app.state.sessionmaker() as db:
        found: PaymentEvent | None = await db.scalar(
            select(PaymentEvent).where(PaymentEvent.provider_event_id == sent.event_id)
        )
        assert found is not None
        return found


async def _events_with(ops: Staff, event_id: str) -> int:
    async with ops.app.state.sessionmaker() as db:
        found: int = (
            await db.scalar(
                select(func.count())
                .select_from(PaymentEvent)
                .where(PaymentEvent.provider_event_id == event_id)
            )
            or 0
        )
        return found


async def _end_holds(ops: Staff) -> None:
    """The job's work, however many other tests' holds are due."""
    async with ops.app.state.sessionmaker() as db, db.begin():
        system = BookingSystem(db, ops.app.state.clock)
        while await system.expire_holds():
            pass


async def _expired(ops: Staff, student: Staff, code: str) -> Staff:
    """The student's hold runs out, and the job ends it: the student, signed in again."""
    ops.app.state.clock.advance(HOLD + timedelta(seconds=1))
    await _end_holds(ops)
    student = await _again(student)
    assert await _status(student, code) == "expired"
    return student


async def _active_beds(ops: Staff, code: str) -> int:
    booking = await _booking(ops, code)
    async with ops.app.state.sessionmaker() as db:
        found: int = (
            await db.scalar(
                select(func.count())
                .select_from(InventoryAllocation)
                .where(InventoryAllocation.booking_id == booking.id, InventoryAllocation.is_active)
            )
            or 0
        )
        return found


def test_a_webhook_secures_a_booking_with_no_browser_at_all(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        before = totals("payments.webhooks")
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        sent = _webhook(ops, "payment.captured", await _money_in(ops, start))
        answer = await _send(ops, sent)
        seen: dict[str, Any] = {
            "answer": (answer.status_code, answer.json()),
            "until the job runs": await _status(student, code),
            "not processed yet": (await _event(ops, sent)).processed_at,
        }
        texts = RecordedTexts()
        await run_due_jobs(ops.app, texts=texts)
        event = await _event(ops, sent)
        payment = await _payment(ops, start)
        async with ops.app.state.sessionmaker() as db:
            actors = list(
                await db.scalars(
                    select(AuditLog.actor_type).where(
                        AuditLog.entity_id == start["id"], AuditLog.action == "payment.captured"
                    )
                )
            )
        return seen | {
            "status": await _status(student, code),
            "payment": (payment.status, payment.provider_payment_id, payment.captured_at),
            "history": await _history(ops, code),
            "event": (event.event_type, event.provider, event.processed_at, event.error),
            "stored": event.payload,
            "actors": actors,
            "texts": [template for template, _ in _about(texts, code)],
            "now": ops.app.state.clock.now(),
            "new": totals("payments.webhooks").get(frozenset({("outcome", "new")}), 0)
            - before.get(frozenset({("outcome", "new")}), 0),
        }

    seen = run(scenario)

    assert seen["answer"] == (200, {"new": True})
    assert seen["until the job runs"] == "held"
    assert seen["not processed yet"] is None
    assert seen["status"] == "token_secured"
    assert seen["payment"][0] == "captured"
    assert seen["payment"][1].startswith("pay_fake_")
    assert seen["payment"][2] == seen["now"]
    assert seen["history"] == [("hold", "student"), ("token_secured", "system")]
    assert seen["event"] == ("payment.captured", "fake", seen["now"], None)
    assert seen["actors"] == ["system"]
    assert seen["texts"] == ["booking_token_in"]
    assert seen["new"] == 1
    # What the gateway's copy held about the student stayed out of it.
    assert set(seen["stored"]) == {"createdAt", "payment"}
    assert set(seen["stored"]["payment"]) == {"id", "orderId", "amountPaise", "currency", "status"}


def test_the_same_event_twice_is_one_event_and_one_job(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        sent = _webhook(ops, "payment.captured", await _money_in(ops, start))
        first = await _send(ops, sent)
        at_once = await asyncio.gather(*[_send(ops, sent) for _ in range(3)])
        event = await _event(ops, sent)
        async with ops.app.state.sessionmaker() as db:
            jobs = await db.scalar(
                select(func.count())
                .select_from(OutboxJob)
                .where(
                    OutboxJob.kind == PROCESS_EVENT,
                    OutboxJob.payload["event"].as_integer() == event.id,
                )
            )
        await run_due_jobs(ops.app)
        later = await _send(ops, sent)
        await run_due_jobs(ops.app)
        return {
            "first": first.json(),
            "at once": [answer.json() for answer in at_once],
            "later": (later.status_code, later.json()),
            "stored": await _events_with(ops, sent.event_id),
            "jobs": jobs,
            "history": await _history(ops, code),
            "audit": await _audited(ops, start),
        }

    assert run(scenario) == {
        "first": {"new": True},
        "at once": [{"new": False}] * 3,
        "later": (200, {"new": False}),
        "stored": 1,
        "jobs": 1,
        "history": [("hold", "student"), ("token_secured", "system")],
        "audit": ["payment.order_created", "payment.captured"],
    }


def test_two_events_about_one_payment_move_it_once(run: Callable[..., Any]) -> None:
    """Razorpay sends payment.captured and order.paid for the same money."""

    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        money = await _money_in(ops, start)
        await _send(ops, _webhook(ops, "order.paid", money))
        await _send(ops, _webhook(ops, "payment.captured", money))
        await run_due_jobs(ops.app)
        return {"history": await _history(ops, code), "audit": await _audited(ops, start)}

    assert run(scenario) == {
        "history": [("hold", "student"), ("token_secured", "system")],
        "audit": ["payment.order_created", "payment.captured"],
    }


def test_events_out_of_order_only_move_a_payment_forward(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        money = await _money_in(ops, start)

        async def after(kind: str, status: GatewayStatus) -> tuple[str, str]:
            await _send(ops, _webhook(ops, kind, money, status=status))
            await run_due_jobs(ops.app)
            return ((await _payment(ops, start)).status, await _status(student, code))

        return {
            "a failed attempt": await after("payment.failed", GatewayStatus.FAILED),
            "the bank says yes": await after("payment.authorized", GatewayStatus.AUTHORIZED),
            "captured": await after("payment.captured", GatewayStatus.CAPTURED),
            "a slow authorized": await after("payment.authorized", GatewayStatus.AUTHORIZED),
            "a slow failure": await after("payment.failed", GatewayStatus.FAILED),
            "history": await _history(ops, code),
        }

    assert run(scenario) == {
        "a failed attempt": ("created", "held"),
        "the bank says yes": ("authorized", "held"),
        "captured": ("captured", "token_secured"),
        "a slow authorized": ("captured", "token_secured"),
        "a slow failure": ("captured", "token_secured"),
        "history": [("hold", "student"), ("token_secured", "system")],
    }


def test_a_webhook_and_a_checkout_at_once_move_the_booking_once(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        proof = await _bank_says_yes(student, start)
        await _send(ops, _webhook(ops, "payment.captured", await _money_in(ops, start)))
        answer, _ = await asyncio.gather(_callback(student, start, proof), run_due_jobs(ops.app))
        again = await _callback(student, start, proof)
        return {
            "answers": (answer.json()["outcome"], again.json()["outcome"]),
            "history": await _history(ops, code),
            "audit": await _audited(ops, start),
        }

    assert run(scenario) == {
        "answers": ("paid", "paid"),
        "history": [("hold", "student"), ("token_secured", "system")],
        "audit": ["payment.order_created", "payment.captured"],
    }


def test_a_webhook_after_a_checkout_changes_nothing(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        answer = await _callback(student, start, await _bank_says_yes(student, start))
        await _send(ops, _webhook(ops, "payment.captured", await _money_in(ops, start)))
        await run_due_jobs(ops.app)
        return {"answer": answer.json()["outcome"], "history": await _history(ops, code)}

    assert run(scenario) == {
        "answer": "paid",
        "history": [("hold", "student"), ("token_secured", "system")],
    }


def test_what_isnt_the_gateways_is_refused_and_nothing_is_stored(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        money = await _money_in(ops, start)
        clock = ops.app.state.clock
        good = _webhook(ops, "payment.captured", money)
        tampered = SignedWebhook(
            good.raw_body.replace(b"200000", b"000100"), good.signature, "evt_tampered"
        )
        not_an_event = _gateway(ops).signed({"hello": "world"}, event_id="evt_not_an_event")
        old = _gateway(ops).webhook(
            "payment.captured", money, at=clock.now() - timedelta(hours=49), event_id="evt_old"
        )
        answers = [
            await _send(ops, good, signature="a" * 64),
            await _send(ops, good, signature=""),
            await _send(ops, tampered),
            await _send(ops, not_an_event),
            await _send(ops, old),
        ]
        await run_due_jobs(ops.app)
        return {
            "answers": [(answer.status_code, answer.json()["code"]) for answer in answers],
            "stored": [
                await _events_with(ops, event_id)
                for event_id in (good.event_id, "evt_tampered", "evt_not_an_event", "evt_old")
            ],
            "status": await _status(student, code),
        }

    assert run(scenario) == {
        "answers": [(400, "WEBHOOK_INVALID")] * 5,
        "stored": [0, 0, 0, 0],
        "status": "held",
    }


def test_a_missing_event_id_falls_back_on_the_body(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> list[Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        sent = _webhook(ops, "payment.captured", await _money_in(ops, start))
        headers = {"X-Razorpay-Signature": sent.signature}
        first = await ops.client.post(WEBHOOK, content=sent.raw_body, headers=headers)
        again = await ops.client.post(WEBHOOK, content=sent.raw_body, headers=headers)
        return [first.json(), again.json()]

    assert run(scenario) == [{"new": True}, {"new": False}]


def test_what_we_dont_act_on_is_kept_answered_and_goes_no_further(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        gateway = _gateway(ops)
        at = int(ops.app.state.clock.now().timestamp())
        downtime = gateway.signed(
            {"event": "payment.downtime.started", "created_at": at, "payload": {"x": {"y": 1}}}
        )
        unreadable = gateway.signed(
            {
                "event": "payment.captured",
                "created_at": at,
                "payload": {"payment": {"entity": {"id": "pay_1"}}},
            }
        )
        strangers = _webhook(
            ops,
            "payment.captured",
            GatewayPayment("pay_1", "order_someone_elses", TOKEN, "INR", GatewayStatus.CAPTURED),
        )
        no_order = _webhook(
            ops,
            "payment.captured",
            GatewayPayment("pay_2", None, TOKEN, "INR", GatewayStatus.CAPTURED),
        )
        answers = [await _send(ops, sent) for sent in (downtime, unreadable, strangers, no_order)]
        await run_due_jobs(ops.app)
        events = [await _event(ops, sent) for sent in (downtime, unreadable, strangers, no_order)]
        return {
            "answers": [answer.status_code for answer in answers],
            "errors": [event.error for event in events],
            "processed": [event.processed_at is not None for event in events],
        }

    assert run(scenario) == {
        "answers": [200] * 4,
        "errors": [None, "unreadable", "unknown_order", "unknown_order"],
        "processed": [True] * 4,
    }


def test_a_payment_that_isnt_this_orders_token_moves_nothing_and_says_so(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        sent = _webhook(
            ops, "payment.captured", await _money_in(ops, start), amount_paise=TOKEN - 1
        )
        await _send(ops, sent)
        await run_due_jobs(ops.app)
        return {
            "status": await _status(student, code),
            "payment": (await _payment(ops, start)).status,
            "error": (await _event(ops, sent)).error,
            "audit": await _audited(ops, start),
        }

    assert run(scenario) == {
        "status": "held",
        "payment": "created",
        "error": "mismatch",
        "audit": ["payment.order_created", "payment.mismatch"],
    }


def test_processing_an_event_twice_changes_nothing_the_second_time(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        sent = _webhook(ops, "payment.captured", await _money_in(ops, start))
        await _send(ops, sent)
        await run_due_jobs(ops.app)
        first = await _event(ops, sent)
        ops.app.state.clock.advance(timedelta(minutes=1))
        async with ops.app.state.sessionmaker() as db, db.begin():
            await PaymentWebhooks(db, ops.app.state.clock).process(first.id)
            await PaymentWebhooks(db, ops.app.state.clock).process(0)
        return {
            "same stamp": (await _event(ops, sent)).processed_at == first.processed_at,
            "history": await _history(ops, code),
        }

    assert run(scenario) == {
        "same stamp": True,
        "history": [("hold", "student"), ("token_secured", "system")],
    }


def test_a_token_after_the_hold_ended_takes_the_bed_back_if_its_free(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        money = await _money_in(ops, start)
        student = await _expired(ops, student, code)
        seen: dict[str, Any] = {"beds, once it ended": await _active_beds(ops, code)}
        await _send(ops, _webhook(ops, "payment.captured", money))
        texts = RecordedTexts()
        await run_due_jobs(ops.app, texts=texts)
        booking = await student.ok("GET", f"/v1/bookings/{code}")
        seen |= {
            "status": booking["status"],
            "owner has until": booking["confirmBy"] is not None,
            "beds": await _active_beds(ops, code),
            "history": await _history(ops, code),
            "texts": [template for template, _ in _about(texts, code)],
            "audit": await _audited(ops, start),
        }
        # It's a booking like any other from here: cancelling frees the bed it took back.
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": TOKEN})
        seen["beds, once cancelled"] = await _active_beds(ops, code)
        return seen

    assert run(scenario) == {
        "beds, once it ended": 0,
        "status": "token_secured",
        "owner has until": True,
        "beds": 1,
        "history": [
            ("hold", "student"),
            ("hold_expired", "system"),
            ("late_payment_revive", "system"),
        ],
        "texts": ["booking_token_in"],
        "audit": ["payment.order_created", "payment.captured"],
        "beds, once cancelled": 0,
    }


def test_a_token_after_the_hold_ended_goes_back_if_the_bed_has_gone(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=1)
        late, held = await _held(ops, listing)
        code = held["code"]
        start = await _start(late, code)
        money = await _money_in(ops, start)
        late = await _expired(ops, late, code)
        # Someone else takes the only bed.
        other = await _student(ops)
        taken = await _hold(other, (await _quote(other, _category_of(listing)))["id"])
        assert taken.status_code == 201, taken.text
        await _send(ops, _webhook(ops, "payment.captured", money))
        texts = RecordedTexts()
        await run_due_jobs(ops.app, texts=texts)
        booking = await late.ok("GET", f"/v1/bookings/{code}")
        answer = await _callback(late, start, await _bank_says_yes(late, start))
        return {
            "status": booking["status"],
            "suggests others": booking["rebook"] is not None,
            "payment": (await _payment(ops, start)).status,
            "beds": await _active_beds(ops, code),
            "history": await _history(ops, code),
            "texts": [template for template, _ in _about(texts, code)],
            "audit": await _audited(ops, start),
            "the other's": await _status(other, taken.json()["code"]),
            "what the browser hears": answer.json()["outcome"],
        }

    assert run(scenario) == {
        "status": "expired",
        "suggests others": True,
        "payment": "captured",
        "beds": 0,
        "history": [
            ("hold", "student"),
            ("hold_expired", "system"),
            ("late_payment_refund", "system"),
        ],
        "texts": ["booking_late_refund"],
        "audit": ["payment.order_created", "payment.captured", "payment.late"],
        "the other's": "held",
        "what the browser hears": "late",
    }


def test_a_token_after_the_move_in_has_passed_goes_back_even_with_the_bed_free(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        money = await _money_in(ops, start)
        student = await _expired(ops, student, code)
        move_in = (await _booking(ops, code)).move_in
        clock = ops.app.state.clock
        clock.advance(timedelta(days=(move_in - clock.now().date()).days + 1))
        await _send(ops, _webhook(ops, "payment.captured", money))
        await run_due_jobs(ops.app)
        return {
            "history": (await _history(ops, code))[-1],
            "beds": await _active_beds(ops, code),
        }

    assert run(scenario) == {"history": ("late_payment_refund", "system"), "beds": 0}


def test_a_token_that_loses_the_race_for_a_free_bed_goes_back_cleanly(
    run: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The check says free, then the constraint says no: another booking got there in between."""

    async def always_free(*_args: Any) -> bool:
        return True

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
        monkeypatch.setattr(BedHolds, "is_free", always_free)
        await _send(ops, _webhook(ops, "payment.captured", money))
        await run_due_jobs(ops.app)
        booking = await _booking(ops, code)
        return {
            "status": booking.status,
            "token stamp": booking.token_secured_at,
            "history": (await _history(ops, code))[-1],
            "payment": (await _payment(ops, start)).status,
            "beds": await _active_beds(ops, code),
            "the other's": await _status(other, taken.json()["code"]),
        }

    assert run(scenario) == {
        "status": "expired",
        "token stamp": None,
        "history": ("late_payment_refund", "system"),
        "payment": "captured",
        "beds": 0,
        "the other's": "held",
    }


def test_a_token_after_the_student_cancelled_moves_nothing_and_is_marked_late(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        money = await _money_in(ops, start)
        await student.ok("POST", f"/v1/bookings/{code}/cancel", json={"refundPaise": 0})
        await _send(ops, _webhook(ops, "payment.captured", money))
        await run_due_jobs(ops.app)
        return {
            "status": await _status(student, code),
            "payment": (await _payment(ops, start)).status,
            "audit": await _audited(ops, start),
        }

    assert run(scenario) == {
        "status": "cancelled",
        "payment": "captured",
        "audit": ["payment.order_created", "payment.captured", "payment.late"],
    }


def test_a_checkout_after_the_hold_ended_takes_the_bed_back_too(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        proof = await _bank_says_yes(student, start)
        student = await _expired(ops, student, code)
        answer = await _callback(student, start, proof)
        return {
            "outcome": answer.json()["outcome"],
            "status": await _status(student, code),
            "again": (await _callback(student, start, proof)).json()["outcome"],
        }

    assert run(scenario) == {"outcome": "paid", "status": "token_secured", "again": "paid"}


def test_a_late_token_at_a_pg_that_confirms_itself_confirms_at_once(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=1)
        await ops.ok("PATCH", f"/v1/ops/properties/{listing['id']}", json={"instantConfirm": True})
        student, held = await _held(ops, listing)
        code = held["code"]
        start = await _start(student, code)
        money = await _money_in(ops, start)
        student = await _expired(ops, student, code)
        await _send(ops, _webhook(ops, "payment.captured", money))
        await run_due_jobs(ops.app)
        return {"status": await _status(student, code), "last": (await _history(ops, code))[-1]}

    assert run(scenario) == {"status": "confirmed", "last": ("confirm", "system")}


def test_the_gateway_a_webhook_is_stored_under_is_the_one_in_use(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> str:
        assert isinstance(ops.app.state.payment_gateway, FakeGateway)
        student, code = await _held_booking(ops)
        start = await _start(student, code)
        sent = _webhook(
            ops, "payment.failed", await _money_in(ops, start), status=GatewayStatus.FAILED
        )
        await _send(ops, sent)
        return (await _event(ops, sent)).provider

    assert run(scenario) == "fake"
