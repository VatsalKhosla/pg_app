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

from app.config import Settings
from app.modules.catalog.agreements import FileAgreements
from tests.conftest import NOTICE_VERSION

# The owner agreement the API runs with in tests: the settings' default.
AGREEMENT_VERSION: Final = Settings.model_fields["owner_agreement_version"].default

# A time a student may offer, a day after the clock the test runs at: 11 am in India.
VISIT_START: Final = "2027-07-15T05:30:00Z"

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
        "someone_elses_media",
        "a_listing",
        "a_room_category",
        "a_room",
        "a_bed",
        "someone_elses_visit",
        "someone_elses_student_visit",
        "someone_elses_grievance",
        "a_missing_rent_band",
        "a_draft_rule_set",
        "a_draft_rule",
        "a_missing_quote",
        "a_missing_alert",
        "a_missing_block",
        "a_missing_booking",
        "an_owner",
        "a_live_listing",
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


def ops_only(status: int) -> dict[str, int]:
    """Ops and admins, in a staff session; 403 for anyone else signed in."""
    return signed_in(403, ops=status, admin=status)


def _new_owner() -> dict[str, Any]:
    return {
        "json": {
            "phone": _new_mobile(),
            "legalName": "Fictional Stays Private Limited",
            "businessName": "Fictional Stays",
        }
    }


def _acceptance() -> dict[str, Any]:
    agreement = FileAgreements().get(AGREEMENT_VERSION)
    assert agreement is not None
    return {"json": {"version": agreement.version, "documentSha256": agreement.sha256}}


def _new_listing() -> dict[str, Any]:
    # The owner doesn't exist, so staff get 404 here; the catalog tests create real listings.
    return {
        "json": {
            "owner": str(uuid.uuid7()),
            "locality": "kamla-nagar",
            "name": "Fictional Residency",
            "addressLine": "House 1, a fictional lane",
            "location": {"lat": 28.68, "lng": 77.2},
            "locationPrecision": "exact",
            "genderPolicy": "girls",
            "meals": "two",
        }
    }


def _visit_booking() -> dict[str, Any]:
    # Nobody is a field agent by that id, so ops get 422; the verification tests book real ones.
    return {"json": {"agent": str(uuid.uuid7()), "scheduledFor": "2027-07-14T10:00:00+00:00"}}


def _visit_report() -> dict[str, Any]:
    # A report that would pass its checks: only whose visit it is decides the answer.
    return {
        "json": {
            "checklist": {
                "buildingAgeYears": None,
                "condition": "good",
                "cracks": "none",
                "exits": 2,
                "fireExtinguishers": True,
                "cctv": True,
                "warden": True,
                "womenSafety": [],
                "licenceNumber": None,
                "societyPermission": "n/a",
                "authorityNotice": False,
            },
            "result": "passed",
            "position": {"lat": 28.68, "lng": 77.2},
            "accuracyM": 10,
            "photos": [str(uuid.uuid7())],
        }
    }


def _reason() -> dict[str, Any]:
    return {"json": {"reason": "A fictional reason"}}


# The defaults in force: sending them again changes nothing (422), yet shows who may.
FEE_IN_FORCE: Final = {"rateBps": 3000, "gstRateBps": 1800, "gstMode": "exclusive"}
BOOKING_IN_FORCE: Final = {
    "tokenPaise": 200000,
    "holdMinutes": 15,
    "freeCancelDays": 7,
    "checkWindowHours": 24,
    "confirmDeadlineHours": 12,
    "noShowDays": 3,
    "lateCancelPolicy": "refund_full",
    "maxActiveHoldsPerUser": 1,
    "maxAdvanceDays": 120,
}
CAPS_IN_FORCE: Final = {"maxPremiumBps": 4000, "maxDiscountBps": 3000, "roundingStepPaise": 5000}


