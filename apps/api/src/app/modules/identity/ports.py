"""What the identity module needs from the outside world, as interfaces (ARCHITECTURE §1)."""

from typing import Protocol


class OtpSender(Protocol):
    """Delivers a sign-in code to a phone. Production uses an SMS provider with a DLT-registered
    template (the founders choose it); development writes the code to the log."""

    async def send(self, phone_e164: str, code: str) -> None:
        """Deliver ``code``, or raise if it couldn't be handed to the provider."""
        ...
