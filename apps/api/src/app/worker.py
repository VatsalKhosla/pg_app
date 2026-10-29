"""Background worker: runs outbox jobs and periodic schedules (``python -m app.worker``).

Several consumers claim jobs concurrently (``WORKER_CONCURRENCY``), the scheduler enqueues
periodic jobs, and a heartbeat file shows the process is alive (read by ``make health`` locally
and by a container health check in production). SIGINT or SIGTERM stops claiming, lets the jobs
in hand finish and exits 0. Losing the database doesn't stop the worker: it logs, backs off and
retries until the database is back or it is told to stop.
"""

import argparse
import asyncio
import contextlib
import os
import signal
import socket
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import structlog

from app.config import Settings
from app.core.clock import Clock, SystemClock
from app.core.db import create_engine, create_sessionmaker
from app.core.logging import configure_logging
from app.core.outbox import JobRegistry, OutboxWorker
from app.core.scheduler import ScheduledJob, Scheduler
from app.core.texts import ConsoleTexts, NoTexts
from app.core.web_cache import NoWebCache, SignedWebCache, WebCache
from app.jobs import SCHEDULES, build_registry
from app.modules.media.adapters.s3 import S3Storage
from app.modules.media.service import Buckets

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = structlog.stdlib.get_logger("app.worker")

DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 5.0
# Calls to other services give up as the API's own do (backend rules).
PROVIDER_TIMEOUT = httpx.Timeout(10.0, connect=3.0)


def web_cache(settings: Settings, http: httpx.AsyncClient) -> WebCache:
    """The web app to revalidate (ADR 0032), when it shares a secret with the API."""
    if settings.revalidate_secret is None:
        return NoWebCache()
    return SignedWebCache(http, site_url=settings.site_url, secret=settings.revalidate_secret)


async def heartbeat(
    *,
    stop: asyncio.Event,
    heartbeat_file: Path | None,
    interval: float,
    beat: asyncio.Event | None = None,
) -> None:
    """Touch the heartbeat file every ``interval`` seconds until ``stop`` is set.

    ``beat`` (optional) is set after every heartbeat, so callers can wait for one.
    """
    while not stop.is_set():
        if heartbeat_file is not None:
            # A thread, so a slow disk (NFS, a container volume) can't stall the event loop.
            await asyncio.to_thread(heartbeat_file.touch)
        if beat is not None:
            beat.set()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)


async def serve(
    settings: Settings,
    *,
    stop: asyncio.Event,
    heartbeat_file: Path | None,
    heartbeat_interval: float,
    clock: Clock,
    registry: JobRegistry,
    schedules: Sequence[ScheduledJob],
) -> None:
    engine = create_engine(settings, application_name="pg-platform-worker")
    sessionmaker = create_sessionmaker(engine)
    identity = f"{socket.gethostname()}:{os.getpid()}"
    logger.info(
        "worker started",
        consumers=settings.worker_concurrency,
        job_kinds=sorted(registry.kinds),
        schedules=[job.name for job in schedules],
    )
    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(
                heartbeat(stop=stop, heartbeat_file=heartbeat_file, interval=heartbeat_interval)
            )
            group.create_task(
                Scheduler(sessionmaker=sessionmaker, clock=clock, jobs=schedules).run(stop)
            )
            for number in range(settings.worker_concurrency):
                consumer = OutboxWorker(
                    sessionmaker=sessionmaker,
                    registry=registry,
                    clock=clock,
                    worker_id=f"{identity}:{number}",
                    batch_size=settings.worker_batch_size,
                    lease=timedelta(seconds=settings.outbox_lease_seconds),
                    idle_wait=timedelta(seconds=settings.worker_poll_interval_seconds),
                )
                group.create_task(consumer.run(stop))
    finally:
        await engine.dispose()
        logger.info("worker stopped")


async def _serve_until_signalled(
    settings: Settings, *, heartbeat_file: Path | None, heartbeat_interval: float
) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    async with httpx.AsyncClient(timeout=PROVIDER_TIMEOUT) as http:
        await serve(
            settings,
            stop=stop,
            heartbeat_file=heartbeat_file,
            heartbeat_interval=heartbeat_interval,
            clock=SystemClock(),
            registry=build_registry(
                storage=S3Storage.from_settings(settings),
                buckets=Buckets.from_settings(settings),
                web_cache=web_cache(settings, http),
                texts=ConsoleTexts() if settings.text_sender == "console" else NoTexts(),
            ),
            schedules=SCHEDULES,
        )


def _positive_seconds(value: str) -> float:
    seconds = float(value)
    if seconds <= 0:
        msg = f"must be greater than zero, got {value}"
        raise argparse.ArgumentTypeError(msg)
    return seconds


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.worker", description=__doc__)
    parser.add_argument(
        "--heartbeat-file",
        type=Path,
        default=None,
        help="file to touch while the worker is alive (default: none)",
    )
    parser.add_argument(
        "--heartbeat-interval",
        type=_positive_seconds,
        default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        help="seconds between heartbeats (default: %(default)s)",
    )
    args = parser.parse_args(argv)
    heartbeat_file: Path | None = args.heartbeat_file
    interval: float = args.heartbeat_interval

    settings = Settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)
    if heartbeat_file is not None:
        heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(
        _serve_until_signalled(settings, heartbeat_file=heartbeat_file, heartbeat_interval=interval)
    )


if __name__ == "__main__":
    main()
