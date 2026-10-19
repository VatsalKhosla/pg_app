"""Session and account routes (ARCHITECTURE §12 and §15). Sign-in itself arrives with OTP (1.2)."""

import uuid

from fastapi import APIRouter, Request, Response, status

from app.core.clock import ClockDep
from app.core.cookies import CSRF_COOKIE, SESSION_COOKIE
from app.core.csrf import CSRF_COOKIE_MAX_AGE, issue_csrf_token
from app.core.db import DbSession
from app.core.errors import NotFoundError, UnauthenticatedError
from app.modules.identity.auth import CookiesDep, CurrentActor
from app.modules.identity.schemas import CsrfToken, Me, SessionInfo, SessionList
from app.modules.identity.service import SessionService, UserService

router = APIRouter(prefix="/v1", tags=["identity"])


def _clear_session_cookies(response: Response, cookies: CookiesDep) -> None:
    cookies.clear(response, SESSION_COOKIE, http_only=True)
    cookies.clear(response, CSRF_COOKIE, http_only=False)


@router.get("/auth/csrf", summary="A CSRF token for this browser")
async def csrf_token(request: Request, response: Response, cookies: CookiesDep) -> CsrfToken:
    """Sets the CSRF cookie and returns the same value, bound to the browser's session cookie if
    it has one. Fetch a new one after signing in or out."""
    secret: bytes = request.app.state.csrf_secret
    token = issue_csrf_token(secret, request.cookies.get(SESSION_COOKIE))
    cookies.set(response, CSRF_COOKIE, token, max_age=CSRF_COOKIE_MAX_AGE, http_only=False)
    return CsrfToken(csrf_token=token)


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
    profile = await UserService(db).profile(actor)
    if profile is None:
        raise UnauthenticatedError
    return Me(
        id=profile.public_id,
        phone=profile.phone_e164,
        email=profile.email,
        name=profile.name,
        roles=sorted(profile.roles),
    )


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
