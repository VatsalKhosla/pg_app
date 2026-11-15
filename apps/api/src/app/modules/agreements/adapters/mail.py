"""Signing codes by email (ADR 0070), sent through the site's mailer as sign-in codes are (ADR
0068): from the founders' Workspace address through Gmail, or to the log in local development."""

from typing import TYPE_CHECKING

from app.config import BRAND_NAME
from app.core.errors import ServiceUnavailableError
from app.modules.agreements.domain.codes import CODE_TTL

if TYPE_CHECKING:
    from app.core.mail import Mailer


class MailSigningCodes:
    """Codes go through ``mailer``. Without one (MAIL_SENDER=unavailable), a test site that shows
    sign-in codes on screen shows these too; anywhere else, signing waits for email."""

    def __init__(self, mailer: Mailer | None, *, shows_code: bool, site_url: str) -> None:
        self._mailer = mailer
        self.shows_code = shows_code
        self._site_url = site_url

    async def send(self, to: str, code: str) -> None:
        if self._mailer is None:
            if self.shows_code:
                return  # The API's answer carries the code.
            raise ServiceUnavailableError(
                "Signing codes can't be sent yet. Please try again later."
            )
        minutes = int(CODE_TTL.total_seconds() // 60)
        await self._mailer.send(
            to,
            f"Your {BRAND_NAME} code to sign your rent agreement",
            f"Your code to sign your rent agreement is {code}.\n\n"
            f"It works for {minutes} minutes. Enter it on your booking's page with your full "
            "name to sign. If you didn't ask for it, you can ignore this email: nobody can sign "
            "for you without the code.\n\n"
            f"{BRAND_NAME}\n{self._site_url}\n",
        )
