"""The identity module's background jobs, registered in app/jobs.py."""

from typing import TYPE_CHECKING, Final

from app.modules.identity.service import delete_finished_sessions, delete_old_challenges

if TYPE_CHECKING:
    from app.core.outbox import JobContext, JobPayload

SESSIONS_CLEANUP: Final = "identity.sessions_cleanup"
OTP_CLEANUP: Final = "identity.otp_cleanup"


async def delete_finished_sessions_job(context: JobContext, _payload: JobPayload) -> None:
    """Daily: delete sessions (with their IP address and user agent) past their retention."""
    await delete_finished_sessions(context.session, context.clock)


async def delete_old_challenges_job(context: JobContext, _payload: JobPayload) -> None:
    """Daily: delete sign-in challenges (phone number, IP address, user agent) after 7 days."""
    await delete_old_challenges(context.session, context.clock)