def _a_rule() -> dict[str, Any]:
    return {
        "json": {
            "label": "Long stay",
            "params": {"kind": "length_of_stay", "tiers": [{"minMonths": 6, "bps": -300}]},
        }
    }


def _complaint() -> dict[str, Any]:
    # Signed in, the account is the contact and the name and phone sent are ignored.
    return {
        "json": {
            "category": "other",
            "details": "Checking who may complain.",
            "name": "A fictional complainant",
            "phone": _new_mobile(),
            "humanCheckToken": "token",
        }
    }


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
    # Media uploads: staff in a staff session, for now. Someone else's file is a 404, though ops
    # and admins may look at any.
    ("POST", "/v1/media"): Rule(
        signed_in(403, field_agent=201, ops=201, admin=201),
        lambda: {
            "json": {"purpose": "listing_photo", "contentType": "image/jpeg", "byteSize": 1_000}
        },
    ),
    ("POST", "/v1/media/{media_id}/uploaded"): Rule(
        signed_in(404), path={"media_id": "someone_elses_media"}
    ),
    ("GET", "/v1/media/{media_id}"): Rule(
        signed_in(404, ops=200, admin=200), path={"media_id": "someone_elses_media"}
    ),
    # The catalog: amenities and live listings for everyone; listings in full for ops and admins.
    ("GET", "/v1/amenities"): Rule(everyone(200)),
    ("GET", "/v1/properties/{slug}"): Rule(everyone(200), path={"slug": "a_live_listing"}),
    ("GET", "/v1/search/properties"): Rule(
        everyone(200), lambda: {"params": {"campus": "hindu-college", "sort": "distance"}}
    ),
    ("GET", "/v1/map/pins"): Rule(
        everyone(200), lambda: {"params": {"bbox": "77.15,28.65,77.25,28.72", "zoom": 13}}
    ),
    # Where the PGs are and every live one, for landing pages and the sitemap (ADR 0032).
    ("GET", "/v1/search/places"): Rule(everyone(200)),
    ("GET", "/v1/search/sitemap"): Rule(everyone(200)),
    # The owner's contact details (ADR 0026): with hide_owner_contact on, as by default, only for
    # someone with a visit or booking there, which nobody here has.
    ("GET", "/v1/properties/{slug}/contact"): Rule(signed_in(403), path={"slug": "a_live_listing"}),
    ("GET", "/v1/ops/owners"): Rule(ops_only(200)),
    ("POST", "/v1/ops/owners"): Rule(ops_only(201), _new_owner),
    ("GET", "/v1/ops/owners/{owner_id}"): Rule(ops_only(200), path={"owner_id": "an_owner"}),
    ("PATCH", "/v1/ops/owners/{owner_id}"): Rule(
        ops_only(200), lambda: {"json": {"businessName": "Renamed"}}, path={"owner_id": "an_owner"}
    ),
    ("GET", "/v1/ops/owners/{owner_id}/agreements"): Rule(
        ops_only(200), path={"owner_id": "an_owner"}
    ),
    # The owner area (ADR 0025): only an owner, signed in by phone, with a business record. The
    # owner caller has one; tests/integration/test_owners.py covers an owner without.
    ("GET", "/v1/owner/profile"): Rule(signed_in(403, owner=200)),
    ("GET", "/v1/owner/agreement"): Rule(signed_in(403, owner=200)),
    ("POST", "/v1/owner/agreement/acceptances"): Rule(signed_in(403, owner=201), _acceptance),
    ("GET", "/v1/ops/properties"): Rule(ops_only(200)),
    ("POST", "/v1/ops/properties"): Rule(ops_only(404), _new_listing),
    ("GET", "/v1/ops/properties/{property_id}"): Rule(
        ops_only(200), path={"property_id": "a_listing"}
    ),
    ("PATCH", "/v1/ops/properties/{property_id}"): Rule(
        ops_only(200), lambda: {"json": {"name": "Renamed"}}, path={"property_id": "a_listing"}
    ),
    ("POST", "/v1/ops/properties/{property_id}/status"): Rule(
        ops_only(200), lambda: {"json": {"status": "delisted"}}, path={"property_id": "a_listing"}
    ),
    ("PUT", "/v1/ops/properties/{property_id}/amenities"): Rule(
        ops_only(200), lambda: {"json": {"amenities": ["wifi"]}}, path={"property_id": "a_listing"}
    ),
    ("PUT", "/v1/ops/properties/{property_id}/media"): Rule(
        ops_only(200), lambda: {"json": {"media": []}}, path={"property_id": "a_listing"}
    ),
    ("GET", "/v1/ops/properties/{property_id}/history"): Rule(
        ops_only(200), path={"property_id": "a_listing"}
    ),
    ("POST", "/v1/ops/properties/{property_id}/room-categories"): Rule(
        ops_only(201),
        lambda: {
            "json": {
                "occupancy": "double",
                "label": "Double sharing",
                "baseRentPaise": 1_200_000,
                "securityDepositPaise": 1_200_000,
            }
        },
        path={"property_id": "a_listing"},
    ),
    ("PATCH", "/v1/ops/room-categories/{category_id}"): Rule(
        ops_only(200),
        lambda: {"json": {"label": "Renamed"}},
        path={"category_id": "a_room_category"},
    ),
    ("POST", "/v1/ops/room-categories/{category_id}/rooms"): Rule(
        ops_only(201),
        lambda: {"json": {"label": "101", "beds": 2}},
        path={"category_id": "a_room_category"},
    ),
    ("POST", "/v1/ops/rooms/{room_id}/beds"): Rule(
        ops_only(201), lambda: {"json": {"label": "A"}}, path={"room_id": "a_room"}
    ),
    ("PATCH", "/v1/ops/beds/{bed_id}"): Rule(
        ops_only(200), lambda: {"json": {"status": "inactive"}}, path={"bed_id": "a_bed"}
    ),
    # Verification (ADR 0024): ops book and cancel, field agents report on their own visits.
    ("GET", "/v1/ops/field-agents"): Rule(ops_only(200)),
    ("POST", "/v1/ops/properties/{property_id}/verification-visits"): Rule(
        ops_only(422), _visit_booking, path={"property_id": "a_listing"}
    ),
    ("GET", "/v1/ops/properties/{property_id}/verification-visits"): Rule(
        ops_only(200), path={"property_id": "a_listing"}
    ),
    ("GET", "/v1/ops/verification-visits"): Rule(
        signed_in(403, field_agent=200, ops=200, admin=200)
    ),
    # Another agent's visit doesn't exist for a field agent.
    ("GET", "/v1/ops/verification-visits/{visit_id}"): Rule(
        signed_in(403, field_agent=404, ops=200, admin=200),
        path={"visit_id": "someone_elses_visit"},
    ),
    ("POST", "/v1/ops/verification-visits/{visit_id}/report"): Rule(
        signed_in(403, field_agent=404), _visit_report, path={"visit_id": "someone_elses_visit"}
    ),
    ("POST", "/v1/ops/verification-visits/{visit_id}/cancel"): Rule(
        ops_only(200), _reason, path={"visit_id": "someone_elses_visit"}
    ),
    # Grievances (ADR 0034): anyone complains, signed in or not; the grievance officer's team
    # (ops and admins) works the queue. The grievance is a fresh one from someone else.
    ("POST", "/v1/grievances"): Rule(everyone(201), _complaint),
    ("GET", "/v1/me/grievances"): Rule(signed_in(200)),
    ("GET", "/v1/ops/grievances"): Rule(signed_in(403, ops=200, admin=200)),
    ("GET", "/v1/ops/grievances/{ticket_number}"): Rule(
        signed_in(403, ops=200, admin=200), path={"ticket_number": "someone_elses_grievance"}
    ),
    ("POST", "/v1/ops/grievances/{ticket_number}/acknowledge"): Rule(
        signed_in(403, ops=200, admin=200),
        lambda: {"json": {"reply": "Checking who may reply."}},
        path={"ticket_number": "someone_elses_grievance"},
    ),
    ("POST", "/v1/ops/grievances/{ticket_number}/resolve"): Rule(
        signed_in(403, ops=200, admin=200),
        lambda: {"json": {"resolution": "Checking who may resolve grievances."}},
        path={"ticket_number": "someone_elses_grievance"},
    ),
    # The fee and booking terms in force, for the public pages (ADR 0034).
    ("GET", "/v1/policies"): Rule(everyone(200)),
    # Policies, caps and rent bands (ADR 0036): admins' alone. No call here changes them: the
    # policies sent are those in force (422), the locality doesn't exist (422), nor the band.
    ("GET", "/v1/admin/policies"): Rule(signed_in(403, admin=200)),
    ("GET", "/v1/admin/policies/history"): Rule(signed_in(403, admin=200)),
    ("POST", "/v1/admin/policies/fee"): Rule(
        signed_in(403, admin=422), lambda: {"json": FEE_IN_FORCE}
    ),
    ("POST", "/v1/admin/policies/booking"): Rule(
        signed_in(403, admin=422), lambda: {"json": BOOKING_IN_FORCE}
    ),
    ("POST", "/v1/admin/policies/caps"): Rule(
        signed_in(403, admin=422), lambda: {"json": CAPS_IN_FORCE}
    ),
    ("GET", "/v1/admin/rent-bands"): Rule(signed_in(403, admin=200)),
    ("POST", "/v1/admin/rent-bands"): Rule(
        signed_in(403, admin=422),
        lambda: {
            "json": {
                "locality": "no-such-locality-for-the-matrix",
                "occupancy": "double",
                "minRentPaise": 800000,
                "maxRentPaise": 1400000,
                "source": "internal",
            }
        },
    ),
    ("POST", "/v1/admin/rent-bands/{band_id}/end"): Rule(
        signed_in(403, admin=404), lambda: {"json": {}}, path={"band_id": "a_missing_rent_band"}
    ),
    # Quotes (ADR 0039): anyone may ask, and read one by its id. No room has the id sent.
    ("POST", "/v1/quotes"): Rule(
        everyone(404),
        lambda: {
            "json": {"roomCategory": str(uuid.uuid7()), "moveIn": "2027-08-20", "stayMonths": 11}
        },
    ),
    ("GET", "/v1/quotes/{quote_id}"): Rule(everyone(404), path={"quote_id": "a_missing_quote"}),
    # The price calendar (ADR 0040): anyone, for a PG the public may see.
    ("GET", "/v1/properties/{slug}/price-calendar"): Rule(
        everyone(200), path={"slug": "a_live_listing"}
    ),
    # A PG's pricing rule sets (ADR 0038): ops and admins, on a fresh listing's own draft.
    ("GET", "/v1/ops/properties/{property_id}/rule-sets"): Rule(
        ops_only(200), path={"property_id": "a_listing"}
    ),
    ("POST", "/v1/ops/properties/{property_id}/rule-sets/draft"): Rule(
        ops_only(200), path={"property_id": "a_listing"}
    ),
    ("GET", "/v1/ops/rule-sets/{rule_set_id}"): Rule(
        ops_only(200), path={"rule_set_id": "a_draft_rule_set"}
    ),
    ("POST", "/v1/ops/rule-sets/{rule_set_id}/rules"): Rule(
        ops_only(201), _a_rule, path={"rule_set_id": "a_draft_rule_set"}
    ),
    ("PUT", "/v1/ops/rules/{rule_id}"): Rule(
        ops_only(200), _a_rule, path={"rule_id": "a_draft_rule"}
    ),
    ("DELETE", "/v1/ops/rules/{rule_id}"): Rule(ops_only(200), path={"rule_id": "a_draft_rule"}),
    ("POST", "/v1/ops/rule-sets/{rule_set_id}/activate"): Rule(
        ops_only(200), lambda: {"json": {}}, path={"rule_set_id": "a_draft_rule_set"}
    ),
    ("DELETE", "/v1/ops/rule-sets/{rule_set_id}"): Rule(
        ops_only(204), path={"rule_set_id": "a_draft_rule_set"}
    ),
    # The pricing editor (ADR 0041): ops and admins. The draft's PG has no room with the id sent.
    ("GET", "/v1/ops/rule-sets/{rule_set_id}/preview"): Rule(
        ops_only(404),
        lambda: {"params": {"room": str(uuid.uuid7()), "moveIn": "2027-01-10", "stay": 11}},
        path={"rule_set_id": "a_draft_rule_set"},
    ),
    ("GET", "/v1/ops/rule-sets/{rule_set_id}/calendar"): Rule(
        ops_only(200), path={"rule_set_id": "a_draft_rule_set"}
    ),
    ("GET", "/v1/ops/properties/{property_id}/market"): Rule(
        ops_only(200), path={"property_id": "a_listing"}
    ),
    # Inventory (ADR 0044): ops and admins; each call blocks a fresh listing's bed. No block has
    # the id sent to end.
    ("GET", "/v1/ops/properties/{property_id}/inventory"): Rule(
        ops_only(200), path={"property_id": "a_listing"}
    ),
    ("POST", "/v1/ops/beds/{bed_id}/blocks"): Rule(
        ops_only(201),
        lambda: {"json": {"kind": "maintenance", "start": "2027-08-01", "end": "2027-08-05"}},
        path={"bed_id": "a_bed"},
    ),
    ("POST", "/v1/ops/blocks/{block_id}/end"): Rule(
        ops_only(404), lambda: {"json": {"on": "2027-08-03"}}, path={"block_id": "a_missing_block"}
    ),
    # Pricing's integrity alerts (ADR 0043): ops and admins. No alert has the id sent.
    ("GET", "/v1/ops/pricing-alerts"): Rule(ops_only(200)),
    ("POST", "/v1/ops/pricing-alerts/{alert_id}/resolve"): Rule(
        ops_only(404), lambda: {"json": {}}, path={"alert_id": "a_missing_alert"}
    ),
    # Bookings (ADR 0046): people signed in by phone hold beds with their own quotes and see their
    # own bookings; staff sessions don't. A hold without an Idempotency-Key is refused before
    # anything else, and the booking asked for is nobody's.
    ("POST", "/v1/bookings"): Rule(
        signed_in(400, field_agent=403, ops=403, admin=403),
        lambda: {"json": {"quote": str(uuid.uuid7())}},
    ),
    ("GET", "/v1/bookings/{code}"): Rule(
        signed_in(404, field_agent=403, ops=403, admin=403), path={"code": "a_missing_booking"}
    ),
    ("GET", "/v1/bookings"): Rule(signed_in(200, field_agent=403, ops=403, admin=403)),
    ("POST", "/v1/bookings/{code}/cancel"): Rule(
        signed_in(404, field_agent=403, ops=403, admin=403),
        lambda: {"json": {"refundPaise": 0}},
        path={"code": "a_missing_booking"},
    ),
    # Moving in (ADR 0050): the student says so on their own booking.
    ("POST", "/v1/bookings/{code}/check-in"): Rule(
        signed_in(404, field_agent=403, ops=403, admin=403), path={"code": "a_missing_booking"}
    ),
    # Answering bookings (ADR 0048): an owner answers their own PGs' bookings, and ops answer any.
    # The booking asked for is nobody's.
    ("GET", "/v1/owner/bookings/{code}"): Rule(
        signed_in(403, owner=404), path={"code": "a_missing_booking"}
    ),
    ("POST", "/v1/owner/bookings/{code}/confirm"): Rule(
        signed_in(403, owner=404), path={"code": "a_missing_booking"}
    ),
    ("POST", "/v1/owner/bookings/{code}/reject"): Rule(
        signed_in(403, owner=404),
        lambda: {"json": {"reason": "The room is under repair"}},
        path={"code": "a_missing_booking"},
    ),
    ("GET", "/v1/ops/bookings/{code}"): Rule(ops_only(404), path={"code": "a_missing_booking"}),
    ("POST", "/v1/ops/bookings/{code}/confirm"): Rule(
        ops_only(404), path={"code": "a_missing_booking"}
    ),
    ("POST", "/v1/ops/bookings/{code}/reject"): Rule(
        ops_only(404),
        lambda: {"json": {"reason": "The room is under repair"}},
        path={"code": "a_missing_booking"},
    ),
    ("POST", "/v1/ops/bookings/{code}/move-in-reminder"): Rule(
        ops_only(404), path={"code": "a_missing_booking"}
    ),
    # Student visits (ADR 0033): people signed in by phone ask and cancel their own; ops book and
    # cancel any; field agents run the ones booked for them. The visit is another student's, booked
    # with another agent, so it doesn't exist for any phone caller or field agent here.
    ("POST", "/v1/visits"): Rule(
        signed_in(404, field_agent=403, ops=403, admin=403),
        lambda: {"json": {"property": "no-such-pg-for-the-matrix", "starts": [VISIT_START]}},
    ),
    ("GET", "/v1/visits"): Rule(signed_in(200, field_agent=403, ops=403, admin=403)),
    ("POST", "/v1/visits/{visit_id}/cancel"): Rule(
        signed_in(404, field_agent=403, ops=403, admin=403),
        path={"visit_id": "someone_elses_student_visit"},
    ),
    ("GET", "/v1/ops/visits"): Rule(ops_only(200)),
    ("GET", "/v1/ops/visits/{visit_id}"): Rule(
        ops_only(200), path={"visit_id": "someone_elses_student_visit"}
    ),
    # No field agent has the id sent.
    ("POST", "/v1/ops/visits/{visit_id}/schedule"): Rule(
        ops_only(422),
        lambda: {"json": {"at": VISIT_START, "agent": str(uuid.uuid7())}},
        path={"visit_id": "someone_elses_student_visit"},
    ),
    ("POST", "/v1/ops/visits/{visit_id}/cancel"): Rule(
        ops_only(200), _reason, path={"visit_id": "someone_elses_student_visit"}
    ),
    ("GET", "/v1/field/visits"): Rule(signed_in(403, field_agent=200)),
    ("GET", "/v1/field/visits/{visit_id}"): Rule(
        signed_in(403, field_agent=404), path={"visit_id": "someone_elses_student_visit"}
    ),
    ("POST", "/v1/field/visits/{visit_id}/check-in"): Rule(
        signed_in(403, field_agent=404),
        lambda: {"json": {"position": {"lat": 28.68, "lng": 77.2}, "accuracyM": 10}},
        path={"visit_id": "someone_elses_student_visit"},
    ),
    ("POST", "/v1/field/visits/{visit_id}/outcome"): Rule(
        signed_in(403, field_agent=404),
        lambda: {"json": {"outcome": "interested"}},
        path={"visit_id": "someone_elses_student_visit"},
    ),
    # A new listing isn't verified yet, so there is nothing to suspend.
    ("POST", "/v1/ops/properties/{property_id}/verification/suspend"): Rule(
        ops_only(409), _reason, path={"property_id": "a_listing"}
    ),
}


def api_routes(app: FastAPI) -> set[tuple[str, str]]:
    """Every (method, path) the app serves. FastAPI keeps included routers nested, so this walks
    their effective routes as its OpenAPI generator does."""
    routes: set[tuple[str, str]] = set()
    for route in iter_route_contexts(app.routes):
        if isinstance(route.original_route, APIRoute) and route.path is not None:
            routes.update((method, route.path) for method in route.methods or ())
    return routes
