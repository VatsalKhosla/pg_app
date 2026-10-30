"""The API, its worker and its migrations in one container: ``python -m app.all_in_one``.

For a host whose free plan runs one process per service and has no background workers, which is
staging for now (ADR 0047). Production runs the API and the worker as services of their own
(ARCHITECTURE §3).

It brings the database up to date and loads the geo reference data, which changes only what
differs. With ``SEED_SAMPLES=true`` (staging) it adds the fictional sample PGs, which a second run
leaves alone and production refuses. Then it runs the worker and the API side by side. When either
stops, so does the other and the container exits, for the host to start it again. A SIGTERM from
the host stops both gracefully.
"""

import os
import signal
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import FrameType

# How long a process may take to stop once asked, before it's killed.
STOP_TIMEOUT_SECONDS: Final = 20
_POLL_SECONDS: Final = 0.5


def supervise(commands: Sequence[Sequence[str]]) -> int:
    """Runs ``commands`` side by side until one ends or a SIGTERM comes, stops the rest, and
    answers the exit code of the one that ended first (0 after a SIGTERM)."""
    processes = [subprocess.Popen(command) for command in commands]  # noqa: S603 - our own commands
    stopping = False

    def stop(_signum: int, _frame: FrameType | None) -> None:
        nonlocal stopping
        stopping = True

    previous = {signum: signal.signal(signum, stop) for signum in (signal.SIGTERM, signal.SIGINT)}
    try:
        ended = None
        while ended is None and not stopping:
            ended = next((process for process in processes if process.poll() is not None), None)
            if ended is None:
                time.sleep(_POLL_SECONDS)
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        return 0 if ended is None else ended.returncode
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _run(*args: str) -> int:
    return subprocess.run([sys.executable, "-m", *args], check=False).returncode  # noqa: S603


def main() -> int:
    for step in (("alembic", "upgrade", "head"), ("app.manage", "geo", "load")):
        if (code := _run(*step)) != 0:
            return code
    # The samples are a nicety: the site starts without them if they can't be made.
    if os.environ.get("SEED_SAMPLES") == "true":
        _run("app.manage", "catalog", "samples")
    port = os.environ.get("PORT", "8000")
    return supervise(
        [
            [sys.executable, "-m", "app.worker"],
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--host",
                "0.0.0.0",  # noqa: S104 - inside the container, behind the host's proxy
                "--port",
                port,
                "--proxy-headers",
                "--no-access-log",
            ],
        ]
    )


if __name__ == "__main__":
    sys.exit(main())
