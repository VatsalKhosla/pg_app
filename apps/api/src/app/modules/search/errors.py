"""The search module's errors (ARCHITECTURE §15)."""

from typing import TYPE_CHECKING

from app.core.errors import AppError

if TYPE_CHECKING:
    from collections.abc import Sequence


class SearchInvalidError(AppError):
    """A search that can't be answered as asked, such as two places at once or sorting by
    distance without a campus. The detail names every problem."""

    status = 422
    code = "SEARCH_INVALID"
    title = "That search doesn't work"

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)
