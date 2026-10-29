"""The visits module's errors (ARCHITECTURE §15)."""

from typing import TYPE_CHECKING

from app.core.errors import AppError

if TYPE_CHECKING:
    from collections.abc import Sequence


class VisitInvalidError(AppError):
    """Times or a request that don't work: the detail names every problem."""

    status = 422
    code = "VISIT_INVALID"
    title = "That visit doesn't work"

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


class VisitLimitReachedError(AppError):
    status = 409
    code = "VISIT_LIMIT_REACHED"
    title = "Too many visits open"


class VisitExistsError(AppError):
    """The student has a visit open to that PG already."""

    status = 409
    code = "VISIT_EXISTS"
    title = "You've asked to visit this PG already"


class CheckInRequiredError(AppError):
    """An outcome needs the agent's check-in first: it's what shows they were there."""

    status = 409
    code = "CHECK_IN_REQUIRED"
    title = "Check in at the building first"


class CheckInTooEarlyError(AppError):
    status = 409
    code = "CHECK_IN_TOO_EARLY"
    title = "It's too early to check in for this visit"
