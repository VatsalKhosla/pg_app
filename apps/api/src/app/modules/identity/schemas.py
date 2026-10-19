"""Request and response bodies of the identity routes (camelCase JSON, unknown fields rejected)."""

import uuid
from datetime import datetime

from app.core.actor import Role
from app.core.schemas import ApiModel


class CsrfToken(ApiModel):
    """Send this value in the X-CSRF-Token header of every POST, PUT, PATCH and DELETE."""

    csrf_token: str


class Me(ApiModel):
    """The signed-in user."""

    id: uuid.UUID
    phone: str
    email: str | None
    name: str | None
    roles: list[Role]


class SessionInfo(ApiModel):
    """One browser or device where the account is signed in."""

    id: uuid.UUID
    # The session this request was made with.
    current: bool
    started_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    user_agent: str | None


class SessionList(ApiModel):
    sessions: list[SessionInfo]
