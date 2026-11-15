"""What the agreements module needs from the outside world, as interfaces (ARCHITECTURE §1)."""

from typing import Protocol


class SigningCodeSender(Protocol):
    """Delivers a signing code to the person signing (ADR 0070): by email, through the site's
    mailer (app/core/mail.py, ADR 0068), to their account's address."""

    # Whether the code may go back to the page that asked for it, because nothing really sends it:
    # local development (the console mailer logs it), and a test site without email that shows
    # sign-in codes on screen too (ADR 0055). Never in production.
    shows_code: bool

    async def send(self, to: str, code: str) -> None:
        """Deliver ``code`` to the address ``to``, or raise if it couldn't be handed over."""
        ...
