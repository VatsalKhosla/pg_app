"""Every route called by every kind of caller, as tests/authorization.py says (step 1.4).

The app runs against PostgreSQL and Valkey. Each call gets a fresh session for its caller (some
routes end it), a valid CSRF token, and someone else's records in its path.
"""

import asyncio
import secrets
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Final

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update

from app.config import Settings
from app.core.actor import Actor, Role
from app.core.clock import FrozenClock
from app.core.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from app.core.csrf import issue_csrf_token
from app.core.ids import new_ticket_number
from app.core.money import Paise
from app.main import create_app
from app.modules.catalog.domain.listing import (
    GenderPolicy,
    LocationPrecision,
    Meals,
    PropertyStatus,
    VerificationStatus,
)
from app.modules.catalog.domain.location import Offset, moved
from app.modules.catalog.domain.rooms import Occupancy
from app.modules.catalog.models import Property
from app.modules.catalog.repository import CatalogRepository
from app.modules.catalog.service import (
    CatalogReader,
    CategoryDraft,
    InventoryService,
    ListingService,
    OwnerRecord,
    OwnerService,
    PropertyDraft,
    VerificationService,
)
from app.modules.compliance.domain.grievances import (
    GrievanceCategory,
    GrievanceStatus,
    acknowledge_by,
    resolve_by,
)
from app.modules.compliance.domain.requests import EXPORT_TTL, DataRequestKind, DataRequestStatus
from app.modules.compliance.models import Grievance
from app.modules.compliance.repository import DataExportRepository, DataRequestRepository
from app.modules.geo.reference import read_reference_data
from app.modules.geo.service import GeoReferenceLoader
from app.modules.identity.domain.sessions import SessionKind
from app.modules.identity.repository import UserRepository
from app.modules.identity.service import SessionService
from app.modules.media.domain.assets import AssetStatus, Moderation, Purpose, Visibility
from app.modules.media.models import MediaAsset
from app.modules.media.repository import MediaRepository
from app.modules.pricing.domain.engine import RuleKind
from app.modules.pricing.domain.rule_sets import RuleSetStatus
from app.modules.pricing.models import PricingRuleRow, PricingRuleSet
from app.modules.visits.domain.visits import StudentVisitStatus
from app.modules.visits.models import Visit
from tests.authorization import CALLERS, MATRIX
from tests.conftest import TEST_SECRET_KEY

pytestmark = pytest.mark.integration

# The account behind each signed-in caller, and the kind of session it signs in with.
SIGNED_IN: Final = {
    "student": (Role.STUDENT, SessionKind.USER),
    "parent": (Role.PARENT, SessionKind.USER),
    "owner": (Role.OWNER, SessionKind.USER),
    "admin_by_phone": (Role.ADMIN, SessionKind.USER),
    "field_agent": (Role.FIELD_AGENT, SessionKind.STAFF),
    "ops": (Role.OPS, SessionKind.STAFF),
    "admin": (Role.ADMIN, SessionKind.STAFF),
}
SAFE_METHODS: Final = frozenset({"GET", "HEAD", "OPTIONS"})


class _NoSms:
    shows_code = False

    async def send(self, phone_e164: str, code: str) -> None:
        return None


def _new_phone() -> str:
    return f"+91{6_000_000_000 + secrets.randbelow(4_000_000_000)}"


async def _add_user(app: FastAPI, role: Role) -> int:
    async with app.state.sessionmaker() as db, db.begin():
        return (await UserRepository(db).add(phone_e164=_new_phone(), roles=(role,))).id


async def _start_session(app: FastAPI, user_id: int, kind: SessionKind) -> tuple[str, str]:
    """A new session's token and public id."""
    async with app.state.sessionmaker() as db:
        issued = await SessionService(db, app.state.clock).start(
            user_id, kind=kind, ip_address=None, user_agent=None
        )
    return issued.token, str(issued.public_id)


