import asyncio
import signal
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest

from app.worker import main, run

if TYPE_CHECKING:
    from pathlib import Path


def test_run_beats_then_stops_promptly(tmp_path: Path) -> None:
    heartbeat = tmp_path / "worker.heartbeat"

    async def scenario() -> None:
        stop, beat = asyncio.Event(), asyncio.Event()
        worker = asyncio.create_task(
            run(stop=stop, heartbeat_file=heartbeat, interval=60, beat=beat)
        )
        await asyncio.wait_for(beat.wait(), timeout=5)
        stop.set()
        await asyncio.wait_for(worker, timeout=1)  # far sooner than the 60 s interval

    asyncio.run(scenario())
    assert heartbeat.exists()


def test_worker_process_exits_cleanly_on_sigterm(tmp_path: Path) -> None:
    # SIGTERM is what ECS (and Docker) send to stop a container.
    heartbeat = tmp_path / "worker.heartbeat"
    command = [sys.executable, "-m", "app.worker", "--heartbeat-file", str(heartbeat)]
    with subprocess.Popen(
        [*command, "--heartbeat-interval", "0.05"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ) as process:
        deadline = time.monotonic() + 15
        while not heartbeat.exists():
            assert process.poll() is None, "worker exited before its first heartbeat"
            assert time.monotonic() < deadline, "no heartbeat within 15 s"
            time.sleep(0.05)

        process.send_signal(signal.SIGTERM)
        output, _ = process.communicate(timeout=15)

    assert process.returncode == 0
    assert "worker started" in output
    assert "worker stopped" in output


@pytest.mark.parametrize("interval", ["0", "-1"])
def test_heartbeat_interval_must_be_positive(interval: str) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--heartbeat-interval", interval])

    assert exit_info.value.code == 2
