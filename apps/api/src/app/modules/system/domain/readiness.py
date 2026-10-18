"""Readiness: an instance is ready only when every dependency check passed."""

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

CheckState = Literal["ok", "unavailable"]


def overall_state(checks: Mapping[str, CheckState]) -> CheckState:
    if checks and all(state == "ok" for state in checks.values()):
        return "ok"
    return "unavailable"