async def _someone_elses_request(app: FastAPI, kind: DataRequestKind) -> str:
    """A data request of someone else's: an export ready to download, or an open deletion."""
    user_id = await _add_user(app, Role.STUDENT)
    now = app.state.clock.now()
    async with app.state.sessionmaker() as db, db.begin():
        request = await DataRequestRepository(db).insert_open(user_id, kind, now=now)
        assert request is not None
        if kind is DataRequestKind.EXPORT:
            await DataExportRepository(db).put(request.id, b"{}")
            request.status = DataRequestStatus.READY
            request.expires_at = now + EXPORT_TTL
        return str(request.public_id)


async def _someone_elses_media(app: FastAPI) -> str:
    """An upload someone else started."""
    user_id = await _add_user(app, Role.FIELD_AGENT)
    async with app.state.sessionmaker() as db, db.begin():
        asset = await MediaRepository(db).add(
            MediaAsset(
                purpose=Purpose.LISTING_PHOTO,
                visibility=Visibility.PUBLIC,
                status=AssetStatus.AWAITING_UPLOAD,
                moderation=Moderation.APPROVED,
                content_type="image/jpeg",
                renditions=[],
                verified_capture=True,
                uploaded_by=user_id,
            )
        )
        return str(asset.public_id)


async def _ops(app: FastAPI) -> Actor:
    """A new ops member, to make records as the ops console would."""
    return Actor(
        user_id=await _add_user(app, Role.OPS),
        user_public_id=uuid.uuid7(),
        roles=frozenset({Role.OPS}),
        session_id=0,
        session_public_id=uuid.uuid7(),
    )


async def _add_owner(app: FastAPI) -> OwnerRecord:
    """A fictional owner, added by ops with their business record."""
    staff = await _ops(app)
    async with app.state.sessionmaker() as db:
        return await OwnerService(db, app.state.clock).add(
            staff, phone=_new_phone(), legal_name="Fictional Owner", business_name="Fictional"
        )


async def _add_caller(app: FastAPI, role: Role) -> int:
    """A caller's account. The owner's comes with a business record, so the owner area is theirs."""
    if role is Role.OWNER:
        return (await _add_owner(app)).owner.user_id
    return await _add_user(app, role)


async def _part_of_a_listing(app: FastAPI, kind: str) -> str:
    """A fresh fictional listing, or its room category, an empty room in it, or a bed."""
    staff = await _ops(app)
    clock = app.state.clock
    campus = read_reference_data().campuses[0].location.point
    owner = await _add_owner(app)
    async with app.state.sessionmaker() as db:
        listing = await ListingService(
            db, clock, buckets=app.state.media_buckets, flags=app.state.flags
        ).create_property(
            staff,
            PropertyDraft(
                owner=owner.owner.public_id,
                locality=read_reference_data().localities[0].slug,
                name="Fictional Residency",
                address_line="House 1, a fictional lane",
                location=moved(campus, Offset(bearing_deg=90.0, distance_m=500.0)),
                location_precision=LocationPrecision.EXACT,
                gender_policy=GenderPolicy.COED,
                meals=Meals.TWO,
            ),
        )
    if kind == "a_listing":
        return str(listing.public_id)
    inventory = InventoryService
    async with app.state.sessionmaker() as db:
        category = await inventory(db, clock).add_room_category(
            staff,
            listing.public_id,
            CategoryDraft(
                occupancy=Occupancy.DOUBLE,
                label="Double sharing",
                base_rent=Paise(1_200_000),
                security_deposit=Paise(1_200_000),
            ),
        )
    if kind == "a_room_category":
        return str(category.public_id)
    async with app.state.sessionmaker() as db:
        room = await inventory(db, clock).add_room(
            staff, category.public_id, label="101", beds=0 if kind == "a_room" else 1
        )
    if kind == "a_room":
        return str(room.public_id)
    async with app.state.sessionmaker() as db:
        beds = await CatalogRepository(db).beds_in(room.id)
    return str(beds[0].public_id)


