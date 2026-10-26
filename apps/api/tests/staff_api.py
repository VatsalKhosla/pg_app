"""Staff using the API as the ops console and the field agents' screens do (steps 2.4 and 2.5): a
signed-in staff member of a given role, with the console's calls, and listings built and verified
the way staff build and verify them.

Listings here are fictional, placed by moving away from a seeded campus.
"""

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI

from app.config import Settings
from app.core.actor import Role
from app.core.clock import FrozenClock
from app.core.cookies import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from app.core.csrf import issue_csrf_token
from app.main import create_app
from app.modules.catalog.domain.location import Offset, moved
from app.modules.geo.reference import read_reference_data
from app.modules.geo.service import GeoReferenceLoader
from app.modules.identity.domain.sessions import SessionKind
from app.modules.identity.repository import UserRepository
from app.modules.identity.service import SessionService
from app.modules.media.domain.assets import AssetStatus, Moderation, Purpose, Visibility
from app.modules.media.models import MediaAsset
from app.modules.media.repository import MediaRepository
from tests.conftest import TEST_SECRET_KEY

DATA = read_reference_data()
CAMPUS = next(campus for campus in DATA.campuses if campus.slug == "hindu-college").location.point
# The scenarios' frozen "now".
NOW = datetime(2027, 7, 14, 10, 0, tzinfo=UTC)


def phone() -> str:
    """A random Indian mobile number, ten digits, so tests never share one."""
    return f"{6_000_000_000 + secrets.randbelow(4_000_000_000)}"


def spot(metres: float, bearing: float = 45.0) -> dict[str, float]:
    point = moved(CAMPUS, Offset(bearing_deg=bearing, distance_m=metres))
    return {"lat": point.lat, "lng": point.lng}


class Staff:
    """A staff member, signed in to staff tools."""

    def __init__(
        self, app: FastAPI, client: httpx.AsyncClient, *, user_id: int, token: str
    ) -> None:
        self.app = app
        self.client = client
        self.user_id = user_id
        self._token = token

    def _headers(self) -> dict[str, str]:
        csrf = issue_csrf_token(TEST_SECRET_KEY.encode(), self._token)
        return {
            CSRF_HEADER: csrf,
            "Cookie": f"{SESSION_COOKIE}={self._token}; {CSRF_COOKIE}={csrf}",
        }

    async def public_id(self) -> str:
        """The id the API knows this staff member by."""
        async with self.app.state.sessionmaker() as db:
            user = await UserRepository(db).get(self.user_id)
            assert user is not None
            return str(user.public_id)

    async def call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        return await self.client.request(method, path, headers=self._headers(), **kwargs)

    async def ok(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = await self.call(method, path, **kwargs)
        assert response.status_code in {200, 201}, response.text
        body: dict[str, Any] = response.json()
        return body

    async def owner(self) -> dict[str, Any]:
        return await self.ok(
            "POST",
            "/v1/ops/owners",
            json={
                "phone": phone(),
                "legalName": "Fictional Stays Private Limited",
                "businessName": f"Fictional Stays {secrets.token_hex(3)}",
                "name": "A Fictional Owner",
            },
        )

    async def listing(self, owner: dict[str, Any], *, at: dict[str, float]) -> dict[str, Any]:
        return await self.ok(
            "POST",
            "/v1/ops/properties",
            json={
                "owner": owner["id"],
                "locality": "kamla-nagar",
                "name": "Fictional Residency",
                "addressLine": "House 1, a fictional lane",
                "location": at,
                "locationPrecision": "exact",
                "genderPolicy": "girls",
                "meals": "two",
                "houseRules": ["No smoking"],
            },
        )

    async def media(
        self, status: AssetStatus = AssetStatus.READY, purpose: Purpose = Purpose.LISTING_PHOTO
    ) -> str:
        """A photo of this staff member's that the media pipeline has finished with (or
        rejected): a listing photo, or a verification photo kept private."""
        private = purpose is Purpose.VERIFICATION_PHOTO
        async with self.app.state.sessionmaker() as db, db.begin():
            asset = await MediaRepository(db).add(
                MediaAsset(
                    purpose=purpose,
                    visibility=Visibility.PRIVATE if private else Visibility.PUBLIC,
                    status=status,
                    moderation=Moderation.APPROVED,
                    content_type="image/jpeg",
                    renditions=[]
                    if status != AssetStatus.READY
                    else [
                        {
                            "name": "card",
                            "content_type": "image/webp",
                            "key": f"{'files' if private else 'media'}/fictional/card.webp",
                            "width": 480,
                            "height": 360,
                            "bytes": 1000,
                        }
                    ],
                    verified_capture=False,
                    uploaded_by=self.user_id,
                )
            )
            return str(asset.public_id)


async def sign_in(app: FastAPI, client: httpx.AsyncClient, *roles: Role) -> Staff:
    """A new staff member with these roles, in a staff session."""
    async with app.state.sessionmaker() as db:
        async with db.begin():
            user = await UserRepository(db).add(phone_e164=f"+91{phone()}", roles=roles)
        session = await SessionService(db, app.state.clock).start(
            user.id, kind=SessionKind.STAFF, ip_address=None, user_agent=None
        )
    return Staff(app, client, user_id=user.id, token=session.token)


CHECKLIST: dict[str, Any] = {
    "buildingAgeYears": 12,
    "condition": "good",
    "cracks": "none",
    "exits": 2,
    "fireExtinguishers": True,
    "cctv": True,
    "warden": True,
    "womenSafety": ["secure_entry", "woman_staff"],
    "licenceNumber": None,
    "societyPermission": "n/a",
    "authorityNotice": False,
}


async def book(ops: Staff, agent: Staff, listing_id: str) -> dict[str, Any]:
    """A visit, booked by ops for the agent, at the frozen clock's time."""
    agent_id = await agent.public_id()
    return await ops.ok(
        "POST",
        f"/v1/ops/properties/{listing_id}/verification-visits",
        json={"agent": agent_id, "scheduledFor": ops.app.state.clock.now().isoformat()},
    )


async def report(
    agent: Staff, visit: dict[str, Any], *, at: dict[str, float], **changes: Any
) -> httpx.Response:
    """The agent's report from ``at``, passed with one photo unless ``changes`` say otherwise."""
    body: dict[str, Any] = {
        "checklist": CHECKLIST,
        "result": "passed",
        "notes": "",
        "position": at,
        "accuracyM": 8.5,
        "photos": [await agent.media(purpose=Purpose.VERIFICATION_PHOTO)],
    } | changes
    return await agent.call("POST", f"/v1/ops/verification-visits/{visit['id']}/report", json=body)


async def verify(ops: Staff, listing: dict[str, Any]) -> dict[str, Any]:
    """The listing verified as a field agent would: booked, visited, passed."""
    agent = await sign_in(ops.app, ops.client, Role.FIELD_AGENT)
    visit = await book(ops, agent, listing["id"])
    response = await report(agent, visit, at=listing["location"])
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def run_as_staff[T](
    settings: Settings, scenario: Callable[[Staff], Awaitable[T]], *, role: Role = Role.OPS
) -> T:
    """Run ``scenario`` as a new staff member with ``role``, against the app with the geo data
    loaded and the clock frozen at NOW."""
    app = create_app(settings, clock=FrozenClock(NOW))

    async def wrapped() -> T:
        async with app.router.lifespan_context(app):
            async with app.state.sessionmaker() as db:
                await GeoReferenceLoader(db, app.state.clock).load(DATA)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="https://api.test"
            ) as client:
                return await scenario(await sign_in(app, client, role))

    return asyncio.run(wrapped())
