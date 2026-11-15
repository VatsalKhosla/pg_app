"""Where messages go out (ADR 0068): the mail sender settings choose, and every module's message
wording, so an email reads as its text would. Used by the API (sign-in codes) and the worker."""

from typing import TYPE_CHECKING

from app.config import BRAND_NAME
from app.core.mail import ConsoleMailer, Mailer, NoMailer, SmtpMailer
from app.modules.booking.texts import TEMPLATES as BOOKING
from app.modules.compliance.texts import TEMPLATES as COMPLIANCE
from app.modules.invoices.texts import TEMPLATES as INVOICES
from app.modules.payments.texts import TEMPLATES as PAYMENTS
from app.modules.visits.texts import TEMPLATES as VISITS

if TYPE_CHECKING:
    from app.config import Settings


def build_mailer(settings: Settings) -> Mailer:
    if settings.mail_sender == "smtp":
        username, password = settings.smtp_username, settings.smtp_password
        sender = settings.mail_from
        if username is None or password is None or sender is None:  # the settings refuse this
            msg = "MAIL_SENDER=smtp needs SMTP_USERNAME, SMTP_PASSWORD and MAIL_FROM"
            raise ValueError(msg)
        return SmtpMailer(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=username,
            password=password.get_secret_value(),
            sender=sender,
            name=BRAND_NAME,
        )
    if settings.mail_sender == "console":
        return ConsoleMailer()
    return NoMailer()


def message_templates() -> dict[str, str]:
    """Every message's wording by its template's name: the modules' names don't overlap."""
    templates: dict[str, str] = {}
    for module in (VISITS, BOOKING, PAYMENTS, INVOICES, COMPLIANCE):
        overlap = templates.keys() & module.keys()
        if overlap:
            msg = f"two modules use the same message names: {sorted(overlap)}"
            raise ValueError(msg)
        templates |= module
    return templates
