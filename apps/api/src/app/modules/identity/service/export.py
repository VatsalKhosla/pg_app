"""What the identity module holds about a person, for their data export (the DPDP Act's right of
access). Runs inside the export job's transaction; every module with personal data adds its own
part (app/jobs.py lists them)."""

from typing import TYPE_CHECKING

from app.modules.identity.domain.staff import IdentityProvider
from app.modules.identity.repository import (
    ConsentRepository,
    IdentityRepository,
    OtpRepository,
    SessionRepository,
    TotpRepository,
    UserRepository,
)

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession


def _iso(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat()


async def personal_data(db: AsyncSession, user_id: int) -> dict[str, object]:
    """The account, its roles, consents, sessions, recent sign-in codes and sign-in methods,
    without secrets (no session tokens, code hashes or authenticator salts)."""
    users = UserRepository(db)
    user = await users.get(user_id)
    if user is None:
        return {}
    google = await IdentityRepository(db).for_user(user_id, IdentityProvider.GOOGLE)
    authenticator = await TotpRepository(db).for_user(user_id)
    return {
        "account": {
            "id": str(user.public_id),
            "phone": user.phone_e164,
            "email": user.email,
            "name": user.name,
            "collegeOrWorkplace": user.college_or_workplace,
            "gender": user.gender,
            "status": user.status,
            "createdAt": _iso(user.created_at),
            "roles": sorted(await users.roles(user_id)),
        },
        "consents": [
            {
                "purpose": consent.purpose,
                "noticeVersion": consent.notice_version,
                "grantedAt": _iso(consent.granted_at),
                "withdrawnAt": _iso(consent.withdrawn_at),
            }
            for consent in await ConsentRepository(db).history(user_id)
        ],
        "sessions": [
            {
                "kind": session.kind,
                "startedAt": _iso(session.started_at),
                "lastSeenAt": _iso(session.last_seen_at),
                "expiresAt": _iso(session.expires_at),
                "endedAt": _iso(session.ended_at),
                "endReason": session.end_reason,
                "ipAddress": session.ip_address,
                "userAgent": session.user_agent,
            }
            for session in await SessionRepository(db).all_for_user(user_id)
        ],
        "signInCodes": [
            {
                "requestedAt": _iso(challenge.requested_at),
                "ipAddress": challenge.ip_address,
                "userAgent": challenge.user_agent,
            }
            for challenge in await OtpRepository(db).for_phone(user.phone_e164)
        ],
        "googleAccount": None
        if google is None
        else {"email": google.email, "lastUsedAt": _iso(google.last_used_at)},
        "authenticatorApp": None
        if authenticator is None or authenticator.confirmed_at is None
        else {"setUpAt": _iso(authenticator.confirmed_at)},
    }
