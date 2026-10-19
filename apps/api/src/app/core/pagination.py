"""Cursor pagination for list endpoints (ARCHITECTURE §15): ``cursor`` and ``limit`` (at most 50).

Lists are ordered by public id. Public ids are UUIDv7, which sort by creation time, so a cursor is
the last id of the previous page: it stays valid while rows are added, and reveals nothing the page
didn't already show. A repository fetches ``limit + 1`` rows; the extra one says whether there is
a next page.
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Annotated, Final

from fastapi import Depends, Query

MAX_PAGE_SIZE: Final = 50
DEFAULT_PAGE_SIZE: Final = 20


@dataclass(frozen=True)
class PageRequest:
    """The rows after ``after`` (from the start when None), at most ``limit`` of them."""

    after: uuid.UUID | None
    limit: int


def page_request(
    cursor: Annotated[
        uuid.UUID | None, Query(description="The previous page's nextCursor; omit it to start.")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> PageRequest:
    return PageRequest(after=cursor, limit=limit)


PageParams = Annotated[PageRequest, Depends(page_request)]


def split_page[T](
    rows: Sequence[T], request: PageRequest, *, cursor_of: Callable[[T], uuid.UUID]
) -> tuple[list[T], uuid.UUID | None]:
    """The page among ``limit + 1`` fetched rows, and the next page's cursor (None at the end)."""
    items = list(rows[: request.limit])
    next_cursor = cursor_of(items[-1]) if len(rows) > request.limit else None
    return items, next_cursor
