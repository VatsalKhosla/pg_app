"""Errors of the identity module, as problem details with stable codes (ARCHITECTURE §15)."""

import math
from datetime import timedelta

from app.core.errors import AppError


class OtpInvalidError(AppError):
    """A wrong code, or a challenge that doesn't exist, was used, or was replaced. Deliberately
    one error for all of these, so nothing about other people's challenges leaks."""

    status = 400
    code = "OTP_INVALID"
    title = "That code isn't right"


class OtpExpiredError(AppError):
    status = 400
    code = "OTP_EXPIRED"
    title = "That code has expired"


class OtpLockedError(AppError):
    status = 400
    code = "OTP_LOCKED"
    title = "Too many wrong codes"


class OtpResendTooSoonError(AppError):
    status = 429
    code = "OTP_RESEND_TOO_SOON"
    title = "Please wait before asking for another code"

    def __init__(self, wait: timedelta) -> None:
        seconds = max(1, math.ceil(wait / timedelta(seconds=1)))
        super().__init__(
            f"You can ask for a new code in {seconds} seconds.",
            headers={"Retry-After": str(seconds)},
        )


class AccountSuspendedError(AppError):
    status = 403
    code = "ACCOUNT_SUSPENDED"
    title = "This account is suspended"
