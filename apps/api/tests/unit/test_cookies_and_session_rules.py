from datetime import UTC, datetime, timedelta

import pytest
from starlette.responses import Response

from app.core.cookies import SESSION_COOKIE, CookiePolicy
from app.modules.identity.domain.sessions import (
    POLICIES,
    SessionKind,
    absolute_expiry,
    is_due_for_touch,
    sliding_expiry,
)

NOW = datetime(2027, 7, 14, 10, 0, tzinfo=UTC)


def _attributes(set_cookie: str) -> dict[str, str]:
    name_value, *attributes = (part.strip() for part in set_cookie.split(";"))
    parsed = {"cookie": name_value}
    for attribute in attributes:
        key, _, value = attribute.partition("=")
        parsed[key.lower()] = value
    return parsed


def test_cookies_are_secure_httponly_when_asked_lax_and_site_wide() -> None:
    response = Response()

    CookiePolicy().set(response, SESSION_COOKIE, "token-value", max_age=3600, http_only=True)

    attributes = _attributes(response.headers["set-cookie"])
    assert attributes["cookie"] == f"{SESSION_COOKIE}=token-value"
    assert {"secure", "httponly"} <= attributes.keys()
    assert attributes["samesite"].lower() == "lax"
    assert attributes["path"] == "/"
    assert attributes["max-age"] == "3600"
    assert "domain" not in attributes


def test_the_parent_domain_is_set_when_configured_and_scripts_may_read_csrf_cookies() -> None:
    response = Response()

    CookiePolicy(domain=".example.test").set(
        response, "__Secure-csrf", "token", max_age=60, http_only=False
    )

    attributes = _attributes(response.headers["set-cookie"])
    assert attributes["domain"] == ".example.test"
    assert "httponly" not in attributes
    assert "secure" in attributes


def test_clearing_a_cookie_expires_it_with_the_same_attributes() -> None:
    response = Response()

    CookiePolicy(domain=".example.test").clear(response, SESSION_COOKIE, http_only=True)

    attributes = _attributes(response.headers["set-cookie"])
    assert attributes["cookie"] == f'{SESSION_COOKIE}=""'
    assert attributes["max-age"] == "0"
    assert attributes["domain"] == ".example.test"
    assert {"secure", "httponly"} <= attributes.keys()


def test_user_sessions_slide_30_days_from_the_last_activity() -> None:
    policy = POLICIES[SessionKind.USER]

    assert absolute_expiry(policy, started_at=NOW) is None
    assert sliding_expiry(policy, now=NOW, absolute_expires_at=None) == NOW + timedelta(days=30)


def test_staff_sessions_never_outlive_12_hours_from_sign_in() -> None:
    policy = POLICIES[SessionKind.STAFF]
    absolute = absolute_expiry(policy, started_at=NOW)

    assert absolute == NOW + timedelta(hours=12)
    later = NOW + timedelta(hours=8)
    assert sliding_expiry(policy, now=later, absolute_expires_at=absolute) == absolute


@pytest.mark.parametrize(
    ("since_last_seen", "due"),
    [(timedelta(minutes=9, seconds=59), False), (timedelta(minutes=10), True)],
)
def test_activity_moves_the_expiry_at_most_every_10_minutes(
    since_last_seen: timedelta, due: bool
) -> None:
    policy = POLICIES[SessionKind.USER]

    assert is_due_for_touch(policy, now=NOW, last_seen_at=NOW - since_last_seen) is due
