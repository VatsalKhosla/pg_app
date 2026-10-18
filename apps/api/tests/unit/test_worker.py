import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.worker import heartbeat, main


def test_heartbeat_beats_then_stops_promptly(tmp_path: Path) -> None:
    heartbeat_file = tmp_path / "worker.heartbeat"

    async def scenario() -> None:
        stop, beat = asyncio.Event(), asyncio.Event()
        task = asyncio.create_task(
            heartbeat(stop=stop, heartbeat_file=heartbeat_file, interval=60, beat=beat)
        )
        await asyncio.wait_for(beat.wait(), timeout=5)
        stop.set()
        await asyncio.wait_for(task, timeout=1)  # far sooner than the 60 s interval

    asyncio.run(scenario())
    assert heartbeat_file.exists()


def test_worker_survives_an_unreachable_database_and_exits_cleanly_on_sigterm(
    tmp_path: Path,
) -> None:
    # SIGTERM is what ECS (and Docker) send to stop a container. Nothing listens on port 9, so
    # every claim fails: the worker must keep beating, back off, and still stop cleanly.
    heartbeat_file = tmp_path / "worker.heartbeat"
    environment = os.environ | {
        "DATABASE_URL": "postgresql+asyncpg://test:test@127.0.0.1:9/test",
        "REDIS_URL": "redis://:test@127.0.0.1:9/0",
        "SECRET_KEY": "test-only-secret-key-0123456789abcdef",
        "LOG_FORMAT": "json",
    }
    command = [sys.executable, "-m", "app.worker", "--heartbeat-file", str(heartbeat_file)]
    with subprocess.Popen(
        [*command, "--heartbeat-interval", "0.05"],
        cwd=tmp_path,  # no .env here
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ) as process:
        deadline = time.monotonic() + 30
        while not heartbeat_file.exists():
            assert process.poll() is None, "worker exited before its first heartbeat"
            assert time.monotonic() < deadline, "no heartbeat within 30 s"
            time.sleep(0.05)
        time.sleep(0.5)  # long enough for the first failed claims
        assert process.poll() is None, "worker stopped on its own"

        process.send_signal(signal.SIGTERM)
        output, _ = process.communicate(timeout=30)

    assert process.returncode == 0, output
    assert "worker started" in output
    assert "outbox claim failed" in output
    assert "worker stopped" in output


@pytest.mark.parametrize("interval", ["0", "-1"])
def test_heartbeat_interval_must_be_positive(interval: str) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--heartbeat-interval", interval])

    assert exit_info.value.code == 2
