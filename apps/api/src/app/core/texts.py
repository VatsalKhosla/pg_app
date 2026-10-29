"""Text messages to people's phones (ARCHITECTURE §14): visit confirmations and reminders now,
booking messages later.

In India a business text is a DLT-registered template with its blanks filled in, sent through a
provider the founders choose (a paid vendor). Until then there are two adapters: one writes each
message to the log (local development and tests; phone numbers masked as everywhere), the other,
for deployed environments, sends nothing and says so, so ops know to call instead.
"""

from typing import TYPE_CHECKING, Protocol

import structlog

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = structlog.stdlib.get_logger(__name__)


class Texts(Protocol):
    async def send(self, phone_e164: str, template: str, values: Mapping[str, str]) -> None:
        """Send ``template`` with its blanks filled in; raise if the provider didn't take it, so
        the job is tried again."""
        ...


class ConsoleTexts:
    async def send(self, phone_e164: str, template: str, values: Mapping[str, str]) -> None:
        logger.info("text message, not sent", phone=phone_e164, template=template, **values)


class NoTexts:
    """No provider yet (TEXT_SENDER=unavailable): nothing goes, and the log says what didn't."""

    async def send(self, phone_e164: str, template: str, values: Mapping[str, str]) -> None:
        logger.warning("text messages are off; not sent", phone=phone_e164, template=template)
