"""An owner's business at a glance (GET /v1/owner/overview, ADR 0071): beds today, the tenants we
placed month by month with their booked rent, our fees, and what waits for the owner."""

from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any

import pytest

from app.config import Settings
from app.core.calendar import india_date
from app.core.outbox import enqueue
from app.modules.booking.jobs import CHECK_WINDOWS
from tests.flags import FixedFlags
from tests.integration.test_booking_check_in import MOVED_IN, _confirmed
from tests.integration.test_booking_confirmation import _booking, _held, _owner_of, _secure
from tests.integration.test_booking_holds import _listing
from tests.integration.test_booking_student import _again
from tests.jobs import run_due_jobs
from tests.staff_api import Staff, run_as_staff

pytestmark = pytest.mark.integration

OVERVIEW = "/v1/owner/overview"


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


def test_a_new_owner_sees_their_beds_and_nothing_placed_yet(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=2)
        owner = await _owner_of(ops, listing)
        return {"overview": await owner.ok("GET", OVERVIEW, params={"months": 6})}

    overview = run(scenario)["overview"]

    months = [date.fromisoformat(month) for month in overview["months"]]
    assert len(months) == 6
    assert all(month.day == 1 for month in months)
    assert months == sorted(months)
    assert months[-1] == date.fromisoformat(overview["today"]).replace(day=1)
    assert (overview["beds"], overview["bedsTaken"]) == (2, 0)
    [pg] = overview["properties"]
    assert (pg["beds"], pg["bedsTaken"], pg["status"]) == (2, 0, "published")
    assert overview["moveIns"] == [0] * 6
    assert overview["rentPaise"] == [0] * 6
    for zero in ("tenantsPlaced", "tenantsNow", "rentNowPaise", "rentBookedPaise", "feesPaise"):
        assert overview[zero] == 0
    assert (overview["bookingsToConfirm"], overview["confirmBy"]) == (0, None)


def test_a_booking_waiting_for_the_owner_shows_with_its_deadline(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        listing = await _listing(ops, beds=2)
        owner = await _owner_of(ops, listing)
        _, held = await _held(ops, listing)
        await _secure(ops, held["code"])
        owner = await _again(owner)
        return {"overview": await owner.ok("GET", OVERVIEW), "booking": held["code"]}

    seen = run(scenario)
    overview = seen["overview"]

    assert overview["bookingsToConfirm"] == 1
    assert overview["confirmBy"] is not None
    # Its bed is held from the move-in day on, which hasn't come: today both beds are free.
    assert (overview["beds"], overview["bedsTaken"]) == (2, 0)
    assert overview["tenantsPlaced"] == 0


def test_a_tenant_we_placed_counts_with_their_rent_and_our_fee(run: Callable[..., Any]) -> None:
    async def scenario(ops: Staff) -> dict[str, Any]:
        student, owner, code = await _confirmed(ops)
        ops.app.state.clock.set(MOVED_IN)
        student = await _again(student)
        await student.ok("POST", f"/v1/bookings/{code}/check-in")
        ops.app.state.clock.advance(timedelta(hours=24))
        async with ops.app.state.sessionmaker() as db, db.begin():
            await enqueue(db, CHECK_WINDOWS, {}, clock=ops.app.state.clock)
        await run_due_jobs(ops.app)
        booking = await _booking(ops, code)
        owner = await _again(owner)
        return {
            "overview": await owner.ok("GET", OVERVIEW),
            "invoices": await owner.ok("GET", "/v1/owner/invoices"),
            "rent": booking.monthly_rent_paise,
            "months": booking.stay_months,
            "moved_in": booking.move_in,
            "today": india_date(ops.app.state.clock.now()),
        }

    seen = run(scenario)
    overview, rent = seen["overview"], seen["rent"]

    assert (overview["tenantsPlaced"], overview["tenantsNow"]) == (1, 1)
    assert overview["rentNowPaise"] == rent
    assert overview["rentBookedPaise"] == rent * seen["months"]
    # The month they moved in counts them, and so does this one, which they live in.
    month = seen["moved_in"].replace(day=1)
    index = [date.fromisoformat(first) for first in overview["months"]].index(month)
    assert overview["moveIns"][index] == 1
    assert overview["rentPaise"][index] == rent
    assert overview["rentPaise"][-1] == rent
    assert sum(overview["moveIns"]) == 1
    # Our fee is the invoice, GST included; what's unpaid is what's left after the token.
    [invoice] = seen["invoices"]["items"]
    assert overview["feesPaise"] == invoice["totalPaise"]
    assert overview["invoicesUnpaid"] == (1 if invoice["status"] == "issued" else 0)
    assert overview["feesDuePaise"] == (
        invoice["balanceDuePaise"] if invoice["status"] == "issued" else 0
    )
    assert overview["rentAfterFeesPaise"] == overview["rentBookedPaise"] - overview["feesPaise"]
    assert (overview["beds"], overview["bedsTaken"]) == (1, 1)
    assert overview["today"] == seen["today"].isoformat()
