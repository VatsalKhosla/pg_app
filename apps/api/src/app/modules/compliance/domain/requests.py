"""Data requests under the DPDP Act (ARCHITECTURE §12): a person asks for a copy of their data,
or for their account's deletion.

An export is built by a background job and can be downloaded for EXPORT_TTL, then its file is
deleted. A deletion goes to the ops queue, where staff complete or reject it with a reason; what a
deletion erases, and what the law makes the platform keep, is the founders' decision (ADR 0018).
Each person has at most one open request of each kind.
"""

from datetime import timedelta
from enum import StrEnum
from typing import Final


class DataRequestKind(StrEnum):
    EXPORT = "export"
    DELETION = "deletion"


class DataRequestStatus(StrEnum):
    # Being worked on: the export being built, or the deletion waiting for ops.
    RECEIVED = "received"
    # Export: the file can be downloaded until it expires.
    READY = "ready"
    # Export: the file was deleted after EXPORT_TTL.
    EXPIRED = "expired"
    # Deletion: carried out by ops.
    COMPLETED = "completed"
    # Deletion: refused by ops, with the reason given to the person.
    REJECTED = "rejected"


EXPORT_TTL: Final = timedelta(days=7)

_NEXT: Final[dict[tuple[DataRequestKind, DataRequestStatus], frozenset[DataRequestStatus]]] = {
    (DataRequestKind.EXPORT, DataRequestStatus.RECEIVED): frozenset({DataRequestStatus.READY}),
    (DataRequestKind.EXPORT, DataRequestStatus.READY): frozenset({DataRequestStatus.EXPIRED}),
    (DataRequestKind.DELETION, DataRequestStatus.RECEIVED): frozenset(
        {DataRequestStatus.COMPLETED, DataRequestStatus.REJECTED}
    ),
}


def can_move(kind: DataRequestKind, current: DataRequestStatus, target: DataRequestStatus) -> bool:
    return target in _NEXT.get((kind, current), frozenset())


def is_open(status: DataRequestStatus) -> bool:
    return status is DataRequestStatus.RECEIVED
