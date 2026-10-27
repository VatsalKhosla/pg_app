import pytest

from app.modules.compliance.domain.requests import (
    DataRequestKind,
    DataRequestStatus,
    can_move,
    is_open,
)
from app.modules.identity.domain.consent import (
    ConsentPurpose,
    has_agreed,
    is_current,
    missing_required,
)

ACCOUNT, MARKETING = ConsentPurpose.ACCOUNT, ConsentPurpose.MARKETING
EXPORT, DELETION = DataRequestKind.EXPORT, DataRequestKind.DELETION
S = DataRequestStatus


def test_an_account_needs_its_own_purpose_and_nothing_else() -> None:
    assert missing_required(frozenset()) == {ACCOUNT}
    assert missing_required(frozenset({MARKETING})) == {ACCOUNT}
    assert missing_required(frozenset({ACCOUNT})) == frozenset()


def test_consent_is_current_only_for_the_current_notice() -> None:
    assert is_current(frozenset({(ACCOUNT, "2027-01")}), notice_version="2027-01")
    assert not is_current(frozenset({(ACCOUNT, "2026-10")}), notice_version="2027-01")
    assert not is_current(frozenset({(MARKETING, "2027-01")}), notice_version="2027-01")
    assert is_current(
        frozenset({(ACCOUNT, "2026-10"), (ACCOUNT, "2027-01")}), notice_version="2027-01"
    )


def test_someone_has_agreed_once_the_account_purpose_is_given_under_any_notice() -> None:
    assert has_agreed(frozenset({(ACCOUNT, "2026-10")}))
    # An account ops made for someone, before they've signed in.
    assert not has_agreed(frozenset())
    assert not has_agreed(frozenset({(MARKETING, "2027-01")}))


@pytest.mark.parametrize(
    ("kind", "current", "allowed"),
    [
        (EXPORT, S.RECEIVED, {S.READY}),
        (EXPORT, S.READY, {S.EXPIRED}),
        (EXPORT, S.EXPIRED, set()),
        (DELETION, S.RECEIVED, {S.COMPLETED, S.REJECTED}),
        (DELETION, S.COMPLETED, set()),
        (DELETION, S.REJECTED, set()),
    ],
)
def test_requests_move_only_forward_and_only_their_own_way(
    kind: DataRequestKind, current: DataRequestStatus, allowed: set[DataRequestStatus]
) -> None:
    assert {target for target in DataRequestStatus if can_move(kind, current, target)} == allowed


def test_only_received_requests_are_open() -> None:
    assert [status for status in DataRequestStatus if is_open(status)] == [S.RECEIVED]
