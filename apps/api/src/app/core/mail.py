"""Email (ADR 0068): sign-in codes and every message the site sends, from the founders' Google
Workspace address through Gmail's SMTP server, until text messages can go too (they need DLT
registration). Three adapters: one writes each message to the log (development and tests), one
sends nothing and says so, and one hands it to an SMTP server.
"""

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Protocol

import structlog

from app.core.pii import mask_email

logger = structlog.stdlib.get_logger(__name__)

# A provider that hasn't answered in this long isn't going to: the job is tried again.
SMTP_TIMEOUT_SECONDS = 20


class Mailer(Protocol):
    async def send(self, to: str, subject: str, text: str) -> None:
        """Send a plain-text email; raise if the server didn't take it, so the job is tried
        again."""
        ...


class ConsoleMailer:
    """Development and tests: the message goes to the log, in full (it may hold a sign-in code)."""

    async def send(self, to: str, subject: str, text: str) -> None:
        logger.info("email, not sent", to=mask_email(to), subject=subject, text=text)


class NoMailer:
    """No mail server set up (MAIL_SENDER=unavailable): nothing goes, and the log says what
    didn't."""

    async def send(self, to: str, subject: str, text: str) -> None:
        logger.warning("email is off; not sent", to=mask_email(to), subject=subject)


class SmtpMailer:
    """An SMTP server with STARTTLS and a login: Gmail's (smtp.gmail.com:587) with a Google
    Workspace account's app password. The standard library's client, in a thread."""

    def __init__(
        self, *, host: str, port: int, username: str, password: str, sender: str, name: str
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from = formataddr((name, sender))
        self._domain = sender.rpartition("@")[2]

    async def send(self, to: str, subject: str, text: str) -> None:
        message = EmailMessage()
        message["From"] = self._from
        message["To"] = to
        message["Subject"] = subject
        message["Message-ID"] = make_msgid(domain=self._domain)
        message.set_content(text)
        await asyncio.to_thread(self._deliver, message)
        logger.info("email sent", to=mask_email(to), subject=subject)

    def _deliver(self, message: EmailMessage) -> None:
        context = ssl.create_default_context()
        with smtplib.SMTP(self._host, self._port, timeout=SMTP_TIMEOUT_SECONDS) as server:
            server.starttls(context=context)
            server.login(self._username, self._password)
            server.send_message(message)
