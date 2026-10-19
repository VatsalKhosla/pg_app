"""Request and response bodies of the identity routes (camelCase JSON, unknown fields rejected)."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints
from pydantic_core import PydanticCustomError

from app.core.actor import Role
from app.core.human_check import MAX_TOKEN_LENGTH
from app.core.schemas import ApiModel
from app.modules.identity.domain.consent import ConsentPurpose
from app.modules.identity.domain.otp import CODE_DIGITS, HUMAN_CHECK_ACTION
from app.modules.identity.domain.phones import normalize_indian_mobile
from app.modules.identity.domain.totp import DIGITS as TOTP_DIGITS


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
    # The privacy notice changed since the account's consent: show the new one and ask again
    # (POST /v1/me/consents).
    consent_required: bool


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


class ConsentInput(ApiModel):
    """What the person agreed to: the privacy notice version they were shown (GET
    /v1/privacy-notice), and the purposes they chose themselves (never pre-ticked)."""

    notice_version: str = Field(min_length=1, max_length=64)
    purposes: list[ConsentPurpose] = Field(max_length=len(ConsentPurpose))


class OtpVerify(ApiModel):
    challenge_id: uuid.UUID
    code: str = Field(pattern=rf"^[0-9]{{{CODE_DIGITS}}}$")
    # Needed to create an account (a first sign-in answers CONSENT_REQUIRED without it, and the
    # code stays usable); optional for an account that already exists.
    consent: ConsentInput | None = None


class SignInResult(ApiModel):
    """Signed in, with the session cookie set. Use ``csrfToken`` (also a cookie) from now on."""

    user: Me
    csrf_token: str
    # The account was created by this sign-in.
    new_user: bool


class StaffTotpSignIn(ApiModel):
    """A code from the authenticator app, sent after signing in by phone."""

    code: str = Field(pattern=rf"^[0-9]{{{TOTP_DIGITS}}}$")


class StaffSignInResult(ApiModel):
    """Signed in to staff tools: a staff session, ending 12 hours after sign-in."""

    user: Me
    # Also set as the CSRF cookie; bound to the new session.
    csrf_token: str


class StaffMember(ApiModel):
    id: uuid.UUID
    name: str | None
    phone: str
    email: str | None
    roles: list[Role]
    # The address of the Google account linked at their first Google sign-in, if any.
    google_account: str | None
    # Whether they can sign in with a phone code and an authenticator app.
    authenticator: bool


class StaffPage(ApiModel):
    items: list[StaffMember]
    # Pass as ``cursor`` for the next page; null on the last one.
    next_cursor: uuid.UUID | None


class NoticePurpose(ApiModel):
    purpose: ConsentPurpose
    # The account needs it; the others are the person's choice, and off unless they choose them.
    required: bool


class PrivacyNoticeInfo(ApiModel):
    """The current privacy notice: its version, which consent must name, and its purposes. The
    notice's text is the web app's."""

    version: str
    purposes: list[NoticePurpose]


class ConsentRecord(ApiModel):
    purpose: ConsentPurpose
    notice_version: str
    granted_at: datetime
    withdrawn_at: datetime | None


class ConsentList(ApiModel):
    """Every consent the account has given, oldest first, withdrawn ones included."""

    consents: list[ConsentRecord]
