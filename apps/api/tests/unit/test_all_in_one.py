"""One container running the API and its worker (ADR 0047): the database, the geo data and, if
asked, the samples first; then, when one process stops, so does the other, and the exit code is
the one that stopped first."""

import sys
import time

import pytest

from app import all_in_one
from app.all_in_one import supervise

SLEEPS = [sys.executable, "-c", "import time; time.sleep(60)"]


def test_when_one_process_ends_the_other_is_stopped() -> None:
    started = time.monotonic()

    code = supervise([SLEEPS, [sys.executable, "-c", "raise SystemExit(3)"]])

    assert code == 3
    # The sleeper was stopped rather than waited for.
    assert time.monotonic() - started < 30


def test_a_clean_exit_is_a_clean_exit() -> None:
    assert supervise([[sys.executable, "-c", "pass"], SLEEPS]) == 0


class _Recorder:
    """Stands in for running each step and supervising the processes, noting what was run."""

    def __init__(self, *, code: int = 0) -> None:
        self.ran: list[tuple[str, ...]] = []
        self._code = code

    def run(self, *args: str) -> int:
        self.ran.append(args)
        return self._code

    def supervise(self, _commands: object) -> int:
        self.ran.append(("supervise",))
        return 0


MIGRATE = ("alembic", "upgrade", "head")
GEO = ("app.manage", "geo", "load")
SAMPLES = ("app.manage", "catalog", "samples")


def test_the_database_and_geo_data_come_first_and_samples_only_when_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(all_in_one, "_run", recorder.run)
    monkeypatch.setattr(all_in_one, "supervise", recorder.supervise)

    monkeypatch.setenv("SEED_SAMPLES", "true")
    assert all_in_one.main() == 0
    monkeypatch.delenv("SEED_SAMPLES")
    assert all_in_one.main() == 0

    serve = ("supervise",)
    assert recorder.ran == [MIGRATE, GEO, SAMPLES, serve, MIGRATE, GEO, serve]


def test_a_failed_migration_starts_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder(code=4)
    monkeypatch.setattr(all_in_one, "_run", recorder.run)
    monkeypatch.setattr(all_in_one, "supervise", recorder.supervise)

    assert all_in_one.main() == 4
    assert recorder.ran == [MIGRATE]
