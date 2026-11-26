"""Messages by email (ADR 0068): who gets an email and who a text, what the email says, and how
it reaches Gmail's server."""

import asyncio
import smtplib
from collections.abc import Callable, Mapping
from email.message import EmailMessage
from typing import ClassVar, Self

import pytest
from pydantic import SecretStr

from app.config import BRAND_NAME, Settings
from app.core import mail
from app.core.mail import ConsoleMailer, NoMailer, SmtpMailer
from app.core.pii import mask_email
from app.core.texts import SUBJECT_MAX, MailTexts, Recipient, subject_of
from app.messages import build_mailer, message_templates
from app.modules.booking.texts import TEMPLATES as BOOKING
from app.modules.compliance.texts import TEMPLATES as COMPLIANCE
from app.modules.invoices.texts import TEMPLATES as INVOICES
from app.modules.payments.texts import TEMPLATES as PAYMENTS
from app.modules.visits.texts import TEMPLATES as VISITS

STUDENT = Recipient(phone_e164="+919876543210", email="student@example.com")
TEMPLATES = {"visit": "{brand}: your visit to {pg} is booked for {when}. Our agent will meet you."}
VALUES = {"brand": "Stays", "pg": "Fictional House", "when": "Sat 10:30"}


class RecordedMailer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to: str, subject: str, text: str) -> None:
        self.sent.append((to, subject, text))


class RecordedTexts:
    def __init__(self) -> None:
        self.sent: list[tuple[Recipient, str, dict[str, str]]] = []

    async def send(self, to: Recipient, template: str, values: Mapping[str, str]) -> None:
        self.sent.append((to, template, dict(values)))


def _messages() -> tuple[MailTexts, RecordedMailer, RecordedTexts]:
    mailer, texts = RecordedMailer(), RecordedTexts()
    messages = MailTexts(mailer, TEMPLATES, fallback=texts, signature="Stays\nhttps://example.in")
    return messages, mailer, texts


def test_a_person_with_an_address_gets_the_message_by_email() -> None:
    messages, mailer, texts = _messages()

    asyncio.run(messages.send(STUDENT, "visit", VALUES))

    assert mailer.sent == [
        (
            "student@example.com",
            "Stays: your visit to Fictional House is booked for Sat 10:30",
            "Stays: your visit to Fictional House is booked for Sat 10:30. Our agent will meet "
            "you.\n\nStays\nhttps://example.in\n",
        )
    ]
    assert texts.sent == []


def test_a_person_without_an_address_gets_a_text() -> None:
    messages, mailer, texts = _messages()
    phone_only = Recipient(phone_e164="+919876543210")

    asyncio.run(messages.send(phone_only, "visit", VALUES))

    assert mailer.sent == []
    assert texts.sent == [(phone_only, "visit", VALUES)]


def test_a_message_with_no_written_wording_goes_as_a_text() -> None:
    messages, mailer, texts = _messages()

    asyncio.run(messages.send(STUDENT, "unknown", VALUES))

    assert mailer.sent == []
    assert texts.sent == [(STUDENT, "unknown", VALUES)]


def test_a_subject_is_the_first_sentence_and_fits_an_inbox() -> None:
    assert subject_of("Your visit is booked. See you then.") == "Your visit is booked"
    long = "A" * 200 + ". The rest."
    subject = subject_of(long)
    assert len(subject) == SUBJECT_MAX
    assert subject.endswith("…")


def test_every_modules_wording_is_there_once() -> None:
    templates = message_templates()

    modules = (VISITS, BOOKING, PAYMENTS, INVOICES, COMPLIANCE)
    assert len(templates) == sum(len(module) for module in modules)
    for module in modules:
        assert module.items() <= templates.items()


def test_an_email_address_is_masked_but_for_its_first_letter() -> None:
    assert mask_email("student@example.com") == "s***@example.com"
    assert mask_email("not-an-address") == "***"


@pytest.mark.parametrize(
    ("sender", "kind"),
    [("console", ConsoleMailer), ("unavailable", NoMailer), ("smtp", SmtpMailer)],
)
def test_the_settings_choose_the_mailer(
    make_settings: Callable[..., Settings], sender: str, kind: type
) -> None:
    settings = make_settings(
        mail_sender=sender,
        smtp_username="support@example.in",
        smtp_password="an-app-password",
        mail_from="support@example.in",
    )

    assert isinstance(build_mailer(settings), kind)


def test_smtp_waiting_for_its_password_sends_nothing(
    make_settings: Callable[..., Settings],
) -> None:
    settings = make_settings(
        mail_sender="smtp", smtp_username="support@example.in", mail_from="support@example.in"
    )

    assert isinstance(build_mailer(settings), NoMailer)


class FakeSmtp:
    """smtplib.SMTP as a test sees it: what was called, in order."""

    instances: ClassVar[list[FakeSmtp]] = []

    def __init__(self, host: str, port: int, *, timeout: float) -> None:
        self.calls: list[object] = [("connect", host, port, timeout)]
        self.message: EmailMessage | None = None
        FakeSmtp.instances.append(self)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.calls.append("quit")

    def starttls(self, *, context: object) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(("login", user, password))

    def send_message(self, message: EmailMessage) -> None:
        self.calls.append("send")
        self.message = message


def test_email_goes_to_the_smtp_server_over_tls_after_logging_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeSmtp.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    mailer = SmtpMailer(
        host="smtp.gmail.com",
        port=587,
        username="support@example.in",
        password=SecretStr("an-app-password").get_secret_value(),
        sender="support@example.in",
        name=BRAND_NAME,
    )

    asyncio.run(mailer.send("student@example.com", "Your visit is booked", "The whole message."))

    [server] = FakeSmtp.instances
    assert server.calls == [
        ("connect", "smtp.gmail.com", 587, mail.SMTP_TIMEOUT_SECONDS),
        "starttls",
        ("login", "support@example.in", "an-app-password"),
        "send",
        "quit",
    ]
    assert server.message is not None
    assert server.message["From"] == f"{BRAND_NAME} <support@example.in>"
    assert server.message["To"] == "student@example.com"
    assert server.message["Subject"] == "Your visit is booked"
    assert server.message["Message-ID"].endswith("@example.in>")
    assert server.message.get_content() == "The whole message.\n"
