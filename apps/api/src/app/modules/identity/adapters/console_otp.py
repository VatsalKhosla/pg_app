"""The development OTP sender: writes the code to the API's log instead of sending an SMS.

Settings refuse it outside local development and tests (OTP_SENDER), because a code in a log is a
key to someone's account.
"""

import structlog

logger = structlog.stdlib.get_logger(__name__)


class ConsoleOtpSender:
    async def send(self, phone_e164: str, code: str) -> None:
        # The phone number is masked in the log like everywhere else; the code is the point.
        logger.warning("development sign-in code, not sent", phone=phone_e164, code=code)
