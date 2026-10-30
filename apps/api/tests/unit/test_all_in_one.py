"""One container running the API and its worker (ADR 0047): when one stops, so does the other,
and the exit code is the one that stopped first."""

import sys
import time

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
