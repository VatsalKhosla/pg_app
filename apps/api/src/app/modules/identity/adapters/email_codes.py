"""Sign-in codes by email (ADR 0068), sent through the site's mailer (app/core/mail.py)."""

from typing import TYPE_CHECKING

from app.config import BRAND_NAME
from app.core.errors import ServiceUnavailableError

if TYPE_CHECKING:
    from datetime import timedelta

    from app.core.mail import Mailer


def _minutes(ttl: timedelta) -> int:
    return int(ttl.total_seconds() // 60)


class EmailCodes:
    """Codes go through ``mailer``. Without one (MAIL_SENDER=unavailable), a test site that shows
    phone codes on screen shows these too (ADR 0055); anywhere else, email sign-in is off."""

    def __init__(
        self, mailer: Mailer | None, *, shows_code: bool, ttl: timedelta, site_url: str
    ) -> None:
        self._mailer = mailer
        self.shows_code = shows_code
        self.available = mailer is not None or shows_code
        self._ttl = ttl
        self._site_url = site_url

    async def send(self, email: str, code: str) -> None:
        if self._mailer is None:
            if self.shows_code:
                return  # The API's answer carries the code.
            raise ServiceUnavailableError("Signing in by email isn't available yet.")
        await self._mailer.send(
            email,
            f"Your {BRAND_NAME} sign-in code",
            f"Your sign-in code is {code}.\n\n"
            f"It works for {_minutes(self._ttl)} minutes. If you didn't ask for it, you can "
            "ignore this email: nobody can sign in without the code.\n\n"
            f"{BRAND_NAME}\n{self._site_url}\n",
        )
