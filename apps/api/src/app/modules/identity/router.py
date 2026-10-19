"""Sign-in, session and account routes (ARCHITECTURE §12 and §15)."""

import uuid
from datetime import timedelta
from typing import Annotated, Final
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.core.actor import STAFF_ROLES, Role
from app.core.clock import Clock, ClockDep
from app.core.cookies import CSRF_COOKIE, SESSION_COOKIE, STAFF_LOGIN_COOKIE, CookiePolicy
from app.core.csrf import CSRF_COOKIE_MAX_AGE, issue_csrf_token
from app.core.current_actor import CurrentActor
from app.core.db import DbSession
from app.core.errors import AppError, ForbiddenError, NotFoundError, UnauthenticatedError
from app.core.pagination import PageParams
from app.core.ratelimit import RateLimit, client_ip, rate_limited
from app.modules.identity.auth import (
    ConsentServiceDep,
    CookiesDep,
    NoticeVersion,
    OtpServiceDep,
    StaffSignInDep,
)
from app.modules.identity.domain.consent import ConsentPurpose
from app.modules.identity.domain.sessions import SessionKind
from app.modules.identity.models import Consent
from app.modules.identity.policies import can_list_staff
from app.modules.identity.schemas import (
    ConsentInput,
    ConsentList,
    ConsentRecord,
    CsrfToken,
    Me,
    NoticePurpose,
    OtpChallengeIssued,
    OtpRequest,
    OtpVerify,
    PrivacyNoticeInfo,
    SessionInfo,
    SessionList,
    SignInResult,
    StaffMember,
    StaffPage,
    StaffSignInResult,
    StaffTotpSignIn,
)
from app.modules.identity.service import (
    ConsentGiven,
    Profile,
    SessionService,
    StaffDirectory,
    UserService,
    privacy_notice,
)
from app.modules.identity.service.staff import LOGIN_TTL

router = APIRouter(prefix="/v1", tags=["identity"])

# Google sends staff back here; register API_URL + this path as the OAuth client's redirect URI.
GOOGLE_CALLBACK_PATH: Final = "/v1/auth/staff/google/callback"
# The web app's staff tools, and its staff sign-in page, which a failed sign-in comes back to with
# the error's code (?error=STAFF_ACCOUNT_NOT_ALLOWED).
STAFF_HOME_PATH: Final = "/staff"
STAFF_SIGN_IN_PATH: Final = "/staff/sign-in"

# Per-IP backstops behind Turnstile and the per-phone limits. Generous, because many students share
# an address (college Wi-Fi, mobile carriers' NAT); refused while Redis is down.
OTP_REQUESTS_PER_IP: Final = RateLimit(
    "otp-requests-per-ip", limit=60, window=timedelta(hours=1), fail_open=False
)
OTP_CHECKS_PER_IP: Final = RateLimit(
    "otp-checks-per-ip", limit=120, window=timedelta(minutes=15), fail_open=False
)
# Staff sign-in: a Google sign-in counts twice (leaving and coming back); the authenticator code
# has its own, tighter limit per staff member as well.
STAFF_SIGN_INS_PER_IP: Final = RateLimit(
    "staff-sign-ins-per-ip", limit=60, window=timedelta(hours=1), fail_open=False
)
STAFF_TOTP_CHECKS_PER_IP: Final = RateLimit(
    "staff-totp-checks-per-ip", limit=60, window=timedelta(minutes=15), fail_open=False
)


def _me(profile: Profile, roles: frozenset[Role]) -> Me:
    return Me(
        id=profile.public_id,
        phone=profile.phone_e164,
        email=profile.email,
        name=profile.name,
        roles=sorted(roles),
        consent_required=profile.consent_required,
    )


def _consent(given: ConsentInput) -> ConsentGiven:
    return ConsentGiven(notice_version=given.notice_version, purposes=frozenset(given.purposes))


def _consent_list(consents: list[Consent]) -> ConsentList:
    return ConsentList(
        consents=[
            ConsentRecord(
                purpose=ConsentPurpose(consent.purpose),
                notice_version=consent.notice_version,
                granted_at=consent.granted_at,
                withdrawn_at=consent.withdrawn_at,
            )
            for consent in consents
        ]
    )


