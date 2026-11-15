"""Rent agreements without a database (ADR 0070): the state machine (every pair, and properties over
any order of events), signing codes, typed names, the text made from a booking, and the templates
on file."""

import asyncio
import hashlib
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from itertools import product
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.config import BRAND_NAME, Settings
from app.core.errors import ServiceUnavailableError
from app.main import create_app, signing_codes
from app.modules.agreements.adapters.mail import MailSigningCodes
from app.modules.agreements.domain.agreements import (
    FINAL,
    SIGNS,
    AgreementEvent,
    AgreementRefusedError,
    AgreementStatus,
    Signer,
    awaits,
    signed_by,
    text_settled,
    transition,
    typed_name,
)
from app.modules.agreements.domain.codes import (
    CODE_TTL,
    MAX_ATTEMPTS,
    RESEND_COOLDOWN,
    CodeState,
    attempts_left,
    code_state,
    resend_wait,
)
from app.modules.agreements.domain.terms import (
    NAME_MISSING,
    ChargeCadence,
    ChargeTerm,
    TemplateError,
    Tenancy,
    blanks,
    missing,
    render,
    spoken_day,
    text_sha256,
)
from app.modules.agreements.templates import (
    CURRENT_VERSION,
    TEMPLATES_DIR,
    VERSION_PATTERN,
    FileTemplates,
    Templates,
    is_draft,
)
from app.modules.catalog.domain.agreements import Agreement
from tests.agreements import FixedAgreements, FixedTemplates

S = AgreementStatus
E = AgreementEvent
ALLOWED = {
    (S.AWAITING_SIGNATURES, E.STUDENT_SIGNS): S.SIGNED_BY_STUDENT,
    (S.AWAITING_SIGNATURES, E.OWNER_SIGNS): S.SIGNED_BY_OWNER,
    (S.SIGNED_BY_STUDENT, E.OWNER_SIGNS): S.SIGNED,
    (S.SIGNED_BY_OWNER, E.STUDENT_SIGNS): S.SIGNED,
    (S.AWAITING_SIGNATURES, E.BOOKING_ENDED_EARLY): S.VOID,
    (S.SIGNED_BY_STUDENT, E.BOOKING_ENDED_EARLY): S.VOID,
    (S.SIGNED_BY_OWNER, E.BOOKING_ENDED_EARLY): S.VOID,
}
# Every version on file, with the SHA-256 of its file: a text people may have signed never changes.
# A change is a new version, with its own line here.
PINNED = {"draft-1": "172e052891f7c752c89098fde330e80bd5be54d05432627163e13c6a69461001"}


@pytest.mark.parametrize(("status", "event"), list(product(S, E)))
def test_the_state_machine_allows_exactly_its_table(status: S, event: E) -> None:
    if (status, event) in ALLOWED:
        assert transition(status, event) is ALLOWED[status, event]
    else:
        with pytest.raises(AgreementRefusedError):
            transition(status, event)


def test_refusals_say_why() -> None:
    with pytest.raises(AgreementRefusedError, match="signed this agreement already"):
        transition(S.SIGNED_BY_STUDENT, E.STUDENT_SIGNS)
    with pytest.raises(AgreementRefusedError, match="Both sides have signed"):
        transition(S.SIGNED, E.BOOKING_ENDED_EARLY)
    with pytest.raises(AgreementRefusedError, match="void"):
        transition(S.VOID, E.OWNER_SIGNS)


@given(st.lists(st.sampled_from(list(E)), max_size=12))
def test_any_order_of_events_keeps_the_agreement_honest(events: list[E]) -> None:
    """Whatever arrives, in whatever order: each side signs at most once, an agreement is signed
    exactly when both have, nothing leaves a final status, and a signed one is never voided."""
    status = S.AWAITING_SIGNATURES
    signers: list[Signer] = []
    for event in events:
        try:
            after = transition(status, event)
        except AgreementRefusedError:
            continue
        assert status not in FINAL
        if event is E.BOOKING_ENDED_EARLY:
            assert after is S.VOID
            assert status is not S.SIGNED
        else:
            signer = Signer.STUDENT if event is E.STUDENT_SIGNS else Signer.OWNER
            assert awaits(status, signer)
            assert signer not in signers
            signers.append(signer)
            assert signed_by(after) == frozenset(signers)
        status = after
    assert (status is S.SIGNED) == (set(signers) == set(Signer))
    assert len(signers) == len(set(signers))


def test_the_text_settles_at_the_first_signature_and_on_voiding() -> None:
    assert not text_settled(S.AWAITING_SIGNATURES)
    assert all(text_settled(status) for status in S if status is not S.AWAITING_SIGNATURES)


def test_each_side_signs_with_its_own_event() -> None:
    assert SIGNS == {Signer.STUDENT: E.STUDENT_SIGNS, Signer.OWNER: E.OWNER_SIGNS}
    assert awaits(S.SIGNED_BY_OWNER, Signer.STUDENT)
    assert not awaits(S.SIGNED_BY_OWNER, Signer.OWNER)
    assert not awaits(S.VOID, Signer.STUDENT)


