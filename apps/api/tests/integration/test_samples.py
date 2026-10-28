"""Fictional sample PGs for local development (step 3.4, ADR 0030): built live through the same
services ops and field agents use, photos and a passed visit included; once only; never when
deployed."""

import asyncio
import io
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.core.clock import FrozenClock
from app.manage import main as manage
from app.samples import LOCK, SAMPLES, SampleBuilder
from tests.jobs import run_due_jobs
from tests.staff_api import NOW, Staff, run_as_staff
from tests.storage import BUCKETS, MemoryStorage

pytestmark = pytest.mark.integration


def test_a_sample_pg_is_built_live_with_its_photos_and_a_passed_visit_and_only_once(
    make_settings: Callable[..., Settings], database_url: str
) -> None:
    said: list[str] = []

    async def scenario(ops: Staff) -> dict[str, Any]:
        def builder() -> SampleBuilder:
            return SampleBuilder(
                ops.app.state.sessionmaker,
                ops.app.state.clock,
                storage=MemoryStorage(),
                buckets=BUCKETS,
                say=said.append,
                samples=SAMPLES[:1],
            )

        built = await builder().build()
        await run_due_jobs(ops.app)
        page = await ops.client.get(f"/v1/properties/{built[0]}")
        found = await ops.client.get(
            "/v1/search/properties", params={"q": "fictional sample aster"}
        )
        return {
            "built": built,
            "page": page.json(),
            "found": [item["slug"] for item in found.json()["items"]],
            "again": await builder().build(),
        }

    found = run_as_staff(make_settings(database_url=database_url), scenario)

    [slug] = found["built"]
    page = found["page"]
    assert slug == "fictional-sample-pg-aster-kamla-nagar"
    assert page["name"] == "Fictional Sample PG Aster"
    assert "fictional" in page["description"]
    assert page["verified"] is True
    assert page["safety"]["verifiedOn"] == NOW.date().isoformat()
    assert len(page["media"]) == 3
    assert [category["baseRentPaise"] for category in page["categories"]] == [1_250_000, 900_000]
    assert slug in found["found"]
    # A second run finds them there and adds nothing.
    assert found["again"] == []
    assert said[-1] == "The sample listings are there already."


def test_a_run_waits_for_one_already_making_the_samples(
    make_settings: Callable[..., Settings], database_url: str
) -> None:
    # Two browser-test workers may run the command at once; the second must not make them again.
    async def scenario(ops: Staff) -> bool:
        sessions = ops.app.state.sessionmaker
        builder = SampleBuilder(
            sessions,
            ops.app.state.clock,
            storage=MemoryStorage(),
            buckets=BUCKETS,
            say=lambda _: None,
            samples=SAMPLES[:1],
        )
        async with sessions() as other, other.begin():
            await other.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(LOCK, 0))))
            run = asyncio.create_task(builder.build())
            await asyncio.sleep(0.5)
            waited = not run.done()
        await run
        return waited

    assert run_as_staff(make_settings(database_url=database_url), scenario)


def test_sample_pgs_are_refused_anywhere_deployed(
    make_settings: Callable[..., Settings], database_url: str
) -> None:
    settings = make_settings(database_url=database_url).model_copy(update={"app_env": "production"})
    out = io.StringIO()

    status = manage(["catalog", "samples"], settings=settings, clock=FrozenClock(NOW), out=out)

    assert status == 1
    assert "local development only" in out.getvalue()
