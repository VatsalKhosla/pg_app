import asyncio
import contextlib
import random
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete, func, select

from app.core.audit import SYSTEM, AuditLog, record
from app.core.clock import FrozenClock
from app.core.outbox import (
    JobContext,
    JobPayload,
    JobRegistry,
    OutboxJob,
    OutboxWorker,
    claim,
    delete_finished_jobs,
    enqueue,
    mark_done,
)
from app.core.scheduler import DailyAt, Every, ScheduledJob, Scheduler

if TYPE_CHECKING:
    from tests.integration.conftest import RunDb, Sessionmaker

pytestmark = pytest.mark.integration

START = datetime(2027, 7, 1, 4, 30, tzinfo=UTC)
LEASE = timedelta(minutes=5)


class _AbortError(Exception):
    pass


@pytest.fixture(autouse=True)
def empty_outbox(run_db: RunDb) -> None:
    async def clear(sessionmaker: Sessionmaker) -> None:
        async with sessionmaker() as session, session.begin():
            await session.execute(delete(OutboxJob))

    run_db(clear)


async def _jobs(sessionmaker: Sessionmaker) -> list[OutboxJob]:
    async with sessionmaker() as session:
        return list((await session.scalars(select(OutboxJob).order_by(OutboxJob.id))).all())


async def _audit_count(sessionmaker: Sessionmaker, entity_id: str) -> int:
    async with sessionmaker() as session:
        count = select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == entity_id)
        return (await session.scalars(count)).one()


async def _record_entity(context: JobContext, payload: JobPayload) -> None:
    await record(
        context.session,
        clock=context.clock,
        actor=SYSTEM,
        action="test.job_ran",
        entity_type="test",
        entity_id=payload["entity"],
    )


def test_a_job_exists_only_if_its_transaction_commits(run_db: RunDb) -> None:
    clock = FrozenClock(START)

    async def scenario(sessionmaker: Sessionmaker) -> list[str]:
        async with sessionmaker() as session, session.begin():
            await enqueue(session, "test.kept", {"n": 1}, clock=clock)
        with contextlib.suppress(_AbortError):
            async with sessionmaker() as session, session.begin():
                await enqueue(session, "test.discarded", {"n": 2}, clock=clock)
                raise _AbortError
        return [job.kind for job in await _jobs(sessionmaker)]

    assert run_db(scenario) == ["test.kept"]


def test_a_dedupe_key_adds_its_job_at_most_once(run_db: RunDb) -> None:
    clock = FrozenClock(START)

    async def scenario(sessionmaker: Sessionmaker) -> tuple[list[bool], int]:
        async with sessionmaker() as session, session.begin():
            added = [
                await enqueue(session, "test.once", {}, clock=clock, dedupe_key="test:once")
                for _ in range(3)
            ]
        return added, len(await _jobs(sessionmaker))

    assert run_db(scenario) == ([True, False, False], 1)


def test_two_workers_never_claim_the_same_job(run_db: RunDb) -> None:
    clock = FrozenClock(START)

    async def drain(sessionmaker: Sessionmaker, worker_id: str) -> list[int]:
        taken: list[int] = []
        while True:
            async with sessionmaker() as session, session.begin():
                jobs = await claim(
                    session, worker_id=worker_id, now=clock.now(), lease=LEASE, limit=7
                )
                await asyncio.sleep(0.005)  # keep the rows locked while the other worker claims
            if not jobs:
                return taken
            taken.extend(job.id for job in jobs)

    async def scenario(sessionmaker: Sessionmaker) -> tuple[list[int], list[int], list[int]]:
        async with sessionmaker() as session, session.begin():
            for number in range(200):
                await enqueue(session, "test.claimed", {"n": number}, clock=clock)
        first, second = await asyncio.gather(
            drain(sessionmaker, "worker-a"), drain(sessionmaker, "worker-b")
        )
        return first, second, [job.id for job in await _jobs(sessionmaker)]

    first, second, every_job = run_db(scenario)

    assert set(first).isdisjoint(second)
    assert sorted(first + second) == sorted(every_job)
    assert first, "worker-a took no jobs"
    assert second, "worker-b took no jobs"