@pytest.mark.parametrize(
    ("typed", "kept"),
    [
        ("  Asha   Verma ", "Asha Verma"),
        ("Ananya D'Souza", "Ananya D'Souza"),
        ("Ananya D\u2019Souza", "Ananya D\u2019Souza"),
        ("Mary-Jane O. Kumar", "Mary-Jane O. Kumar"),
        ("आशा वर्मा", "आशा वर्मा"),
        ("Asha\nVerma", "Asha Verma"),
        ("A", None),
        ("Asha 2", None),
        ("<script>", None),
        ("...", None),
        ("x" * 81, None),
    ],
)
def test_a_typed_name_is_letters_tidied(typed: str, kept: str | None) -> None:
    assert typed_name(typed) == kept


NOW = datetime(2027, 8, 1, 10, 0, tzinfo=UTC)


def test_a_signing_code_is_open_until_used_locked_or_expired() -> None:
    def state(**changes: object) -> CodeState:
        values: dict[str, object] = {
            "now": NOW,
            "expires_at": NOW + CODE_TTL,
            "attempts": 0,
            "consumed_at": None,
            "superseded_at": None,
        } | changes
        return code_state(**values)  # type: ignore[arg-type]

    assert state() is CodeState.OPEN
    assert state(consumed_at=NOW) is CodeState.USED
    assert state(superseded_at=NOW) is CodeState.USED
    assert state(attempts=MAX_ATTEMPTS) is CodeState.LOCKED
    assert state(attempts=MAX_ATTEMPTS - 1) is CodeState.OPEN
    assert state(now=NOW + CODE_TTL) is CodeState.EXPIRED
    assert timedelta(minutes=10) == CODE_TTL


def test_a_new_code_waits_for_the_cooldown() -> None:
    assert resend_wait(now=NOW, last_requested_at=None) == timedelta(0)
    assert resend_wait(now=NOW, last_requested_at=NOW - timedelta(seconds=10)) == timedelta(
        seconds=20
    )
    assert resend_wait(now=NOW, last_requested_at=NOW - RESEND_COOLDOWN) == timedelta(0)
    assert attempts_left(3) == 2
    assert attempts_left(9) == 0


TENANCY = Tenancy(
    booking_code="BK-7F3K2Q9M",
    licensor="Fictional Stays Private Limited",
    licensor_business="Fictional Stays",
    licensee="Asha Verma",
    pg_name="Fictional Residency",
    pg_address="House 1, a fictional lane, Satya Niketan",
    room_type="Double sharing",
    room="101",
    bed="A",
    move_in=date(2027, 8, 20),
    stay_months=11,
    planned_move_out=date(2028, 7, 20),
    monthly_rent_paise=1_030_000,
    deposit_paise=1_000_000,
    token_paise=200_000,
    due_at_move_in_paise=830_000,
    monthly_charges_paise=80_000,
    one_time_charges_paise=50_000,
    charges=(
        ChargeTerm("Electricity", ChargeCadence.METERED, 80_000, rate_paise=900, unit="kWh"),
        ChargeTerm("Registration", ChargeCadence.ONE_TIME, 50_000),
    ),
)


def _current() -> str:
    template = FileTemplates().get(CURRENT_VERSION)
    assert template is not None
    return template


def test_the_text_states_the_bookings_facts_and_amounts_as_the_booking_has_them() -> None:
    text = render(_current(), TENANCY, brand=BRAND_NAME)

    for fact in (
        "BK-7F3K2Q9M",
        "Fictional Stays Private Limited",
        "Asha Verma",
        "Fictional Residency, House 1, a fictional lane, Satya Niketan",
        "bed A in room 101 (Double sharing)",
        "20 August 2027",
        "11 months, until 20 July 2028",
        "₹10,300",
        "₹10,000",
        "₹2,000",
        "₹8,300",
        "- Electricity: ₹9 per kWh used, about ₹800 a month",
        "- Registration: ₹500 once",
        BRAND_NAME,
    ):
        assert fact in text, fact
    assert "{" not in text
    assert "}" not in text


def test_the_same_facts_make_the_same_text_byte_for_byte() -> None:
    first = render(_current(), TENANCY, brand=BRAND_NAME)

    assert render(_current(), replace(TENANCY), brand=BRAND_NAME) == first
    assert text_sha256(first) == hashlib.sha256(first.encode()).hexdigest()
    assert render(_current(), replace(TENANCY, room="102"), brand=BRAND_NAME) != first


def test_a_missing_name_shows_and_holds_up_signing() -> None:
    text = render(_current(), replace(TENANCY, licensee=None), brand=BRAND_NAME)

    assert NAME_MISSING in text
    assert missing(replace(TENANCY, licensee=None)) == ["the student's name"]
    assert missing(TENANCY) == []


def test_what_people_typed_cant_turn_into_markdown() -> None:
    text = render(
        "- {pg_name}\n- {licensee}",
        replace(TENANCY, pg_name="**Free** [rent](/ops)", licensee="Asha\n# Verma"),
        brand=BRAND_NAME,
    )

    assert text == "- Free (rent)(/ops)\n- Asha # Verma"


