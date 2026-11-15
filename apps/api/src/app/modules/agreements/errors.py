"""The agreements module's errors (ARCHITECTURE §15, ADR 0070)."""

import math
from typing import TYPE_CHECKING

from app.core.errors import AppError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import timedelta


class AgreementTextChangedError(AppError):
    """The signer was shown a text that isn't the agreement's text now: the booking's facts or the
    template changed while they read. They read the new text and sign that."""

    status = 409
    code = "AGREEMENT_TEXT_CHANGED"
    title = "The agreement has changed since you opened it"


class AgreementNotReadyError(AppError):
    """Nobody may sign yet: the text still lacks something, such as the student's name."""

    status = 409
    code = "AGREEMENT_NOT_READY"
    title = "The agreement isn't ready to sign yet"


class SigningNeedsEmailError(AppError):
    """The signer's account has no email address to send the code to, while texts can't go yet
    (ADR 0068). An owner's address is added by ops; a student signs in with theirs."""

    status = 409
    code = "SIGNING_NEEDS_EMAIL"
    title = "Your account needs an email address to sign"


class SigningCodeInvalidError(AppError):
    """A wrong code, a used or replaced one, or none asked for: deliberately one error."""

    status = 400
    code = "SIGNING_CODE_INVALID"
    title = "That code isn't right"


class SigningCodeExpiredError(AppError):
    status = 400
    code = "SIGNING_CODE_EXPIRED"
    title = "That code has expired"


class SigningCodeLockedError(AppError):
    status = 400
    code = "SIGNING_CODE_LOCKED"
    title = "Too many wrong codes"


class SigningCodeTooSoonError(AppError):
    status = 429
    code = "SIGNING_CODE_TOO_SOON"
    title = "Please wait before asking for another code"

    def __init__(self, wait: timedelta) -> None:
        seconds = max(1, math.ceil(wait.total_seconds()))
        super().__init__(
            f"You can ask for a new code in {seconds} seconds.",
            headers={"Retry-After": str(seconds)},
        )


class PoliceDetailsInvalidError(AppError):
    """Details the police form can't take, as the domain's rules say; every problem in the
    detail."""

    status = 422
    code = "POLICE_DETAILS_INVALID"
    title = "Those details can't be used as they are"

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__(" ".join(problems))
        self.problems = list(problems)


class AcknowledgementInvalidError(AppError):
    """An acknowledgement that isn't the owner's own upload, isn't a document, or was refused as a
    file."""

    status = 422
    code = "ACKNOWLEDGEMENT_INVALID"
    title = "That acknowledgement can't be used"