async def _live_listing(app: FastAPI) -> str:
    """A fresh fictional listing with a bed to sell, verified and published: its slug."""
    bed = await _part_of_a_listing(app, "a_bed")
    async with app.state.sessionmaker() as db:
        listing = await CatalogReader(
            db, buckets=app.state.media_buckets, flags=app.state.flags
        ).listing_of(bed=uuid.UUID(bed))
    async with app.state.sessionmaker() as db, db.begin():
        # As a passed visit leaves it (tests/integration/test_verification.py books real ones).
        await db.execute(
            update(Property)
            .where(Property.public_id == listing)
            .values(verification_status=VerificationStatus.VERIFIED)
        )
    async with app.state.sessionmaker() as db:
        published = await ListingService(
            db, app.state.clock, buckets=app.state.media_buckets, flags=app.state.flags
        ).move(await _ops(app), listing, PropertyStatus.PUBLISHED)
    return published.slug


async def _someone_elses_visit(app: FastAPI) -> str:
    """A visit booked for a field agent who isn't the caller."""
    listing = await _part_of_a_listing(app, "a_listing")
    ops = await _ops(app)
    agent_id = await _add_user(app, Role.FIELD_AGENT)
    async with app.state.sessionmaker() as db:
        agent = await UserRepository(db).get(agent_id)
        assert agent is not None
        agent_public_id = agent.public_id
    async with app.state.sessionmaker() as db:
        service = VerificationService(db, app.state.clock, buckets=app.state.media_buckets)
        visit = await service.schedule(
            ops, uuid.UUID(listing), agent=agent_public_id, scheduled_for=app.state.clock.now()
        )
    return str(visit.public_id)


async def _someone_elses_student_visit(app: FastAPI) -> str:
    """A student's visit to a live listing, booked with a field agent: neither is the caller."""
    slug = await _live_listing(app)
    student_id = await _add_user(app, Role.STUDENT)
    agent_id = await _add_user(app, Role.FIELD_AGENT)
    ops = await _ops(app)
    now = app.state.clock.now()
    async with app.state.sessionmaker() as db, db.begin():
        property_id = await db.scalar(select(Property.id).where(Property.slug == slug))
        assert property_id is not None
        visit = Visit(
            property_id=property_id,
            student_id=student_id,
            status=StudentVisitStatus.SCHEDULED,
            preferred_starts=[now + timedelta(days=1)],
            requested_at=now,
            scheduled_at=now + timedelta(days=1),
            scheduled_by=ops.user_id,
            agent_id=agent_id,
        )
        db.add(visit)
        await db.flush()
        return str(visit.public_id)


async def _someone_elses_grievance(app: FastAPI) -> str:
    """A complaint someone made signed out, just received."""
    now = app.state.clock.now()
    async with app.state.sessionmaker() as db, db.begin():
        grievance = Grievance(
            ticket_number=new_ticket_number(),
            name="A fictional complainant",
            email="someone@example.com",
            category=GrievanceCategory.OTHER,
            details="A fictional complaint.",
            status=GrievanceStatus.RECEIVED,
            received_at=now,
            acknowledge_by=acknowledge_by(now),
            resolve_by=resolve_by(now),
        )
        db.add(grievance)
        return grievance.ticket_number


async def _a_draft(app: FastAPI, kind: str) -> str:
    """A fresh listing's draft rule set, or the one rule in it."""
    listing = uuid.UUID(await _part_of_a_listing(app, "a_listing"))
    async with app.state.sessionmaker() as db, db.begin():
        property_id = await db.scalar(select(Property.id).where(Property.public_id == listing))
        assert property_id is not None
        draft = PricingRuleSet(property_id=property_id, version=1, status=RuleSetStatus.DRAFT)
        db.add(draft)
        await db.flush()
        rule = PricingRuleRow(
            rule_set_id=draft.id,
            position=0,
            kind=RuleKind.EARLY_BIRD,
            label="Early-bird",
            params={"min_days_before": 30, "bps": -500},
        )
        db.add(rule)
        await db.flush()
        return str(draft.public_id if kind == "a_draft_rule_set" else rule.public_id)


