"""The OTP sender for a test site with no SMS yet (OTP_SENDER=screen, ADR 0055): nothing is sent,
and the sign-in page shows the code (``shows_code``).

Whoever asks for a code gets it, so anyone can sign in with any number. That's acceptable on a test
copy of the site with fictional PGs, under a banner saying so, and never anywhere else: settings
refuse this sender in production.
"""


class ScreenOtpSender:
    shows_code = True

    async def send(self, phone_e164: str, code: str) -> None:
        """Nothing to deliver, and nothing logged: the API's answer carries the code."""
