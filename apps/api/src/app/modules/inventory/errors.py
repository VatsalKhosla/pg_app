"""The inventory module's errors (ARCHITECTURE §15)."""

from typing import TYPE_CHECKING

from app.core.errors import AppError

if TYPE_CHECKING:
    from collections.abc import Sequence


class BlockInvalidError(AppError):
    """A block that can't be placed as asked: the detail names every problem."""

    status = 422
    code = "BLOCK_INVALID"
    title = "That block doesn't work"

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


class BedUnavailableError(AppError):
    """Something already holds the bed on one of the days asked for; the detail says what."""

    status = 409
    code = "BED_UNAVAILABLE"
    title = "That bed is taken then"
