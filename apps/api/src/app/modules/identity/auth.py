"""Who is calling: the session cookie turned into an ``Actor``, for routes of any module.

``CurrentActor`` answers 401 without a live session. When activity slides the session's expiry,
the cookie goes out again with the new lifetime, so the browser keeps it as long as the server
does.
"""

from typing import Annotated

from fastapi import Depends, Request, Response

from app.core.actor import Actor
from app.core.clock import ClockDep
from app.core.cookies import SESSION_COOKIE, CookiePolicy
from app.core.db import DbSession
from app.core.errors import UnauthenticatedError
from app.modules.identity.service import OtpService, SessionService, StaffSignInService


def get_cookie_policy(request: Request) -> CookiePolicy:
    policy: CookiePolicy = request.app.state.cookies
    return policy


CookiesDep = Annotated[CookiePolicy, Depends(get_cookie_policy)]


async def get_actor(
    request: Request, response: Response, db: DbSession, clock: ClockDep, cookies: CookiesDep
) -> Actor:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise UnauthenticatedError
    authentication = await SessionService(db, clock).authenticate(token)
    if authentication is None:
        raise UnauthenticatedError
    if authentication.refreshed:
        remaining = authentication.expires_at - clock.now()
        cookies.set(
            response,
            SESSION_COOKIE,
            token,
            max_age=int(remaining.total_seconds()),
            http_only=True,
        )
    return authentication.actor


CurrentActor = Annotated[Actor, Depends(get_actor)]


def get_otp_service(request: Request, db: DbSession, clock: ClockDep) -> OtpService:
    state = request.app.state
    return OtpService(
        db,
        clock,
        secret=state.secret_key,
        sender=state.otp_sender,
        human_check=state.human_check,
        limiter=state.rate_limiter,
    )


OtpServiceDep = Annotated[OtpService, Depends(get_otp_service)]


def get_staff_sign_in_service(
    request: Request, db: DbSession, clock: ClockDep
) -> StaffSignInService:
    state = request.app.state
    return StaffSignInService(
        db,
        clock,
        secret=state.secret_key,
        google=state.google_sign_in,
        google_domains=state.staff_google_domains,
        google_emails=state.staff_google_emails,
        limiter=state.rate_limiter,
    )


StaffSignInDep = Annotated[StaffSignInService, Depends(get_staff_sign_in_service)]
