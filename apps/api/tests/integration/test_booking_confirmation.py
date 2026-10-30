"""The confirmation flow in the API (step 5.4, ADR 0048): once the token is in, the owner (or ops)
confirms or rejects; a PG that confirms itself does so at once; an owner who doesn't answer in
time loses the booking. Each change texts the people it concerns."""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.config import Settings
from app.core.actor import Role
from app.core.errors import InvalidTransitionError
from app.core.outbox import enqueue
from app.modules.booking.jobs import CONFIRMATION_TIMEOUTS
from app.modules.booking.models import Booking, BookingEventRecord
from app.modules.booking.service import BookingSystem, bookings_part
from app.modules.identity.domain.sessions import SessionKind
from app.modules.inventory.models import InventoryAllocation
from tests.flags import FixedFlags
from tests.integration.test_booking_holds import _category_of, _hold, _listing, _quote, _student
from tests.jobs import RecordedTexts, run_due_jobs
from tests.staff_api import NOW, Staff, as_owner, run_as_staff, sign_in

pytestmark = pytest.mark.integration


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


async def _held(ops: Staff, listing: dict[str, Any]) -> tuple[Staff, dict[str, Any]]:
    """A student, and the booking they hold at ``listing``."""
    student = await _student(ops)
    response = await _hold(student, (await _quote(student, _category_of(listing)))["id"])
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return student, body


async def _booking(ops: Staff, code: str) -> Booking:
    async with ops.app.state.sessionmaker() as db:
        found: Booking | None = await db.scalar(select(Booking).where(Booking.code == code))
        assert found is not None
        return found


async def _secure(ops: Staff, code: str, *, paid: int | None = None) -> None:
    """The token comes in, as a verified payment will make it (Phase 6)."""
    booking = await _booking(ops, code)
    async with ops.app.state.sessionmaker() as db, db.begin():
        await BookingSystem(db, ops.app.state.clock).secure_token(
            booking.public_id, paid_paise=booking.token_paise if paid is None else paid
        )


async def _history(ops: Staff, code: str) -> list[tuple[str, str]]:
    booking = await _booking(ops, code)
    async with ops.app.state.sessionmaker() as db:
        rows = await db.execute(
            select(BookingEventRecord.event, BookingEventRecord.actor_type)
            .where(BookingEventRecord.booking_id == booking.id)
            .order_by(BookingEventRecord.id)
        )
        return [(event, actor) for event, actor in rows]


def _about(texts: RecordedTexts, code: str) -> list[tuple[str, dict[str, str]]]:
    """The texts about this booking: the shared database holds other tests' jobs too."""
    return [(template, values) for _, template, values in texts.sent if values.get("code") == code]


async def _owner_of(ops: Staff, listing: dict[str, Any]) -> Staff:
    """The listing's owner, signed in by phone."""
    return await as_owner(ops, listing["owner"])


def test_an_owner_confirms_a_booking_once_the_token_is_in(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=1)
        owner = await _owner_of(ops, listing)
        student, held = await _held(ops, listing)
        code = held["code"]
        seen: dict[str, Any] = {
            "too soon": (await owner.call("POST", f"/v1/owner/bookings/{code}/confirm")).json()[
                "code"
            ]
        }
        await _secure(ops, code)
        texts = RecordedTexts()
        await run_due_jobs(ops.app, texts=texts)
        seen["waiting"] = await owner.ok("GET", f"/v1/owner/bookings/{code}")
        seen["confirmed"] = await owner.ok("POST", f"/v1/owner/bookings/{code}/confirm")
        seen["again"] = (await owner.call("POST", f"/v1/owner/bookings/{code}/confirm")).json()[
            "code"
        ]
        seen["student sees"] = (await student.ok("GET", f"/v1/bookings/{code}"))["status"]
        await run_due_jobs(ops.app, texts=texts)
        seen["texts"] = _about(texts, code)
        seen["history"] = await _history(ops, code)
        seen["confirmed at"] = (await _booking(ops, code)).confirmed_at
        return seen

    seen = run(scenario)

    assert seen["too soon"] == "INVALID_TRANSITION"
    waiting = seen["waiting"]
    assert waiting["status"] == "token_secured"
    # The owner has 12 hours from the token to answer.
    assert waiting["confirmBy"] == (NOW + timedelta(hours=12)).isoformat().replace("+00:00", "Z")
    assert (waiting["room"], waiting["bed"]) == ("101", "A")
    assert seen["confirmed"]["status"] == "confirmed"
    assert seen["again"] == "INVALID_TRANSITION"
    assert seen["student sees"] == "confirmed"
    assert seen["confirmed at"] == NOW
    assert seen["history"] == [
        ("hold", "student"),
        ("token_secured", "system"),
        ("confirm", "owner"),
    ]
    templates = [template for template, _ in seen["texts"]]
    assert templates == ["booking_token_in", "booking_confirmed"]
    token_in, confirmed = (values for _, values in seen["texts"])
    # 12 hours after 3:30 pm in India.
    assert token_in["confirm_by"] == "Thu 15 Jul, 3:30 am"
    # Only once it's confirmed does the student get the address (rule 11).
    assert confirmed["address"] == "House 1, a fictional lane, Satya Niketan"
    assert "address" not in token_in


