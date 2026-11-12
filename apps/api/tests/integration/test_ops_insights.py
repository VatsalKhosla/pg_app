"""The staff dashboard's numbers (GET /v1/ops/insights): the weeks line up, and a booking counts."""

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

import pytest

from app.config import Settings
from app.modules.identity.domain.sessions import SessionKind
from tests.flags import FixedFlags
from tests.integration.test_booking_board import _token_in
from tests.integration.test_booking_student import _again
from tests.staff_api import Staff, run_as_staff

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


def test_the_dashboard_counts_each_week_and_lists_every_listing_status(
    run: Callable[..., Any],
) -> None:
    async def scenario(ops: Staff) -> tuple[dict[str, Any], dict[str, Any]]:
        before = await ops.ok("GET", "/v1/ops/insights", params={"weeks": 8})
        await _token_in(ops)
        ops = await _again(ops, kind=SessionKind.STAFF)
        after = await ops.ok("GET", "/v1/ops/insights", params={"weeks": 8})
        return before, after

    before, after = run(scenario)

    weeks = [date.fromisoformat(week) for week in after["weeks"]]
    assert len(weeks) == 8
    assert all(week.weekday() == 0 for week in weeks)
    assert weeks == sorted(weeks)
    for series in ("tokensSecured", "visitsRequested", "feesInvoicedPaise"):
        assert len(after[series]) == 8
    # The token came in this week: the last week's count went up by one.
    assert after["tokensSecured"][-1] == before["tokensSecured"][-1] + 1
    assert {item["status"] for item in after["listings"]} >= {"published"}
    assert "statuses" in after["board"]