def test_a_handlers_work_commits_together_with_its_done_mark(run_db: RunDb) -> None:
    clock = FrozenClock(START)
    entity = f"test-{uuid.uuid4().hex}"
    registry = JobRegistry()
    registry.register("test.audited", _record_entity)

    async def scenario(sessionmaker: Sessionmaker) -> tuple[int, str, datetime | None, int]:
        async with sessionmaker() as session, session.begin():
            await enqueue(session, "test.audited", {"entity": entity}, clock=clock)
        worker = OutboxWorker(
            sessionmaker=sessionmaker, registry=registry, clock=clock, worker_id="worker-a"
        )
        processed = await worker.run_once()
        [job] = await _jobs(sessionmaker)
        return processed, job.status, job.completed_at, await _audit_count(sessionmaker, entity)

    assert run_db(scenario) == (1, "done", START, 1)


def test_a_failing_job_is_retried_with_backoff_then_dead_lettered(run_db: RunDb) -> None:
    clock = FrozenClock(START)
    entity = f"test-{uuid.uuid4().hex}"

    async def fail(context: JobContext, payload: JobPayload) -> None:
        await _record_entity(context, payload)  # rolled back with the failure
        msg = "no account for +919876543210"
        raise LookupError(msg)

    registry = JobRegistry()
    registry.register("test.failing", fail)

    async def scenario(
        sessionmaker: Sessionmaker,
    ) -> tuple[list[tuple[str, int]], list[timedelta], list[str], int]:
        async with sessionmaker() as session, session.begin():
            await enqueue(session, "test.failing", {"entity": entity}, clock=clock, max_attempts=3)
        worker = OutboxWorker(
            sessionmaker=sessionmaker,
            registry=registry,
            clock=clock,
            worker_id="worker-a",
            rng=random.Random(7),  # noqa: S311 - test jitter
        )
        states: list[tuple[str, int]] = []
        delays: list[timedelta] = []
        errors: list[str] = []
        for _ in range(3):
            assert await worker.run_once() == 1
            [job] = await _jobs(sessionmaker)
            states.append((job.status, job.attempts))
            errors.append(job.last_error or "")
            if job.status == "pending":
                delays.append(job.run_at - clock.now())
                assert await worker.run_once() == 0, "a retry ran before it was due"
                clock.set(job.run_at)
        return states, delays, errors, await _audit_count(sessionmaker, entity)

    states, delays, errors, audits = run_db(scenario)

    assert states == [("pending", 1), ("pending", 2), ("dead", 3)]
    assert timedelta(seconds=5) <= delays[0] <= timedelta(seconds=10)
    assert timedelta(seconds=10) <= delays[1] <= timedelta(seconds=20)
    assert all(error.startswith("LookupError: no account for ******3210") for error in errors)
    assert audits == 0


def test_a_job_whose_worker_died_is_taken_over_after_its_lease(run_db: RunDb) -> None:
    clock = FrozenClock(START)
    attempts_run: list[int] = []

    async def note_attempt(context: JobContext, _payload: JobPayload) -> None:
        attempts_run.append(context.attempt)

    registry = JobRegistry()
    registry.register("test.leased", note_attempt)

    async def scenario(sessionmaker: Sessionmaker) -> tuple[int, int, bool, str, int]:
        async with sessionmaker() as session, session.begin():
            await enqueue(session, "test.leased", {}, clock=clock)
        # worker-a takes the job, then dies before finishing it.
        async with sessionmaker() as session, session.begin():
            [stale] = await claim(
                session, worker_id="worker-a", now=clock.now(), lease=LEASE, limit=1
            )
        worker_b = OutboxWorker(
            sessionmaker=sessionmaker, registry=registry, clock=clock, worker_id="worker-b"
        )
        while_leased = await worker_b.run_once()
        clock.advance(LEASE + timedelta(seconds=1))
        after_lease = await worker_b.run_once()
        async with sessionmaker() as session, session.begin():  # worker-a comes back, too late
            late = await mark_done(session, stale, worker_id="worker-a", now=clock.now())
        [job] = await _jobs(sessionmaker)
        return while_leased, after_lease, late, job.status, job.attempts

    assert run_db(scenario) == (0, 1, False, "done", 2)
    assert attempts_run == [2]