def _clear_session_cookies(response: Response, cookies: CookiesDep) -> None:
    cookies.clear(response, SESSION_COOKIE, http_only=True)
    cookies.clear(response, CSRF_COOKIE, http_only=False)


async def _start_session(
    request: Request,
    response: Response,
    *,
    user_id: int,
    kind: SessionKind,
    db: DbSession,
    clock: Clock,
    cookies: CookiePolicy,
) -> str:
    """Sign ``user_id`` in on this browser, ending its previous session, and set the session and
    CSRF cookies on ``response``. Returns the CSRF token, bound to the new session."""
    issued = await SessionService(db, clock).start(
        user_id,
        kind=kind,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        replacing=request.cookies.get(SESSION_COOKIE),
    )
    lifetime = int((issued.expires_at - clock.now()).total_seconds())
    cookies.set(response, SESSION_COOKIE, issued.token, max_age=lifetime, http_only=True)
    csrf = issue_csrf_token(request.app.state.secret_key, issued.token)
    cookies.set(response, CSRF_COOKIE, csrf, max_age=CSRF_COOKIE_MAX_AGE, http_only=False)
    return csrf


async def _profile(db: DbSession, user_id: int, notice_version: str) -> Profile:
    profile = await UserService(db).profile(user_id, notice_version=notice_version)
    if profile is None:  # pragma: no cover - the user was just found or created
        raise UnauthenticatedError
    return profile


@router.get("/auth/csrf", summary="A CSRF token for this browser")
async def csrf_token(request: Request, response: Response, cookies: CookiesDep) -> CsrfToken:
    """Sets the CSRF cookie and returns the same value, bound to the browser's session cookie if
    it has one. Fetch a new one after signing in or out."""
    secret: bytes = request.app.state.secret_key
    token = issue_csrf_token(secret, request.cookies.get(SESSION_COOKIE))
    cookies.set(response, CSRF_COOKIE, token, max_age=CSRF_COOKIE_MAX_AGE, http_only=False)
    return CsrfToken(csrf_token=token)


