"""Idempotency keys for POSTs that create bookings, payments, refunds or invoices (§15).

The client sends ``Idempotency-Key`` with such a request and the same key on every retry. The
service claims the key inside its own transaction (``begin``) and stores the response in that same
transaction (``complete``) before committing. So:

- a retry after success gets the stored response back, with ``Idempotent-Replayed: true``, and
  the work runs exactly once, even when retries race: a concurrent duplicate waits on the key's
  row until the first transaction ends, then replays its response;
- if the work fails and rolls back, the key is released with it, so a retry runs again;
- the same key with a different request (method, route or body) is refused with 422.

Keys are scoped to whoever sent them (the signed-in user, from step 1.1) and kept for 24 hours.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

from fastapi import Request  # noqa: TC002 - FastAPI reads dependency signatures at runtime
from fastapi.responses import JSONResponse
from sqlalchemy import DateTime, Index, Integer, Text, UniqueConstraint, delete, select, update
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model
from app.core.errors import AppError

if TYPE_CHECKING:
    from pydantic import JsonValue
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.clock import Clock
    from app.core.outbox import JobContext, JobPayload

IDEMPOTENCY_KEY_HEADER: Final = "Idempotency-Key"
REPLAYED_HEADER: Final = "Idempotent-Replayed"
KEY_TTL: Final = timedelta(hours=24)
IDEMPOTENCY_CLEANUP: Final = "idempotency.cleanup"

_WELL_FORMED_KEY: Final = re.compile(r"[A-Za-z0-9._:-]{8,255}")
# The header as a route's OpenAPI operation describes it (``openapi_extra``), so the typed client
# asks for it. The route checks it itself, to answer the codes above.
OPENAPI_HEADER: Final = {
    "parameters": [
        {
            "name": IDEMPOTENCY_KEY_HEADER,
            "in": "header",
            "required": True,
            "description": "The same key on every retry of a request: a retry gets the first"
            " answer back.",
            "schema": {"type": "string", "pattern": f"^{_WELL_FORMED_KEY.pattern}$"},
        }
    ]
}


class IdempotencyKeyRequiredError(AppError):
    status = 400
    code = "IDEMPOTENCY_KEY_REQUIRED"
    title = "Idempotency-Key header required"


class IdempotencyKeyInvalidError(AppError):
    status = 400
    code = "IDEMPOTENCY_KEY_INVALID"
    title = "Idempotency-Key header is malformed"


class IdempotencyKeyReusedError(AppError):
    status = 422
    code = "IDEMPOTENCY_KEY_REUSED"
    title = "Idempotency key already used for a different request"


class IdempotencyKeyConflictError(AppError):
    status = 409
    code = "IDEMPOTENCY_KEY_CONFLICT"
    title = "Idempotency key is in an unexpected state"


class IdempotencyRecord(Model):
    __tablename__ = "idempotency_keys"

    scope: Mapped[str] = mapped_column(Text)
    key: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(Text)
    route: Mapped[str] = mapped_column(Text)
    request_sha256: Mapped[str] = mapped_column(Text)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[Any | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("scope", "key"),
        Index("ix_idempotency_keys_expires_at", "expires_at"),
    )


@dataclass(frozen=True, slots=True)
class IdempotentRequest:
    scope: str  # who sent it, e.g. "user:42"
    key: str
    method: str
    route: str  # the route template, e.g. "/v1/bookings"
    fingerprint: str  # SHA-256 of method, route and body


@dataclass(frozen=True, slots=True)
class StoredResponse:
    status_code: int
    body: JsonValue


def fingerprint(method: str, route: str, body: bytes) -> str:
    digest = hashlib.sha256()
    for part in (method.encode(), route.encode(), body):
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    return digest.hexdigest()


def idempotency_key(request: Request) -> str:
    """The validated ``Idempotency-Key`` header (a FastAPI dependency)."""
    key = request.headers.get(IDEMPOTENCY_KEY_HEADER)
    if key is None:
        raise IdempotencyKeyRequiredError("Send an Idempotency-Key header, reused on every retry.")
    if not _WELL_FORMED_KEY.fullmatch(key):
        raise IdempotencyKeyInvalidError("Use 8 to 255 characters: letters, digits, . _ : or -.")
    return key


async def idempotent_request(request: Request, *, scope: str) -> IdempotentRequest:
    key = idempotency_key(request)
    route = str(getattr(request.scope.get("route"), "path", request.url.path))
    return IdempotentRequest(
        scope=scope,
        key=key,
        method=request.method,
        route=route,
        fingerprint=fingerprint(request.method, route, await request.body()),
    )


async def begin(
    session: AsyncSession, request: IdempotentRequest, *, clock: Clock
) -> StoredResponse | None:
    """Claim the key in the caller's transaction.

    Returns the stored response when this is a retry, or None when the work should run now; the
    caller then calls ``complete`` before committing.
    """
    now = clock.now()
    same_key = (IdempotencyRecord.scope == request.scope, IdempotencyRecord.key == request.key)
    await session.execute(
        delete(IdempotencyRecord).where(*same_key, IdempotencyRecord.expires_at <= now)
    )
    claimed = await session.execute(
        insert(IdempotencyRecord)
        .values(
            scope=request.scope,
            key=request.key,
            method=request.method,
            route=request.route,
            request_sha256=request.fingerprint,
            expires_at=now + KEY_TTL,
        )
        .on_conflict_do_nothing(index_elements=[IdempotencyRecord.scope, IdempotencyRecord.key])
        .returning(IdempotencyRecord.id)
    )
    if claimed.scalar_one_or_none() is not None:
        return None
    existing = (
        await session.execute(
            select(
                IdempotencyRecord.request_sha256,
                IdempotencyRecord.response_status,
                IdempotencyRecord.response_body,
            ).where(*same_key)
        )
    ).one()
    if existing.request_sha256 != request.fingerprint:
        raise IdempotencyKeyReusedError("Use a new Idempotency-Key for a different request.")
    if existing.response_status is None:
        raise IdempotencyKeyConflictError
    return StoredResponse(status_code=existing.response_status, body=existing.response_body)


async def complete(
    session: AsyncSession, request: IdempotentRequest, response: StoredResponse
) -> None:
    """Store the response for retries, in the same transaction as the work."""
    await session.execute(
        update(IdempotencyRecord)
        .where(IdempotencyRecord.scope == request.scope, IdempotencyRecord.key == request.key)
        .values(response_status=response.status_code, response_body=response.body)
    )


def replay(stored: StoredResponse) -> JSONResponse:
    return JSONResponse(
        stored.body, status_code=stored.status_code, headers={REPLAYED_HEADER: "true"}
    )


async def delete_expired_keys(context: JobContext, _payload: JobPayload) -> None:
    """Periodic cleanup of keys past their 24 hours."""
    await context.session.execute(
        delete(IdempotencyRecord).where(IdempotencyRecord.expires_at <= context.clock.now())
    )