def test_no_charges_say_so() -> None:
    assert render("{charges}", replace(TENANCY, charges=()), brand=BRAND_NAME) == "- None."


def test_a_template_with_a_blank_nothing_fills_is_refused() -> None:
    with pytest.raises(TemplateError, match="unknown_blank"):
        render("Hello {unknown_blank}", TENANCY, brand=BRAND_NAME)


def test_dates_are_written_out() -> None:
    assert spoken_day(date(2027, 1, 5)) == "5 January 2027"


def test_every_template_on_file_is_pinned_fills_every_blank_and_says_draft_while_one() -> None:
    files = sorted(TEMPLATES_DIR.glob("*.md"))

    assert {path.stem for path in files} == set(PINNED)
    for path in files:
        assert VERSION_PATTERN.fullmatch(path.stem)
        content = path.read_bytes()
        assert hashlib.sha256(content).hexdigest() == PINNED[path.stem], (
            f"{path.name} changed: publish a new version instead"
        )
        template = content.decode()
        render(template, TENANCY, brand=BRAND_NAME)
        assert blanks(template) >= {"licensor", "licensee", "pg_address", "monthly_rent"}
        if is_draft(path.stem):
            assert "**DRAFT" in template.splitlines()[2]


def test_the_template_in_force_is_on_file() -> None:
    assert Templates().version == CURRENT_VERSION
    with pytest.raises(LookupError):
        Templates(FixedTemplates(), version="v9")


def test_templates_are_read_only_from_their_own_files(tmp_path: Path) -> None:
    (tmp_path / "v1.md").write_text("Agreed: {licensee}.")

    assert FileTemplates(tmp_path).get("v1") == "Agreed: {licensee}."
    assert FileTemplates(tmp_path).get("../v1") is None
    assert FileTemplates(tmp_path).get("v2") is None


def test_production_refuses_to_start_on_a_draft_rent_agreement(
    make_settings: Callable[..., Settings],
) -> None:
    production = {
        "app_env": "production",
        "cors_allowed_origins": ("https://www.example.in",),
        "site_url": "https://www.example.in",
        "api_url": "https://api.example.in",
        "media_public_base_url": "https://media.example.in",
        "privacy_notice_version": "2027-01",
        "owner_agreement_version": "2027-01",
        "otp_sender": "unavailable",
        "payment_gateway": "razorpay",
        "razorpay_key_id": "rzp_live_abc",
        "razorpay_key_secret": "a-razorpay-secret",
        "razorpay_webhook_secret": "a-razorpay-webhook-secret",
        "invoice_seller_name": "Fictional Stays Private Limited",
        "invoice_seller_address": "1 A Fictional Road, New Delhi",
        "invoice_seller_gstin": "00ABCDE0000F0Z0",
        "invoice_sac_code": "0000",
        "turnstile_secret_key": "test-turnstile-secret",
        "revalidate_secret": "a-revalidation-secret-of-32-chars!!",
        "text_sender": "unavailable",
        "mail_sender": "unavailable",
        "field_encryption_keys": "k1:" + "A" * 43,
    }
    owners = FixedAgreements(Agreement("2027-01", "A fictional reviewed agreement."))
    with pytest.raises(RuntimeError, match="rent agreement's template draft-1 is a draft"):
        create_app(make_settings(**production), agreements=owners)

    reviewed = Templates(FixedTemplates(("2027-01", "Agreed: {licensee}.")), version="2027-01")
    create_app(make_settings(**production), agreements=owners, rent_templates=reviewed)


class RecordedMailer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to: str, subject: str, text: str) -> None:
        self.sent.append((to, subject, text))


def test_a_signing_code_goes_by_email_through_the_sites_mailer() -> None:
    mailer = RecordedMailer()
    codes = MailSigningCodes(mailer, shows_code=False, site_url="https://www.example.in")

    asyncio.run(codes.send("asha@example.com", "123456"))

    [(to, subject, text)] = mailer.sent
    assert to == "asha@example.com"
    assert BRAND_NAME in subject
    assert "123456" in text
    assert "10 minutes" in text
    assert "https://www.example.in" in text


def test_without_a_mailer_codes_show_on_a_test_site_and_go_nowhere_else() -> None:
    shown = MailSigningCodes(None, shows_code=True, site_url="https://test.example.in")
    asyncio.run(shown.send("asha@example.com", "123456"))

    off = MailSigningCodes(None, shows_code=False, site_url="https://www.example.in")
    with pytest.raises(ServiceUnavailableError):
        asyncio.run(off.send("asha@example.com", "123456"))


@pytest.mark.parametrize(
    ("mail_sender", "shows_code", "expected"),
    [("console", False, True), ("unavailable", True, True), ("unavailable", False, False)],
)
def test_signing_codes_go_the_way_sign_in_codes_do(
    make_settings: Callable[..., Settings], mail_sender: str, shows_code: bool, expected: bool
) -> None:
    sender = signing_codes(make_settings(mail_sender=mail_sender), shows_code=shows_code)

    assert sender.shows_code is expected