def test_ops_reject_a_booking_for_its_owner_and_the_bed_is_free_again(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=1)
        _, held = await _held(ops, listing)
        code = held["code"]
        await _secure(ops, code)
        texts = RecordedTexts()
        await run_due_jobs(ops.app, texts=texts)
        blank = await ops.call("POST", f"/v1/ops/bookings/{code}/reject", json={"reason": ""})
        rejected = await ops.ok(
            "POST",
            f"/v1/ops/bookings/{code}/reject",
            json={"reason": "  The room is under repair "},
        )
        booking = await _booking(ops, code)
        async with ops.app.state.sessionmaker() as db:
            active = await db.scalar(
                select(InventoryAllocation.is_active).where(
                    InventoryAllocation.booking_id == booking.id
                )
            )
            note = await db.scalar(
                select(BookingEventRecord.payload["note"].astext).where(
                    BookingEventRecord.booking_id == booking.id,
                    BookingEventRecord.event == "reject",
                )
            )
        await run_due_jobs(ops.app, texts=texts)
        _, again = await _held(ops, listing)
        return {
            "blank": blank.status_code,
            "status": rejected["status"],
            "ended": (booking.cancelled_by, booking.cancellation_kind, booking.cancelled_at),
            "active": active,
            "note": note,
            "texts": [template for template, _ in _about(texts, code)],
            "next student": again["status"],
        }

    assert run(scenario) == {
        "blank": 422,
        "status": "rejected",
        "ended": ("ops", "reject", NOW),
        "active": False,
        "note": "The room is under repair",
        "texts": ["booking_token_in", "booking_rejected"],
        "next student": "held",
    }


def test_an_owner_who_doesnt_answer_in_time_loses_the_booking(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=1)
        _, held = await _held(ops, listing)
        code = held["code"]
        await _secure(ops, code)
        texts = RecordedTexts()
        await run_due_jobs(ops.app, texts=texts)

        async def timeouts() -> None:
            async with ops.app.state.sessionmaker() as db, db.begin():
                await enqueue(db, CONFIRMATION_TIMEOUTS, {}, clock=ops.app.state.clock)
            await run_due_jobs(ops.app, texts=texts)

        ops.app.state.clock.advance(timedelta(hours=12) - timedelta(seconds=1))
        await timeouts()
        before = (await _booking(ops, code)).status
        ops.app.state.clock.advance(timedelta(seconds=1))
        await timeouts()
        after = await _booking(ops, code)
        # A second run finds nothing left to do.
        await timeouts()
        return {
            "before": before,
            "after": (after.status, after.version),
            "history": await _history(ops, code),
            # The token's text first; the timeout's two then go as separate jobs, in either order.
            "texts": [
                (sent := [template for template, _ in _about(texts, code)])[0],
                *sorted(sent[1:]),
            ],
        }

    assert run(scenario) == {
        "before": "token_secured",
        "after": ("rejected", 3),
        "history": [
            ("hold", "student"),
            ("token_secured", "system"),
            ("confirm_timeout", "system"),
        ],
        "texts": ["booking_token_in", "booking_confirmation_missed", "booking_not_confirmed"],
    }


def test_a_pg_that_confirms_itself_confirms_as_the_token_comes_in(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=1)
        await ops.ok("PATCH", f"/v1/ops/properties/{listing['id']}", json={"instantConfirm": True})
        _, held = await _held(ops, listing)
        await _secure(ops, held["code"])
        texts = RecordedTexts()
        await run_due_jobs(ops.app, texts=texts)
        return {
            "status": (await _booking(ops, held["code"])).status,
            "history": await _history(ops, held["code"]),
            # The owner's text and the student's go as separate jobs, in either order.
            "texts": sorted(template for template, _ in _about(texts, held["code"])),
        }

    assert run(scenario) == {
        "status": "confirmed",
        "history": [("hold", "student"), ("token_secured", "system"), ("confirm", "system")],
        "texts": ["booking_confirmed", "booking_new_confirmed"],
    }


def test_who_may_answer_a_booking_and_with_what_token(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=2)
        other_listing = await _listing(ops, beds=1)
        owner, someone_else = await _owner_of(ops, listing), await _owner_of(ops, other_listing)
        student, held = await _held(ops, listing)
        code = held["code"]
        seen: dict[str, Any] = {}
        try:
            await _secure(ops, code, paid=held["tokenPaise"] - 1)
        except InvalidTransitionError as refused:
            seen["a short payment"] = refused.detail
        await _secure(ops, code)
        path = f"/v1/owner/bookings/{code}/confirm"
        seen["another owner"] = (await someone_else.call("POST", path)).status_code
        seen["the student"] = (await student.call("POST", path)).status_code
        seen["ops on the owner's route"] = (await ops.call("POST", path)).status_code
        seen["the owner on ops' route"] = (
            await owner.call("POST", f"/v1/ops/bookings/{code}/confirm")
        ).status_code
        seen["no such booking"] = (
            await owner.call("POST", "/v1/owner/bookings/BK-0000ZZZZ/confirm")
        ).status_code
        agent = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
        seen["a field agent"] = (await agent.call("GET", f"/v1/ops/bookings/{code}")).status_code
        phone_user = await sign_in(ops.app, ops.client, Role.STUDENT, kind=SessionKind.USER)
        seen["a stranger"] = (await phone_user.call("GET", f"/v1/bookings/{code}")).status_code
        return seen

    assert run(scenario) == {
        "a short payment": "The payment isn't the booking's token.",
        "another owner": 404,
        "the student": 403,
        "ops on the owner's route": 403,
        "the owner on ops' route": 403,
        "no such booking": 404,
        "a field agent": 403,
        "a stranger": 404,
    }


def test_a_students_bookings_are_in_their_data_export(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> Any:
        listing = await _listing(ops, beds=1)
        student, held = await _held(ops, listing)
        await _secure(ops, held["code"])
        async with ops.app.state.sessionmaker() as db:
            return await bookings_part(db, student.user_id)

    part = run(scenario)

    [booking] = part["bookings"]
    assert booking["status"] == "token_secured"
    assert [step["event"] for step in booking["history"]] == ["hold", "token_secured"]