# Path values that need nothing made first.
_FIXED: Final[dict[str, Callable[[], str]]] = {
    "an_optional_purpose": lambda: "marketing",
    "a_campus": lambda: read_reference_data().campuses[0].slug,
    "a_missing_rent_band": lambda: str(uuid.uuid7()),
    "a_missing_quote": lambda: str(uuid.uuid7()),
    "a_missing_alert": lambda: str(uuid.uuid7()),
    "a_missing_block": lambda: str(uuid.uuid7()),
}


async def _path_value(app: FastAPI, kind: str) -> str:
    if (fixed := _FIXED.get(kind)) is not None:
        return fixed()
    match kind:
        case "someone_elses_session":
            user_id = await _add_user(app, Role.STUDENT)
            value = (await _start_session(app, user_id, SessionKind.USER))[1]
        case "someone_elses_export" | "someone_elses_deletion_request":
            wanted = DataRequestKind.EXPORT if kind.endswith("export") else DataRequestKind.DELETION
            value = await _someone_elses_request(app, wanted)
        case "someone_elses_media":
            value = await _someone_elses_media(app)
        case "a_listing" | "a_room_category" | "a_room" | "a_bed":
            value = await _part_of_a_listing(app, kind)
        case "someone_elses_visit":
            value = await _someone_elses_visit(app)
        case "someone_elses_student_visit":
            value = await _someone_elses_student_visit(app)
        case "someone_elses_grievance":
            value = await _someone_elses_grievance(app)
        case "a_draft_rule_set" | "a_draft_rule":
            value = await _a_draft(app, kind)
        case "an_owner":
            value = str((await _add_owner(app)).owner.public_id)
        case "a_live_listing":
            value = await _live_listing(app)
        case _:
            msg = f"no way to make {kind!r}"
            raise LookupError(msg)
    return value


def _headers(token: str | None, *, unsafe: bool) -> dict[str, str]:
    cookies = [] if token is None else [f"{SESSION_COOKIE}={token}"]
    headers: dict[str, str] = {}
    if unsafe:
        csrf = issue_csrf_token(TEST_SECRET_KEY.encode(), token)
        cookies.append(f"{CSRF_COOKIE}={csrf}")
        headers[CSRF_HEADER] = csrf
    if cookies:
        headers["Cookie"] = "; ".join(cookies)
    return headers


def test_every_caller_gets_what_the_authorization_matrix_says(
    make_settings: Callable[..., Settings], database_url: str, valkey_url: str
) -> None:
    app = create_app(
        make_settings(database_url=database_url, redis_url=valkey_url),
        clock=FrozenClock(datetime(2027, 7, 14, 10, 0, tzinfo=UTC)),
    )
    address = f"10.{secrets.randbelow(256)}.{secrets.randbelow(256)}.{secrets.randbelow(256)}"

    async def call_everything() -> list[str]:
        async with app.router.lifespan_context(app):
            app.state.otp_sender = _NoSms()
            async with app.state.sessionmaker() as db:
                await GeoReferenceLoader(db, app.state.clock).load(read_reference_data())
            accounts = {
                caller: (await _add_caller(app, role), kind)
                for caller, (role, kind) in SIGNED_IN.items()
            }
            transport = httpx.ASGITransport(app=app, client=(address, 50_000))
            wrong: list[str] = []
            async with httpx.AsyncClient(
                transport=transport, base_url="https://api.test"
            ) as client:
                for (method, path), rule in MATRIX.items():
                    for caller in CALLERS:
                        values = {
                            name: await _path_value(app, kind) for name, kind in rule.path.items()
                        }
                        url = path.format(**values)
                        token = None
                        if caller in accounts:
                            token, _ = await _start_session(app, *accounts[caller])
                        client.cookies.clear()
                        response = await client.request(
                            method,
                            url,
                            headers=_headers(token, unsafe=method not in SAFE_METHODS),
                            **rule.request(),
                        )
                        expected = rule.expected[caller]
                        if response.status_code != expected:
                            wrong.append(
                                f"{method} {path} as {caller}: {response.status_code}, "
                                f"expected {expected} ({response.text[:100]})"
                            )
            return wrong

    assert asyncio.run(call_everything()) == []
