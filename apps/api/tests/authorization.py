"""The authorization matrix (ARCHITECTURE §12): every route of the API, every kind of caller, and
the status each one gets.

It is written out by hand, apart from the routes themselves, so that changing who may call a route
means changing this table in the same review. tests/unit/test_authorization_coverage.py fails when
a route has no entry here, or an entry has no route; tests/integration/test_authorization_matrix.py
calls every route as every caller and compares.

Each entry says what fills its path parameters, from PATH_VALUES, made afresh for every call.
Records are someone else's, so a route about one record must answer 404 to anyone but its owner,
rather than reveal that it exists.
"""

import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final

from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts

from tests.conftest import NOTICE_VERSION

# Who calls: nobody signed in; people signed in by phone (an admin's phone session carries no staff
# roles); staff in staff sessions.
CALLERS: Final = (
    "anonymous",
    "student",
    "parent",
    "owner",
    "admin_by_phone",
    "field_agent",
    "ops",
    "admin",
)
# What the integration test can fill a path parameter with.
PATH_VALUES: Final = frozenset(
    {
        "someone_elses_session",
        "someone_elses_export",
        "someone_elses_deletion_request",
        "an_optional_purpose",
        "a_campus",
    }
)


def everyone(status: int) -> dict[str, int]:
    return dict.fromkeys(CALLERS, status)


def signed_in(status: int, **exceptions: int) -> dict[str, int]:
    """401 without a session; ``status`` for every signed-in caller, apart from ``exceptions``."""
    return {"anonymous": 401, **dict.fromkeys(CALLERS[1:], status), **exceptions}


def _new_mobile() -> str:
    return str(6_000_000_000 + secrets.randbelow(4_000_000_000))


def _nothing() -> dict[str, Any]:
    return {}


@dataclass(frozen=True)
class Rule:
    expected: dict[str, int]
    # The request's body or query, made afresh for every call.
    request: Callable[[], dict[str, Any]] = _nothing
    # What fills each path parameter (one of PATH_VALUES).
    path: dict[str, str] = field(default_factory=dict)


MATRIX: Final[dict[tuple[str, str], Rule]] = {
    # Probes.
    ("GET", "/healthz"): Rule(everyone(200)),
    ("GET", "/readyz"): Rule(everyone(200)),
    # Signing in and out.
    ("GET", "/v1/auth/csrf"): Rule(everyone(200)),
    ("POST", "/v1/auth/otp/request"): Rule(
        everyone(202), lambda: {"json": {"phone": _new_mobile(), "humanCheckToken": "token"}}
    ),
    # A challenge nobody asked for: refused alike, whoever asks.
    ("POST", "/v1/auth/otp/verify"): Rule(
        everyone(400), lambda: {"json": {"challengeId": str(uuid.uuid7()), "code": "123456"}}
    ),
    # Google sign-in isn't set up here: both redirect to the staff sign-in page with an error.
    ("GET", "/v1/auth/staff/google"): Rule(everyone(303)),
    ("GET", "/v1/auth/staff/google/callback"): Rule(
        everyone(303), lambda: {"params": {"code": "code", "state": "state"}}
    ),
    # Nobody here has an authenticator app, so even staff are refused.
    ("POST", "/v1/auth/staff/totp"): Rule(signed_in(403), lambda: {"json": {"code": "123456"}}),
    ("POST", "/v1/auth/logout"): Rule(everyone(204)),
    ("POST", "/v1/auth/logout-everywhere"): Rule(signed_in(204)),
    # The signed-in account.
    ("GET", "/v1/me"): Rule(signed_in(200)),
    ("PATCH", "/v1/me"): Rule(
        signed_in(200), lambda: {"json": {"collegeOrWorkplace": "A college"}}
    ),
    ("GET", "/v1/me/sessions"): Rule(signed_in(200)),
    ("DELETE", "/v1/me/sessions/{session_id}"): Rule(
        signed_in(404), path={"session_id": "someone_elses_session"}
    ),
    # Consent.
    ("GET", "/v1/privacy-notice"): Rule(everyone(200)),
    ("GET", "/v1/me/consents"): Rule(signed_in(200)),
    ("POST", "/v1/me/consents"): Rule(
        signed_in(200),
        lambda: {"json": {"noticeVersion": NOTICE_VERSION, "purposes": ["marketing"]}},
    ),
    ("DELETE", "/v1/me/consents/{purpose}"): Rule(
        signed_in(204), path={"purpose": "an_optional_purpose"}
    ),
    # Data requests: people's own, and the ops queue.
    ("POST", "/v1/me/data-requests"): Rule(signed_in(202), lambda: {"json": {"kind": "export"}}),
    ("GET", "/v1/me/data-requests"): Rule(signed_in(200)),
    ("GET", "/v1/me/data-requests/{request_id}/file"): Rule(
        signed_in(404), path={"request_id": "someone_elses_export"}
    ),
    ("GET", "/v1/ops/data-requests"): Rule(signed_in(403, ops=200, admin=200)),
    ("POST", "/v1/ops/data-requests/{request_id}/resolve"): Rule(
        signed_in(403, ops=200, admin=200),
        lambda: {"json": {"outcome": "rejected", "note": "Checking who may resolve requests."}},
        path={"request_id": "someone_elses_deletion_request"},
    ),
    # Admins, in a staff session.
    ("GET", "/v1/admin/staff"): Rule(signed_in(403, admin=200)),
    # Geo reference data: public.
    ("GET", "/v1/cities"): Rule(everyone(200)),
    ("GET", "/v1/localities"): Rule(everyone(200)),
    ("GET", "/v1/campuses"): Rule(everyone(200)),
    ("GET", "/v1/campuses/{slug}"): Rule(everyone(200), path={"slug": "a_campus"}),
    ("GET", "/v1/metro-stations"): Rule(everyone(200)),
}


def api_routes(app: FastAPI) -> set[tuple[str, str]]:
    """Every (method, path) the app serves. FastAPI keeps included routers nested, so this walks
    their effective routes as its OpenAPI generator does."""
    routes: set[tuple[str, str]] = set()
    for route in iter_route_contexts(app.routes):
        if isinstance(route.original_route, APIRoute) and route.path is not None:
            routes.update((method, route.path) for method in route.methods or ())
    return routes
