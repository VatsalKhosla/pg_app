"""The parts of the outbox and scheduler that need no database: backoff, registry and slots."""

import random
from datetime import UTC, datetime, time, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.analytics import NoAnalytics
from app.core.outbox import FIRST_RETRY_DELAY, MAX_RETRY_DELAY, JobRegistry, retry_delay
from app.core.scheduler import DailyAt, Every, ScheduledJob, dedupe_key
from app.core.texts import NoTexts
from app.core.web_cache import NoWebCache
from app.jobs import SCHEDULES, build_registry
from app.modules.pricing.occupancy import NoBookingsYet
from app.modules.pricing.service import BAND_CHANGED, CAPS_CHANGED, RULES_CHANGED
from app.modules.search.jobs import REPRICE
from tests.storage import BUCKETS, MemoryStorage


@given(st.integers(min_value=1, max_value=10_000), st.integers(min_value=0, max_value=2**32))
def test_retry_delays_double_with_jitter_and_stay_capped(attempt: int, seed: int) -> None:
    ceiling = min(MAX_RETRY_DELAY, FIRST_RETRY_DELAY * 2 ** min(attempt - 1, 32))

    delay = retry_delay(attempt, random.Random(seed))  # noqa: S311 - test jitter

    assert ceiling / 2 <= delay <= ceiling <= MAX_RETRY_DELAY


def test_the_first_retries_come_quickly_and_later_ones_cap_at_an_hour() -> None:
    always_max = random.Random()  # noqa: S311 - test jitter
    always_max.random = lambda: 1.0  # type: ignore[method-assign]  # pin the jitter to its top

    delays = [retry_delay(attempt, always_max) for attempt in (1, 2, 3, 10, 20)]

    assert delays == [
        timedelta(seconds=10),
        timedelta(seconds=20),
        timedelta(seconds=40),
        timedelta(hours=1),
        timedelta(hours=1),
    ]


def test_a_job_kind_can_have_only_one_handler() -> None:
    async def handler(*_: object) -> None:
        return None

    registry = JobRegistry()
    registry.register("example.ping", handler)

    with pytest.raises(ValueError, match="already registered"):
        registry.register("example.ping", handler)
    assert registry.get("example.ping") is handler
    assert registry.get("example.unknown") is None


def test_every_schedule_has_a_registered_handler() -> None:
    kinds = build_registry(
        storage=MemoryStorage(),
        buckets=BUCKETS,
        web_cache=NoWebCache(),
        texts=NoTexts(),
        analytics=NoAnalytics(),
        beds=NoBookingsYet(),
    ).kinds

    assert {job.kind for job in SCHEDULES} <= kinds
    assert len({job.name for job in SCHEDULES}) == len(SCHEDULES)
    # Prices that move reprice search's summaries (step 4.7).
    assert {RULES_CHANGED, BAND_CHANGED, CAPS_CHANGED, REPRICE} <= kinds


@pytest.mark.parametrize(
    ("interval", "now", "slot"),
    [
        (
            timedelta(minutes=1),
            datetime(2027, 7, 1, 9, 5, 42, tzinfo=UTC),
            datetime(2027, 7, 1, 9, 5, tzinfo=UTC),
        ),
        (
            timedelta(minutes=5),
            datetime(2027, 7, 1, 9, 4, 59, tzinfo=UTC),
            datetime(2027, 7, 1, 9, 0, tzinfo=UTC),
        ),
        (
            timedelta(hours=1),
            datetime(2027, 7, 1, 9, 0, tzinfo=UTC),
            datetime(2027, 7, 1, 9, 0, tzinfo=UTC),
        ),
    ],
)
def test_interval_slots_start_on_round_boundaries(
    interval: timedelta, now: datetime, slot: datetime
) -> None:
    assert Every(interval).latest_slot(now) == slot


@pytest.mark.parametrize(
    ("now", "slot"),
    [
        # 10:00 in India is 04:30 UTC.
        (datetime(2027, 7, 1, 4, 30, tzinfo=UTC), datetime(2027, 7, 1, 4, 30, tzinfo=UTC)),
        (datetime(2027, 7, 1, 12, 0, tzinfo=UTC), datetime(2027, 7, 1, 4, 30, tzinfo=UTC)),
        (datetime(2027, 7, 1, 4, 29, tzinfo=UTC), datetime(2027, 6, 30, 4, 30, tzinfo=UTC)),
        # 23:00 UTC on 30 June is 04:30 on 1 July in India: before 10:00, so 30 June's slot.
        (datetime(2027, 6, 30, 23, 0, tzinfo=UTC), datetime(2027, 6, 30, 4, 30, tzinfo=UTC)),
    ],
)
def test_daily_slots_are_in_india_time(now: datetime, slot: datetime) -> None:
    assert DailyAt(time(10, 0)).latest_slot(now) == slot


def test_schedules_reject_impossible_settings() -> None:
    with pytest.raises(ValueError, match="positive"):
        Every(timedelta(0))
    with pytest.raises(ValueError, match="India time"):
        DailyAt(time(10, 0, tzinfo=UTC))


def test_dedupe_keys_name_the_schedule_and_the_slot() -> None:
    job = ScheduledJob(
        name="booking.expire_holds",
        kind="booking.expire_holds",
        schedule=Every(timedelta(minutes=1)),
    )

    assert dedupe_key(job, datetime(2027, 7, 1, 9, 5, tzinfo=UTC)) == (
        "schedule:booking.expire_holds:2027-07-01T09:05:00+00:00"
    )
