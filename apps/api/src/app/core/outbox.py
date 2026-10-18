"""The transactional outbox: background jobs created in the same transaction as their cause.

``enqueue()`` adds a job inside the caller's transaction, so a job exists exactly when the change
that caused it was committed (ARCHITECTURE §5). Workers claim due jobs with
``FOR UPDATE SKIP LOCKED``, so no two workers ever hold the same job. A handler's database work
and the job's "done" mark commit together. A failed job is retried with exponential backoff and
jitter, then marked ``dead`` after ``max_attempts``. A worker that dies mid-job loses its lease
and the job is claimed again. Handlers must therefore be idempotent: an external effect (an SMS,
a gateway call) can happen more than once.
"""

import asyncio
import contextlib
import random
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

import structlog
from opentelemetry import metrics
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Text,
    and_,
    delete,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model
from app.core.pii import mask_text

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.core.clock import Clock

type JobPayload = dict[str, Any]

DEFAULT_MAX_ATTEMPTS: Final = 10
FIRST_RETRY_DELAY: Final = timedelta(seconds=10)
MAX_RETRY_DELAY: Final = timedelta(hours=1)
DONE_RETENTION: Final = timedelta(days=7)
DEAD_RETENTION: Final = timedelta(days=30)
OUTBOX_CLEANUP: Final = "outbox.cleanup"
_MAX_ERROR_LENGTH: Final = 2000

logger = structlog.stdlib.get_logger(__name__)

_meter = metrics.get_meter("app.outbox")
_jobs_finished = _meter.create_counter("outbox.jobs", unit="{job}", description="Jobs finished")
_job_duration = _meter.create_histogram("outbox.job.duration", unit="ms")
_job_lag = _meter.create_histogram("outbox.job.lag", unit="ms", description="Due until started")


class OutboxJob(Model):
    __tablename__ = "outbox_jobs"

    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(Text)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dedupe_key: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'running', 'done', 'dead')", name="status"),
        CheckConstraint("attempts >= 0", name="attempts"),
        CheckConstraint("max_attempts > 0", name="max_attempts"),
        Index("ix_outbox_jobs_status_run_at", "status", "run_at"),
        Index(
            "uq_outbox_jobs_dedupe_key",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
    )


