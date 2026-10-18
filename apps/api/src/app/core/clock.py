"""The injectable clock: the only place the application reads the current time (CLAUDE.md).

Domain code receives times as arguments; services, jobs and middleware ask a ``Clock``; tests use
``FrozenClock`` to stop and move time. ``now()`` is always timezone-aware UTC.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Protocol

from fastapi import Depends, Request

from app.core.calendar import india_date


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """A clock for tests: it stands still until moved with ``advance`` or ``set``."""

    def __init__(self, at: datetime) -> None:
        self._now = _as_utc(at)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta

    def set(self, at: datetime) -> None:
        self._now = _as_utc(at)


def _as_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        msg = "the clock needs a timezone-aware datetime"
        raise ValueError(msg)
    return moment.astimezone(UTC)


def today_in_india(clock: Clock) -> date:
    return india_date(clock.now())


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


ClockDep = Annotated[Clock, Depends(get_clock)]