@router.post(
    "/auth/otp/request",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send a sign-in code by SMS",
    dependencies=[Depends(rate_limited(OTP_REQUESTS_PER_IP))],
)
async def request_otp(body: OtpRequest, request: Request, otp: OtpServiceDep) -> OtpChallengeIssued:
    """Sends a six-digit code to the phone, replacing any earlier code. The answer is the same
    whether or not the number has an account."""
    issued = await otp.request(
        body.phone,
        human_check_token=body.human_check_token,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return OtpChallengeIssued(
        challenge_id=issued.public_id,
        expires_at=issued.expires_at,
        resend_after=issued.resend_after,
    )


@router.post(
    "/auth/otp/verify",
    summary="Sign in with the code",
    dependencies=[Depends(rate_limited(OTP_CHECKS_PER_IP))],
)
async def verify_otp(
    body: OtpVerify,
    *,
    request: Request,
    response: Response,
    db: DbSession,
    clock: ClockDep,
    cookies: CookiesDep,
    otp: OtpServiceDep,
    notice_version: NoticeVersion,
) -> SignInResult:
    """Checks the code and signs the phone's owner in, creating the account on first sign-in,
    which needs consent to the privacy notice. Sets the session and CSRF cookies; any earlier
    session in this browser ends."""
    signed_in = await otp.verify(
        body.challenge_id,
        body.code,
        consent=None if body.consent is None else _consent(body.consent),
    )
    csrf = await _start_session(
        request,
        response,
        user_id=signed_in.user_id,
        kind=SessionKind.USER,
        db=db,
        clock=clock,
        cookies=cookies,
    )
    profile = await _profile(db, signed_in.user_id, notice_version)
    return SignInResult(
        user=_me(profile, profile.roles - STAFF_ROLES),
        csrf_token=csrf,
        new_user=signed_in.new_user,
    )


def _staff_sign_in_failed(
    request: Request, cookies: CookiePolicy, failure: AppError
) -> RedirectResponse:
    """Back to the web app's staff sign-in page, with the reason's code."""
    query = urlencode({"error": failure.code})
    response = RedirectResponse(
        f"{request.app.state.site_url}{STAFF_SIGN_IN_PATH}?{query}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    cookies.clear(response, STAFF_LOGIN_COOKIE, http_only=True, host_only=True)
    return response


@router.get(
    "/auth/staff/google",
    status_code=status.HTTP_303_SEE_OTHER,
    response_class=RedirectResponse,
    summary="Sign in to staff tools with Google",
    dependencies=[Depends(rate_limited(STAFF_SIGN_INS_PER_IP))],
)
async def start_google_sign_in(
    request: Request, cookies: CookiesDep, staff: StaffSignInDep
) -> RedirectResponse:
    """Open this in the browser (not with fetch): it goes on to Google, which sends the browser
    back to the callback. A failure lands on the web app's staff sign-in page with an error
    code."""
    try:
        login = staff.start_google()
    except AppError as failure:
        return _staff_sign_in_failed(request, cookies, failure)
    response = RedirectResponse(login.authorization_url, status_code=status.HTTP_303_SEE_OTHER)
    cookies.set(
        response,
        STAFF_LOGIN_COOKIE,
        login.cookie,
        max_age=int(LOGIN_TTL.total_seconds()),
        http_only=True,
        host_only=True,
    )
    return response


@router.get(
    GOOGLE_CALLBACK_PATH.removeprefix("/v1"),
    status_code=status.HTTP_303_SEE_OTHER,
    response_class=RedirectResponse,
    summary="Where Google sends staff back to",
    dependencies=[Depends(rate_limited(STAFF_SIGN_INS_PER_IP))],
)
async def finish_google_sign_in(
    request: Request,
    *,
    code: Annotated[str | None, Query(max_length=2048)] = None,
    state: Annotated[str | None, Query(max_length=256)] = None,
    error: Annotated[str | None, Query(max_length=256)] = None,
    db: DbSession,
    clock: ClockDep,
    cookies: CookiesDep,
    staff: StaffSignInDep,
) -> RedirectResponse:
    """Signs the staff member in (a 12-hour staff session; any earlier session in this browser
    ends) and sends them to the web app's staff tools, or back to its staff sign-in page with an
    error code: STAFF_ACCOUNT_NOT_ALLOWED, STAFF_SIGN_IN_EXPIRED, STAFF_SIGN_IN_CANCELLED or
    SERVICE_UNAVAILABLE."""
    try:
        user_id = await staff.finish_google(
            login_cookie=request.cookies.get(STAFF_LOGIN_COOKIE),
            state=state,
            code=code,
            error=error,
        )
    except AppError as failure:
        return _staff_sign_in_failed(request, cookies, failure)
    response = RedirectResponse(
        f"{request.app.state.site_url}{STAFF_HOME_PATH}", status_code=status.HTTP_303_SEE_OTHER
    )
    await _start_session(
        request,
        response,
        user_id=user_id,
        kind=SessionKind.STAFF,
        db=db,
        clock=clock,
        cookies=cookies,
    )
    cookies.clear(response, STAFF_LOGIN_COOKIE, http_only=True, host_only=True)
    return response


@router.post(
    "/auth/staff/totp",
    summary="Sign in to staff tools with an authenticator code",
    dependencies=[Depends(rate_limited(STAFF_TOTP_CHECKS_PER_IP))],
)
async def staff_totp_sign_in(
    body: StaffTotpSignIn,
    *,
    actor: CurrentActor,
    request: Request,
    response: Response,
    db: DbSession,
    clock: ClockDep,
    cookies: CookiesDep,
    staff: StaffSignInDep,
    notice_version: NoticeVersion,
) -> StaffSignInResult:
    """For staff without Google sign-in: after signing in by phone, a code from the authenticator
    app set up for them gives a staff session (12 hours), which replaces the phone session."""
    user_id = await staff.verify_totp(actor, body.code)
    csrf = await _start_session(
        request,
        response,
        user_id=user_id,
        kind=SessionKind.STAFF,
        db=db,
        clock=clock,
        cookies=cookies,
    )
    profile = await _profile(db, user_id, notice_version)
    return StaffSignInResult(user=_me(profile, profile.roles), csrf_token=csrf)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Sign out here")
async def logout(
    request: Request, response: Response, db: DbSession, clock: ClockDep, cookies: CookiesDep
) -> None:
    """Ends this browser's session, if it has one, and clears the cookies. Safe to repeat."""
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await SessionService(db, clock).end(token)
    _clear_session_cookies(response, cookies)


@router.post(
    "/auth/logout-everywhere",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign out on every device",
)
async def logout_everywhere(
    actor: CurrentActor, response: Response, db: DbSession, clock: ClockDep, cookies: CookiesDep
) -> None:
    await SessionService(db, clock).end_everywhere(actor)
    _clear_session_cookies(response, cookies)


@router.get("/me", summary="The signed-in user")
async def me(actor: CurrentActor, db: DbSession, notice_version: NoticeVersion) -> Me:
    """The account, with the roles this session carries (a phone sign-in never carries staff
    roles), and whether its consent must be asked for again."""
    profile = await UserService(db).profile(actor.user_id, notice_version=notice_version)
    if profile is None:
        raise UnauthenticatedError
    return _me(profile, actor.roles)


@router.get("/privacy-notice", summary="The current privacy notice's version and purposes")
async def current_privacy_notice(notice_version: NoticeVersion) -> PrivacyNoticeInfo:
    """What consent must name. The notice's text is the web app's, under the same version."""
    notice = privacy_notice(notice_version)
    return PrivacyNoticeInfo(
        version=notice.version,
        purposes=[
            NoticePurpose(purpose=purpose, required=required)
            for purpose, required in notice.purposes
        ],
    )


@router.get("/me/consents", summary="What the account has agreed to")
async def my_consents(actor: CurrentActor, consents: ConsentServiceDep) -> ConsentList:
    return _consent_list(await consents.history(actor.user_id))


@router.post("/me/consents", summary="Agree to the current notice, or to an optional purpose")
async def give_consent(
    body: ConsentInput, actor: CurrentActor, consents: ConsentServiceDep
) -> ConsentList:
    """Records consent to the purposes given, under the current notice (409
    PRIVACY_NOTICE_CHANGED for any other version). Purposes already agreed to stay as they are."""
    return _consent_list(await consents.grant(actor.user_id, _consent(body)))


@router.delete(
    "/me/consents/{purpose}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Withdraw consent to an optional purpose",
)
async def withdraw_consent(
    purpose: ConsentPurpose, actor: CurrentActor, consents: ConsentServiceDep
) -> None:
    """Safe to repeat. The account's own purposes can't be withdrawn while it exists (409
    CONSENT_NEEDED_FOR_ACCOUNT): ask for its deletion instead."""
    await consents.withdraw(actor.user_id, purpose)


@router.get("/me/sessions", summary="Where this account is signed in")
async def my_sessions(actor: CurrentActor, db: DbSession, clock: ClockDep) -> SessionList:
    sessions = await SessionService(db, clock).live_sessions(actor)
    return SessionList(
        sessions=[
            SessionInfo(
                id=session.public_id,
                current=session.id == actor.session_id,
                started_at=session.started_at,
                last_seen_at=session.last_seen_at,
                expires_at=session.expires_at,
                user_agent=session.user_agent,
            )
            for session in sessions
        ]
    )


@router.delete(
    "/me/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign out one device",
)
async def end_session(
    session_id: uuid.UUID,
    *,
    actor: CurrentActor,
    response: Response,
    db: DbSession,
    clock: ClockDep,
    cookies: CookiesDep,
) -> None:
    """Another user's session answers 404, like one that doesn't exist."""
    if not await SessionService(db, clock).end_one(actor, session_id):
        raise NotFoundError
    if session_id == actor.session_public_id:
        _clear_session_cookies(response, cookies)


@router.get("/admin/staff", summary="Staff accounts")
async def list_staff(actor: CurrentActor, page: PageParams, db: DbSession) -> StaffPage:
    """Admins only (in a staff session): everyone with a staff role, and how each signs in."""
    if not can_list_staff(actor):
        raise ForbiddenError
    records, next_cursor = await StaffDirectory(db).page(page)
    return StaffPage(
        items=[
            StaffMember(
                id=record.user.public_id,
                name=record.user.name,
                phone=record.user.phone_e164,
                email=record.user.email,
                roles=sorted(record.roles),
                google_account=record.google_email,
                authenticator=record.authenticator,
            )
            for record in records
        ],
        next_cursor=next_cursor,
    )
