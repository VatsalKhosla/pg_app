"""The OTP sender for an environment without SMS yet (OTP_SENDER=unavailable): phone sign-in answers
503 while everything else works. Until the founders choose an SMS provider, this is what a
deployed environment runs."""

from app.core.errors import ServiceUnavailableError


class UnavailableOtpSender:
    shows_code = False

    async def send(self, phone_e164: str, code: str) -> None:
        raise ServiceUnavailableError("Signing in by phone isn't available yet.")
