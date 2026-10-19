"""Sign-in, session and account routes (ARCHITECTURE §12 and §15)."""

import uuid
from datetime import timedelta
from typing import Final

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.actor import STAFF_ROLES, Role
from app.core.clock import ClockDep
from app.core.cookies import CSRF_COOKIE, SESSION_COOKIE
from app.core.csrf import CSRF_COOKIE_MAX_AGE, issue_csrf_token
from app.core.db import DbSession
from app.core.errors import NotFoundError, UnauthenticatedError
from app.core.ratelimit import RateLimit, client_ip, rate_limited
from app.modules.identity.auth import CookiesDep, CurrentActor, OtpServiceDep
from app.modules.identity.domain.sessions import SessionKind
from app.modules.identity.schemas import (
    CsrfToken,
    Me,
    OtpChallengeIssued,
    OtpRequest,
    OtpVerify,
    SessionInfo,
    SessionList,
    SignInResult,
)
from app.modules.identity.service import Profile, SessionService, UserService

router = APIRouter(prefix="/v1", tags=["identity"])

# Per-IP backstops behind Turnstile and the per-phone limits. Generous, because many students share
# an address (college Wi-Fi, mobile carriers' NAT); refused while Redis is down.
OTP_REQUESTS_PER_IP: Final = RateLimit(
    "otp-requests-per-ip", limit=60, window=timedelta(hours=1), fail_open=False
)
OTP_CHECKS_PER_IP: Final = RateLimit(
    "otp-checks-per-ip", limit=120, window=timedelta(minutes=15), fail_open=False
)


def _me(profile: Profile, roles: frozenset[Role]) -> Me:
    return Me(
        id=profile.public_id,
        phone=profile.phone_e164,
        email=profile.email,
        name=profile.name,
        roles=sorted(roles),
    )


def _clear_session_cookies(response: Response, cookies: CookiesDep) -> None:
    cookies.clear(response, SESSION_COOKIE, http_only=True)
    cookies.clear(response, CSRF_COOKIE, http_only=False)


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
) -> SignInResult:
    """Checks the code and signs the phone's owner in, creating the account on first sign-in.
    Sets the session and CSRF cookies; any earlier session in this browser ends."""
    signed_in = await otp.verify(body.challenge_id, body.code)
    issued = await SessionService(db, clock).start(
        signed_in.user_id,
        kind=SessionKind.USER,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        replacing=request.cookies.get(SESSION_COOKIE),
    )
    lifetime = int((issued.expires_at - clock.now()).total_seconds())
    cookies.set(response, SESSION_COOKIE, issued.token, max_age=lifetime, http_only=True)
    csrf = issue_csrf_token(request.app.state.secret_key, issued.token)
    cookies.set(response, CSRF_COOKIE, csrf, max_age=CSRF_COOKIE_MAX_AGE, http_only=False)
    profile = await UserService(db).profile(signed_in.user_id)
    if profile is None:  # pragma: no cover - the user was just found or created
        raise UnauthenticatedError
    return SignInResult(
        user=_me(profile, profile.roles - STAFF_ROLES),
        csrf_token=csrf,
        new_user=signed_in.new_user,
    )


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
async def me(actor: CurrentActor, db: DbSession) -> Me:
    """The account, with the roles this session carries (a phone sign-in never carries staff
    roles)."""
    profile = await UserService(db).profile(actor.user_id)
    if profile is None:
        raise UnauthenticatedError
    return _me(profile, actor.roles)


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