async def enqueue(
    session: AsyncSession,
    kind: str,
    payload: JobPayload,
    *,
    clock: Clock,
    run_at: datetime | None = None,
    dedupe_key: str | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> bool:
    """Add a job in the caller's transaction; it exists only if that transaction commits.

    With a ``dedupe_key`` the job is added at most once, ever; returns False if it already was.
    """
    statement = insert(OutboxJob).values(
        kind=kind,
        payload=payload,
        run_at=run_at or clock.now(),
        max_attempts=max_attempts,
        dedupe_key=dedupe_key,
    )
    if dedupe_key is not None:
        statement = statement.on_conflict_do_nothing(
            index_elements=[OutboxJob.dedupe_key], index_where=OutboxJob.dedupe_key.is_not(None)
        )
    result = await session.execute(statement.returning(OutboxJob.id))
    return result.scalar_one_or_none() is not None


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    id: int
    kind: str
    payload: JobPayload
    attempt: int
    max_attempts: int
    run_at: datetime


async def claim(
    session: AsyncSession, *, worker_id: str, now: datetime, lease: timedelta, limit: int
) -> list[ClaimedJob]:
    """Lease up to ``limit`` due jobs to ``worker_id`` until ``now + lease``."""
    due = (
        select(OutboxJob.id)
        .where(
            or_(
                and_(OutboxJob.status == "pending", OutboxJob.run_at <= now),
                # The worker holding it died: its lease ran out, so the job is up for grabs.
                and_(OutboxJob.status == "running", OutboxJob.locked_until < now),
            )
        )
        .order_by(OutboxJob.run_at, OutboxJob.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(
        update(OutboxJob)
        .where(OutboxJob.id.in_(due))
        .values(
            status="running",
            attempts=OutboxJob.attempts + 1,
            locked_by=worker_id,
            locked_until=now + lease,
        )
        .returning(
            OutboxJob.id,
            OutboxJob.kind,
            OutboxJob.payload,
            OutboxJob.attempts,
            OutboxJob.max_attempts,
            OutboxJob.run_at,
        )
        .execution_options(synchronize_session=False)
    )
    return [ClaimedJob(*row) for row in result.all()]


async def mark_done(
    session: AsyncSession, job: ClaimedJob, *, worker_id: str, now: datetime
) -> bool:
    """Mark ``job`` done if ``worker_id`` still holds it; False means the lease was lost."""
    result = await session.execute(
        update(OutboxJob)
        .where(
            OutboxJob.id == job.id,
            OutboxJob.status == "running",
            OutboxJob.locked_by == worker_id,
        )
        .values(status="done", completed_at=now, locked_by=None, locked_until=None, last_error=None)
        .returning(OutboxJob.id)
        .execution_options(synchronize_session=False)
    )
    return result.scalar_one_or_none() is not None


async def mark_failed(
    session: AsyncSession,
    job: ClaimedJob,
    *,
    worker_id: str,
    error: str,
    retry_at: datetime | None,
) -> str | None:
    """Put ``job`` back for a retry at ``retry_at``, or mark it dead when that is None.

    Returns the new status, or None if ``worker_id`` no longer holds the job.
    """
    status = "dead" if retry_at is None else "pending"
    values: dict[str, object] = {
        "status": status,
        "last_error": error,
        "locked_by": None,
        "locked_until": None,
    }
    if retry_at is not None:
        values["run_at"] = retry_at
    result = await session.execute(
        update(OutboxJob)
        .where(
            OutboxJob.id == job.id,
            OutboxJob.status == "running",
            OutboxJob.locked_by == worker_id,
        )
        .values(values)
        .returning(OutboxJob.id)
        .execution_options(synchronize_session=False)
    )
    return status if result.scalar_one_or_none() is not None else None


def retry_delay(
    attempt: int,
    rng: random.Random,
    *,
    first: timedelta = FIRST_RETRY_DELAY,
    cap: timedelta = MAX_RETRY_DELAY,
) -> timedelta:
    """Exponential backoff with jitter: between half of and all of ``first * 2^(attempt - 1)``,
    never more than ``cap``. The jitter keeps failed jobs from retrying in lockstep."""
    ceiling = min(cap, first * (1 << min(max(attempt - 1, 0), 32)))
    return ceiling / 2 + ceiling / 2 * rng.random()


@dataclass(frozen=True, slots=True)
class JobContext:
    """What a handler gets. Its database work belongs to ``session``'s transaction, which the
    worker commits together with the job's "done" mark; a handler never commits itself."""

    session: AsyncSession
    clock: Clock
    job_id: int
    attempt: int


type JobHandler = Callable[[JobContext, JobPayload], Awaitable[None]]


class JobRegistry:
    """Which handler runs each job kind."""

    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}

    def register(self, kind: str, handler: JobHandler) -> None:
        if kind in self._handlers:
            msg = f"a handler for {kind!r} is already registered"
            raise ValueError(msg)
        self._handlers[kind] = handler

    def get(self, kind: str) -> JobHandler | None:
        return self._handlers.get(kind)

    @property
    def kinds(self) -> frozenset[str]:
        return frozenset(self._handlers)


class _LeaseLostError(Exception):
    pass


def _milliseconds(delta: timedelta) -> float:
    return delta / timedelta(milliseconds=1)


class OutboxWorker:
    """One consumer: claims a batch of due jobs, runs them one by one, repeats."""

    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        registry: JobRegistry,
        clock: Clock,
        worker_id: str,
        batch_size: int = 10,
        lease: timedelta = timedelta(minutes=5),
        idle_wait: timedelta = timedelta(seconds=1),
        rng: random.Random | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._registry = registry
        self._clock = clock
        self._worker_id = worker_id
        self._batch_size = batch_size
        self._lease = lease
        self._idle_wait = idle_wait
        self._rng = rng or random.Random()  # noqa: S311 - jitter, not cryptography

    async def run(self, stop: asyncio.Event) -> None:
        """Process jobs until ``stop`` is set, finishing the batch in hand first."""
        failures = 0
        while not stop.is_set():
            try:
                processed = await self.run_once()
            except (SQLAlchemyError, OSError) as error:
                failures += 1
                processed = 0
                wait = retry_delay(
                    failures, self._rng, first=self._idle_wait, cap=timedelta(seconds=30)
                )
                logger.warning(
                    "outbox claim failed; backing off",
                    worker=self._worker_id,
                    error=type(error).__name__,
                    retry_in_s=round(wait.total_seconds(), 1),
                )
            else:
                failures = 0
                wait = self._idle_wait
            if processed == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=wait.total_seconds())

    async def run_once(self) -> int:
        """Claim one batch and process it; returns how many jobs it took."""
        async with self._sessionmaker() as session, session.begin():
            jobs = await claim(
                session,
                worker_id=self._worker_id,
                now=self._clock.now(),
                lease=self._lease,
                limit=self._batch_size,
            )
        for job in jobs:
            await self._process(job)
        return len(jobs)

    async def _process(self, job: ClaimedJob) -> None:
        log = logger.bind(job_id=job.id, kind=job.kind, attempt=job.attempt)
        handler = self._registry.get(job.kind)
        if handler is None:
            await self._fail(job, log, "no handler is registered for this kind", dead=True)
            return
        if job.attempt > job.max_attempts:  # its lease ran out on the last allowed attempt
            await self._fail(job, log, "attempts exhausted", dead=True)
            return

        _job_lag.record(_milliseconds(self._clock.now() - job.run_at), {"kind": job.kind})
        started = time.perf_counter()
        try:
            async with self._sessionmaker() as session, session.begin():
                context = JobContext(
                    session=session, clock=self._clock, job_id=job.id, attempt=job.attempt
                )
                await handler(context, job.payload)
                done = await mark_done(
                    session, job, worker_id=self._worker_id, now=self._clock.now()
                )
                if not done:
                    raise _LeaseLostError
        except _LeaseLostError:
            log.warning("outbox job lease lost; its work was rolled back")
            return
        except Exception as error:  # noqa: BLE001 - a failing handler must never stop the worker
            await self._fail(job, log, f"{type(error).__name__}: {error}")
            return
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            _job_duration.record(duration_ms, {"kind": job.kind})
        _jobs_finished.add(1, {"kind": job.kind, "outcome": "done"})
        log.info("outbox job done", duration_ms=round(duration_ms, 1))

    async def _fail(
        self, job: ClaimedJob, log: structlog.stdlib.BoundLogger, error: str, *, dead: bool = False
    ) -> None:
        exhausted = dead or job.attempt >= job.max_attempts
        retry_at = None if exhausted else self._clock.now() + retry_delay(job.attempt, self._rng)
        message = mask_text(error)[:_MAX_ERROR_LENGTH]
        try:
            async with self._sessionmaker() as session, session.begin():
                status = await mark_failed(
                    session, job, worker_id=self._worker_id, error=message, retry_at=retry_at
                )
        except SQLAlchemyError, OSError:
            log.exception("could not record an outbox job failure; its lease will run out")
            return
        if status == "dead":
            _jobs_finished.add(1, {"kind": job.kind, "outcome": "dead"})
            log.error("outbox job dead", error=message)
        elif status == "pending":
            _jobs_finished.add(1, {"kind": job.kind, "outcome": "retry"})
            log.warning("outbox job failed; will retry", error=message, retry_at=retry_at)
        else:
            log.warning("outbox job lease lost before its failure was recorded")


async def delete_finished_jobs(context: JobContext, _payload: JobPayload) -> None:
    """Periodic cleanup: drop done jobs after 7 days and dead ones after 30."""
    now = context.clock.now()
    await context.session.execute(
        delete(OutboxJob).where(
            or_(
                and_(OutboxJob.status == "done", OutboxJob.completed_at < now - DONE_RETENTION),
                and_(OutboxJob.status == "dead", OutboxJob.updated_at < now - DEAD_RETENTION),
            )
        )
    )
