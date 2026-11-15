"""What the agreements module needs from the outside world, as interfaces (ARCHITECTURE §1)."""

from typing import Protocol


class SigningCodeSender(Protocol):
    """Delivers a signing code to the person signing (ADR 0070): by email once the mail port is
    wired in; to the API's log in local development. ``user_id`` is the internal id of their
    account, so the adapter finds the address itself."""

    async def send(self, user_id: int, code: str) -> None:
        """Deliver ``code``, or raise if it couldn't be handed over."""
        ...
