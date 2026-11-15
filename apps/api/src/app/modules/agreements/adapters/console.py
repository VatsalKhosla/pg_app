"""Signing-code senders for where no email goes out (ADR 0070).

``ConsoleSigningCodeSender`` writes the code to the API's log, for local development and tests:
the API also hands the code back to the page there. ``UnavailableSigningCodeSender`` refuses to
send any, so a deployed environment without email delivery answers 503 rather than pretending a
code went out. The mail adapter replaces it once the mail port is wired in.
"""

import structlog

from app.core.errors import ServiceUnavailableError

logger = structlog.stdlib.get_logger(__name__)


class ConsoleSigningCodeSender:
    async def send(self, user_id: int, code: str) -> None:
        logger.warning("development signing code, not sent", user_id=user_id, code=code)


class UnavailableSigningCodeSender:
    async def send(self, user_id: int, code: str) -> None:
        raise ServiceUnavailableError("Signing codes can't be sent yet. Please try again later.")
