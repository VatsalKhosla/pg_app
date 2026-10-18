"""Periodic jobs that are safe with any number of workers (ARCHITECTURE §7.5).

On every tick each schedule names its latest slot (``14:05`` for "every minute", ``10:00 today``
for "daily at 10:00 India time") and enqueues one outbox job for it with the dedupe key
``schedule:<name>:<slot>``. Whichever worker gets there first creates the job; for the others
it's a no-op. A slot missed while every worker was down runs once when one comes back, not once
per missed slot: periodic jobs sweep current state, so catching up once is enough.
"""

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING, Final

import structlog
from sqlalchemy.exc import SQLAlchemyError

from app.core.calendar import INDIA
from app.core.outbox import enqueue

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.core.clock import Clock

_EPOCH: Final = datetime(1970, 1, 1, tzinfo=UTC)

logger = structlog.stdlib.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Every:
    """Every ``interval``, on boundaries counted from the Unix epoch (so every minute is :00)."""

    interval: timedelta

    def __post_init__(self) -> None:
        if self.interval <= timedelta(0):
            msg = "the interval must be positive"
            raise ValueError(msg)

    def latest_slot(self, now: datetime) -> datetime:
        return _EPOCH + ((now - _EPOCH) // self.interval) * self.interval


@dataclass(frozen=True, slots=True)
class DailyAt:
    """Once a day at ``at``, wall-clock time in India."""

    at: time

    def __post_init__(self) -> None:
        if self.at.tzinfo is not None:
            msg = "give the time without a timezone; it is read as India time"
            raise ValueError(msg)

    def latest_slot(self, now: datetime) -> datetime:
        local_now = now.astimezone(INDIA)
        slot = datetime.combine(local_now.date(), self.at, tzinfo=INDIA)
        if slot > local_now:
            slot -= timedelta(days=1)
        return slot.astimezone(UTC)


type Schedule = Every | DailyAt


@dataclass(frozen=True, slots=True)
class ScheduledJob:
    name: str
    kind: str
    schedule: Schedule


def dedupe_key(job: ScheduledJob, slot: datetime) -> str:
    return f"schedule:{job.name}:{slot.isoformat()}"


class Scheduler:
    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        clock: Clock,
        jobs: Sequence[ScheduledJob],
        tick: timedelta = timedelta(seconds=15),
    ) -> None:
        self._sessionmaker = sessionmaker
        self._clock = clock
        self._jobs = tuple(jobs)
        self._tick = tick

    async def tick_once(self) -> int:
        """Enqueue the latest slot of every schedule that hasn't been enqueued yet."""
        now = self._clock.now()
        created = 0
        async with self._sessionmaker() as session, session.begin():
            for job in self._jobs:
                slot = job.schedule.latest_slot(now)
                added = await enqueue(
                    session,
                    job.kind,
                    {"scheduledFor": slot.isoformat()},
                    clock=self._clock,
                    run_at=slot,
                    dedupe_key=dedupe_key(job, slot),
                )
                if added:
                    created += 1
                    logger.info("scheduled job enqueued", schedule=job.name, slot=slot.isoformat())
        return created

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.tick_once()
            except (SQLAlchemyError, OSError) as error:
                logger.warning("scheduler tick failed", error=type(error).__name__)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self._tick.total_seconds())
