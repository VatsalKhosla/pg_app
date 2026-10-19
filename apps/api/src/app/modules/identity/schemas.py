"""Request and response bodies of the identity routes (camelCase JSON, unknown fields rejected)."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints
from pydantic_core import PydanticCustomError

from app.core.actor import Role
from app.core.human_check import MAX_TOKEN_LENGTH
from app.core.schemas import ApiModel
from app.modules.identity.domain.otp import CODE_DIGITS, HUMAN_CHECK_ACTION
from app.modules.identity.domain.phones import normalize_indian_mobile


def _indian_mobile(value: str) -> str:
    phone = normalize_indian_mobile(value)
    if phone is None:
        raise PydanticCustomError("phone_invalid", "Enter a 10-digit Indian mobile number.")
    return phone


IndianMobile = Annotated[str, StringConstraints(max_length=32), AfterValidator(_indian_mobile)]


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


class OtpRequest(ApiModel):
    """Ask for a sign-in code by SMS."""

    # Any common way of writing an Indian mobile number; it is stored as +91XXXXXXXXXX.
    phone: IndianMobile
    human_check_token: str = Field(
        min_length=1,
        max_length=MAX_TOKEN_LENGTH,
        description=(
            "The token of the sign-in form's Cloudflare Turnstile widget, whose action is "
            f"`{HUMAN_CHECK_ACTION}`."
        ),
    )


class OtpChallengeIssued(ApiModel):
    """A code is on its way. Send it back with ``challengeId`` to sign in."""

    challenge_id: uuid.UUID
    expires_at: datetime
    # When another code may be asked for.
    resend_after: datetime


class OtpVerify(ApiModel):
    challenge_id: uuid.UUID
    code: str = Field(pattern=rf"^[0-9]{{{CODE_DIGITS}}}$")


class SignInResult(ApiModel):
    """Signed in, with the session cookie set. Use ``csrfToken`` (also a cookie) from now on."""

    user: Me
    csrf_token: str
    # The account was created by this sign-in.
    new_user: bool
