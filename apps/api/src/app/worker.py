"""Background worker entrypoint: ``python -m app.worker``.

Step 0.4 adds outbox job processing and the scheduler. Until then the worker proves the process
life cycle the platform relies on: it starts, reports liveness by touching a heartbeat file (read
by ``make health`` locally and by a container health check in production) and shuts down cleanly
on SIGINT or SIGTERM.
"""

import argparse
import asyncio
import contextlib
import logging
import signal
from pathlib import Path

logger = logging.getLogger("app.worker")

DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 5.0
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


async def run(
    *,
    stop: asyncio.Event,
    heartbeat_file: Path | None,
    interval: float,
    beat: asyncio.Event | None = None,
) -> None:
    """Touch the heartbeat file every ``interval`` seconds until ``stop`` is set.

    ``beat`` (optional) is set after every heartbeat, so callers can wait for one.
    """
    logger.info("worker started")
    while not stop.is_set():
        if heartbeat_file is not None:
            # A thread, so a slow disk (NFS, a container volume) can't stall the event loop.
            await asyncio.to_thread(heartbeat_file.touch)
        if beat is not None:
            beat.set()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)
    logger.info("worker stopped")


async def _serve(*, heartbeat_file: Path | None, interval: float) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await run(stop=stop, heartbeat_file=heartbeat_file, interval=interval)


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

    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    if heartbeat_file is not None:
        heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(_serve(heartbeat_file=heartbeat_file, interval=interval))


if __name__ == "__main__":
    main()
