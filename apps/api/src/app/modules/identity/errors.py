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


class StaffSignInExpiredError(AppError):
    """The Google sign-in can't be finished: it took too long, was started in another tab, or its
    code was already used. Starting again fixes it."""

    status = 400
    code = "STAFF_SIGN_IN_EXPIRED"
    title = "Sign-in expired; please start again"


class StaffSignInCancelledError(AppError):
    status = 400
    code = "STAFF_SIGN_IN_CANCELLED"
    title = "Sign-in was cancelled"


class StaffAccountNotAllowedError(AppError):
    """Deliberately one error for every reason (not an allowed Google account, not staff, no
    authenticator, suspended), so nobody can probe who is staff."""

    status = 403
    code = "STAFF_ACCOUNT_NOT_ALLOWED"
    title = "This account can't sign in to staff tools"


class TotpInvalidError(AppError):
    status = 400
    code = "TOTP_INVALID"
    title = "That authenticator code isn't right"


class ConsentRequiredError(AppError):
    """A first sign-in creates the account only with consent to the privacy notice's required
    purposes. The code stays usable: send it again with the consent."""

    status = 400
    code = "CONSENT_REQUIRED"
    title = "Agree to the privacy notice to create your account"


class PrivacyNoticeChangedError(AppError):
    """The consent names a privacy notice version that isn't the current one."""

    status = 409
    code = "PRIVACY_NOTICE_CHANGED"
    title = "The privacy notice has changed; please read the new one"


class ConsentNeededForAccountError(AppError):
    status = 409
    code = "CONSENT_NEEDED_FOR_ACCOUNT"
    title = "The account can't run without this consent; ask for the account's deletion instead"