def test_a_kind_without_a_handler_is_dead_lettered_at_once(run_db: RunDb) -> None:
    clock = FrozenClock(START)

    async def scenario(sessionmaker: Sessionmaker) -> tuple[str, int, str | None]:
        async with sessionmaker() as session, session.begin():
            await enqueue(session, "test.unhandled", {}, clock=clock)
        worker = OutboxWorker(
            sessionmaker=sessionmaker, registry=JobRegistry(), clock=clock, worker_id="worker-a"
        )
        await worker.run_once()
        [job] = await _jobs(sessionmaker)
        return job.status, job.attempts, job.last_error

    assert run_db(scenario) == ("dead", 1, "no handler is registered for this kind")


def test_cleanup_drops_only_old_finished_jobs(run_db: RunDb) -> None:
    clock = FrozenClock(START)

    def job(name: str, status: str, finished_days_ago: int) -> OutboxJob:
        finished = START - timedelta(days=finished_days_ago)
        return OutboxJob(
            kind=name,
            payload={},
            status=status,
            max_attempts=10,
            run_at=finished,
            completed_at=finished if status == "done" else None,
            updated_at=finished,
        )

    async def scenario(sessionmaker: Sessionmaker) -> list[str]:
        async with sessionmaker() as session, session.begin():
            session.add_all(
                [
                    job("done-8-days-ago", "done", 8),
                    job("done-yesterday", "done", 1),
                    job("dead-31-days-ago", "dead", 31),
                    job("dead-5-days-ago", "dead", 5),
                    job("pending-long-ago", "pending", 90),
                ]
            )
        async with sessionmaker() as session, session.begin():
            context = JobContext(session=session, clock=clock, job_id=0, attempt=1)
            await delete_finished_jobs(context, {})
        return sorted(job.kind for job in await _jobs(sessionmaker))

    assert run_db(scenario) == ["dead-5-days-ago", "done-yesterday", "pending-long-ago"]


def test_any_number_of_schedulers_enqueue_each_slot_once(run_db: RunDb) -> None:
    clock = FrozenClock(START + timedelta(seconds=20))  # 10:00:20 in India
    schedules = [
        ScheduledJob("test.minutely", "test.minutely", Every(timedelta(minutes=1))),
        ScheduledJob("test.daily", "test.daily", DailyAt(time(10, 0))),
    ]

    async def scenario(
        sessionmaker: Sessionmaker,
    ) -> tuple[int, int, int, list[tuple[str, datetime]]]:
        schedulers = [
            Scheduler(sessionmaker=sessionmaker, clock=clock, jobs=schedules) for _ in range(3)
        ]
        first = await asyncio.gather(*(scheduler.tick_once() for scheduler in schedulers))
        again = await schedulers[0].tick_once()
        clock.advance(timedelta(minutes=1))
        next_minute = await schedulers[1].tick_once()
        jobs = await _jobs(sessionmaker)
        return sum(first), again, next_minute, sorted((job.kind, job.run_at) for job in jobs)

    created, again, next_minute, jobs = run_db(scenario)

    assert (created, again, next_minute) == (2, 0, 1)
    assert jobs == [
        ("test.daily", START),
        ("test.minutely", START),
        ("test.minutely", START + timedelta(minutes=1)),
    ]
