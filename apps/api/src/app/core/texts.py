"""Messages to people (ARCHITECTURE §14): visit confirmations and reminders, bookings, refunds,
invoices and complaints.

A message goes to a person, by email when they have an address (ADR 0068), else by text. In India a
business text is a DLT-registered template with its blanks filled in, sent through a provider the
founders choose; until that's done, texts go to the log (local development and tests; phone
numbers masked as everywhere) or nowhere (deployed environments), and email carries the message.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import structlog

from app.core.pii import mask_email

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.core.mail import Mailer

logger = structlog.stdlib.get_logger(__name__)

# An email's subject is its message's first sentence, cut to this length.
SUBJECT_MAX = 78


@dataclass(frozen=True, slots=True)
class Recipient:
    """Whom a message is for: at least one of the two."""

    phone_e164: str | None = None
    email: str | None = None


class Texts(Protocol):
    async def send(self, to: Recipient, template: str, values: Mapping[str, str]) -> None:
        """Send ``template`` with its blanks filled in; raise if the provider didn't take it, so
        the job is tried again."""
        ...


class ConsoleTexts:
    async def send(self, to: Recipient, template: str, values: Mapping[str, str]) -> None:
        logger.info("text message, not sent", phone=to.phone_e164, template=template, **values)


class NoTexts:
    """No provider yet (TEXT_SENDER=unavailable): nothing goes, and the log says what didn't."""

    async def send(self, to: Recipient, template: str, values: Mapping[str, str]) -> None:
        logger.warning("text messages are off; not sent", phone=to.phone_e164, template=template)


def subject_of(text: str) -> str:
    """An email's subject: the message's first sentence, short enough for an inbox."""
    first = text.split(". ", 1)[0].rstrip(".")
    return first if len(first) <= SUBJECT_MAX else first[: SUBJECT_MAX - 1].rstrip() + "…"


class MailTexts:
    """Each message by email when its person has an address, written from the same template as
    the text; otherwise to ``fallback`` (the text sender)."""

    def __init__(
        self,
        mailer: Mailer,
        templates: Mapping[str, str],
        *,
        fallback: Texts,
        signature: str,
    ) -> None:
        self._mailer = mailer
        self._templates = templates
        self._fallback = fallback
        self._signature = signature

    async def send(self, to: Recipient, template: str, values: Mapping[str, str]) -> None:
        wording = self._templates.get(template)
        if to.email is None or wording is None:
            await self._fallback.send(to, template, values)
            return
        text = wording.format_map(dict(values))
        logger.info("message by email", to=mask_email(to.email), template=template)
        await self._mailer.send(to.email, subject_of(text), f"{text}\n\n{self._signature}\n")
