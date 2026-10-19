from hypothesis import given
from hypothesis import strategies as st

from app.modules.identity.domain.staff import GoogleAccount, google_account_allowed

DOMAINS = frozenset({"example.in"})
EMAILS = frozenset({"founder@gmail.com"})


def _allowed(*, email: str, hosted_domain: str | None, verified: bool = True) -> bool:
    account = GoogleAccount(
        subject="110169484474386276334",
        email=email,
        email_verified=verified,
        hosted_domain=hosted_domain,
    )
    return google_account_allowed(account, domains=DOMAINS, emails=EMAILS)


def test_accounts_of_an_allowed_workspace_domain_are_allowed() -> None:
    assert _allowed(email="ops@example.in", hosted_domain="example.in")
    assert _allowed(email="ops@example.in", hosted_domain="Example.IN")


def test_an_address_at_the_domain_is_not_enough_without_the_workspace_claim() -> None:
    # Anyone can make a personal Google account with an address at the company's domain.
    assert not _allowed(email="ops@example.in", hosted_domain=None)


def test_an_allowed_address_is_allowed_without_a_workspace() -> None:
    assert _allowed(email="Founder@Gmail.com", hosted_domain=None)


def test_an_unverified_address_is_never_allowed() -> None:
    assert not _allowed(email="founder@gmail.com", hosted_domain=None, verified=False)
    assert not _allowed(email="ops@example.in", hosted_domain="example.in", verified=False)


def test_another_workspace_domain_is_refused() -> None:
    assert not _allowed(email="ops@other.in", hosted_domain="other.in")


@given(st.emails(), st.sampled_from([None, "other.in", "example.com", "notexample.in"]))
def test_nobody_outside_the_allowed_domains_and_addresses_gets_in(
    email: str, hosted_domain: str | None
) -> None:
    if email.lower() not in EMAILS:
        assert not _allowed(email=email, hosted_domain=hosted_domain)
