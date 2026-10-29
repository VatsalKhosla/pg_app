"""Data requests (ARCHITECTURE §12, DPDP): a person asks for a copy of their data or for their
account's deletion. An export is put together by a background job from every module's part and
kept for a week; a deletion waits in the ops queue for staff to complete or reject it. Each method
is one transaction.
"""

import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Final

import structlog

from app.core import audit
from app.core.errors import InvalidTransitionError, NotFoundError
from app.core.outbox import enqueue
from app.core.pagination import split_page
from app.core.ratelimit import RateLimit, enforce
from app.modules.compliance.domain.requests import (
    EXPORT_TTL,
    DataRequestKind,
    DataRequestStatus,
    can_move,
)
from app.modules.compliance.policies import can_see_data_request
from app.modules.compliance.repository import DataExportRepository, DataRequestRepository
from app.modules.identity.service import Person, UserService

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.actor import Actor
    from app.core.clock import Clock
    from app.core.pagination import PageRequest
    from app.core.ratelimit import RateLimiter
    from app.modules.compliance.models import DataRequest

BUILD_EXPORT: Final = "compliance.build_export"
# Requests are cheap to refuse but each export is built in full: a few a day is plenty.
REQUESTS_PER_DAY: Final = RateLimit(
    "data-requests-per-user", limit=10, window=timedelta(days=1), fail_open=True
)

# One module's part of a person's export: section names to JSON-ready data.
type Exporter = Callable[[AsyncSession, int], Awaitable[dict[str, object]]]

logger = structlog.stdlib.get_logger(__name__)


@dataclass(frozen=True)
class QueuedRequest:
    request: DataRequest
    # Whose request it is; None if the account has gone.
    person: Person | None


class DataRequestService:
    def __init__(self, db: AsyncSession, clock: Clock, *, limiter: RateLimiter) -> None:
        self._db = db
        self._clock = clock
        self._limiter = limiter
        self._requests = DataRequestRepository(db)
        self._exports = DataExportRepository(db)

    async def ask(self, actor: Actor, kind: DataRequestKind) -> DataRequest:
        """A new request, or the open one of this kind if there is one already (so asking twice
        is harmless)."""
        await enforce(self._limiter, REQUESTS_PER_DAY, str(actor.user_id))
        async with self._db.begin():
            request = await self._requests.insert_open(actor.user_id, kind, now=self._clock.now())
            if request is None:
                existing = await self._requests.open_for(actor.user_id, kind)
                if existing is None:  # pragma: no cover - resolved between the two statements
                    raise InvalidTransitionError
                return existing
            if kind is DataRequestKind.EXPORT:
                await enqueue(
                    self._db,
                    BUILD_EXPORT,
                    {"data_request_id": request.id},
                    clock=self._clock,
                    dedupe_key=f"data-export:{request.public_id}",
                )
            logger.info("data request received", kind=kind, user_id=actor.user_id)
            return request

    async def mine(
        self, actor: Actor, page: PageRequest
    ) -> tuple[list[DataRequest], uuid.UUID | None]:
        async with self._db.begin():
            rows = await self._requests.page(
                user_id=actor.user_id, after=page.after, limit=page.limit
            )
        return split_page(rows, page, cursor_of=lambda row: row.public_id)

    async def export_file(self, actor: Actor, public_id: uuid.UUID) -> tuple[DataRequest, bytes]:
        """A ready export's file, for the person who asked only; anything else is 404."""
        async with self._db.begin():
            request = await self._requests.by_public_id(public_id)
            if (
                request is None
                or not can_see_data_request(actor, owner_id=request.user_id)
                or request.kind != DataRequestKind.EXPORT
                or request.status != DataRequestStatus.READY
            ):
                raise NotFoundError
            content = await self._exports.content(request.id)
            if content is None:  # pragma: no cover - a ready export always has its file
                raise NotFoundError
            return request, content

    async def queue(
        self, page: PageRequest, *, status: DataRequestStatus | None
    ) -> tuple[list[QueuedRequest], uuid.UUID | None]:
        """The requests for staff to see, oldest first, with whose they are."""
        async with self._db.begin():
            rows = await self._requests.page(status=status, after=page.after, limit=page.limit)
        requests, next_cursor = split_page(rows, page, cursor_of=lambda row: row.public_id)
        people = await UserService(self._db).people(request.user_id for request in requests)
        return [QueuedRequest(request, people.get(request.user_id)) for request in requests], (
            next_cursor
        )

    async def resolve(
        self, actor: Actor, public_id: uuid.UUID, *, outcome: DataRequestStatus, note: str
    ) -> QueuedRequest:
        """Staff complete or reject a deletion request; audited. Exports resolve themselves, and
        a request resolved already can't be again (INVALID_TRANSITION)."""
        now = self._clock.now()
        async with self._db.begin():
            request = await self._requests.by_public_id(public_id, for_update=True)
            if request is None:
                raise NotFoundError
            if not can_move(
                DataRequestKind(request.kind), DataRequestStatus(request.status), outcome
            ):
                raise InvalidTransitionError
            request.status = outcome
            request.resolved_at = now
            request.resolved_by = actor.user_id
            request.note = note
            await audit.record(
                self._db,
                clock=self._clock,
                actor=audit.Actor("staff", actor.user_id),
                action="data_request.resolved",
                entity_type="data_request",
                entity_id=str(request.public_id),
                details={"kind": request.kind, "outcome": outcome},
            )
        people = await UserService(self._db).people([request.user_id])
        return QueuedRequest(request, people.get(request.user_id))


async def build_export(
    session: AsyncSession, clock: Clock, data_request_id: int, exporters: Sequence[Exporter]
) -> None:
    """The job behind an export: every module's part of the person's data, as one JSON file.
    Runs in the job's transaction; a request already built (a repeated job) is left alone."""
    request = await DataRequestRepository(session).by_id(data_request_id, for_update=True)
    if request is None or request.status != DataRequestStatus.RECEIVED:
        return
    now = clock.now()
    data: dict[str, object] = {"exportedAt": now.isoformat()}
    for exporter in exporters:
        data |= await exporter(session, request.user_id)
    content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode()
    await DataExportRepository(session).put(request.id, content)
    request.status = DataRequestStatus.READY
    request.resolved_at = now
    request.expires_at = now + EXPORT_TTL
    logger.info("data export ready", user_id=request.user_id, size=len(content))


async def data_requests_part(session: AsyncSession, user_id: int) -> dict[str, object]:
    """The compliance module's part of an export: the person's data requests."""
    return {
        "dataRequests": [
            {
                "kind": request.kind,
                "status": request.status,
                "requestedAt": request.requested_at.isoformat(),
                "resolvedAt": None
                if request.resolved_at is None
                else request.resolved_at.isoformat(),
                "note": request.note,
            }
            for request in await DataRequestRepository(session).for_user(user_id)
        ]
    }


async def expire_exports(session: AsyncSession, clock: Clock) -> int:
    """Retention: delete export files past their expiry, and mark their requests expired."""
    requests = await DataRequestRepository(session).exports_past(clock.now())
    for request in requests:
        request.status = DataRequestStatus.EXPIRED
    await DataExportRepository(session).delete_for(request.id for request in requests)
    return len(requests)
