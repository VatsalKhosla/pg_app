"""Search's speed (step 3.2, ADR 0028): BUILD_PLAN asks for p95 under 300 ms on a seeded set of
3,000 properties. The listings are fictional, scattered around the seeded campuses, in a database
of their own so the other tests never see them.
"""

import asyncio
import logging
import random
import statistics
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any, Final

import pytest
from sqlalchemy.engine import make_url

from app.config import Settings
from tests.bulk_listings import FIRST_WORDS, SECOND_WORDS, add_listings
from tests.integration.conftest import alembic_config, execute_autocommit
from tests.staff_api import DATA, Staff, run_as_staff

pytestmark = pytest.mark.integration

LISTINGS: Final = 3_000
SEARCHES: Final = 200
P95_LIMIT_MS: Final = 300


@pytest.fixture
def own_database_url(postgres_url: str) -> Iterator[str]:
    """A database of this test's own, migrated, and dropped afterwards."""
    from alembic import command  # noqa: PLC0415 - only this fixture migrates

    name = f"search_speed_{uuid.uuid4().hex[:12]}"
    asyncio.run(execute_autocommit(postgres_url, f'CREATE DATABASE "{name}"'))
    url = make_url(postgres_url).set(database=name).render_as_string(hide_password=False)
    try:
        command.upgrade(alembic_config(url), "head")
        yield url
    finally:
        asyncio.run(execute_autocommit(postgres_url, f'DROP DATABASE "{name}" WITH (FORCE)'))


async def _seed(ops: Staff, rng: random.Random) -> None:
    """3,000 live listings with three room categories each, and their search entries and price
    summaries, written straight into the tables: only the search query is being timed."""
    await add_listings(
        ops.app.state.sessionmaker,
        ops.app.state.engine,
        now=ops.app.state.clock.now(),
        rng=rng,
        count=LISTINGS,
    )


def _searches(rng: random.Random) -> list[dict[str, Any]]:
    campuses = [campus.slug for campus in DATA.campuses]
    localities = [locality.slug for locality in DATA.localities]
    kinds: list[Callable[[], dict[str, Any]]] = [
        lambda: {"campus": rng.choice(campuses), "sort": "distance"},
        lambda: {"campus": rng.choice(campuses), "radius_m": 5_000, "sort": "price_asc"},
        lambda: {
            "campus": rng.choice(campuses),
            "budget_min_paise": 800_000,
            "budget_max_paise": 1_500_000,
            "occupancy": rng.choice(("single", "double", "triple")),
        },
        lambda: {"locality": rng.choice(localities), "sort": "newest"},
        lambda: {"gender": rng.choice(("boys", "girls")), "ac": "true", "sort": "price_desc"},
        lambda: {"meals": "three", "attached_bath": "true", "available": "true"},
        lambda: {"amenities": ["wifi", "cctv"], "campus": rng.choice(campuses)},
        lambda: {"q": rng.choice(FIRST_WORDS).lower()},
        lambda: {"q": f"{rng.choice(FIRST_WORDS)} {rng.choice(SECOND_WORDS)}"},
        lambda: {"bbox": "77.15,28.64,77.25,28.72", "sort": "price_asc"},
        lambda: {"move_in_month": None, "campus": rng.choice(campuses), "limit": 50},
    ]
    return [
        {key: value for key, value in rng.choice(kinds)().items() if value} for _ in range(SEARCHES)
    ]


def test_search_answers_within_300_ms_at_the_95th_percentile_over_3000_listings(
    make_settings: Callable[..., Settings], own_database_url: str, valkey_url: str
) -> None:
    rng = random.Random(2027)  # noqa: S311 - fictional test data, the same every run

    async def scenario(ops: Staff) -> list[tuple[float, dict[str, Any]]]:
        await _seed(ops, rng)
        timings: list[tuple[float, dict[str, Any]]] = []
        searches = _searches(rng)
        # The first few warm the connection pool and the planner's caches.
        for params in searches[:5]:
            await ops.client.get("/v1/search/properties", params=params)
        for params in searches:
            started = time.perf_counter()
            response = await ops.client.get("/v1/search/properties", params=params)
            timings.append(((time.perf_counter() - started) * 1_000, params))
            assert response.status_code == 200, response.text
            next_cursor = response.json()["nextCursor"]
            if next_cursor is not None and rng.random() < 0.25:
                started = time.perf_counter()
                page = await ops.client.get(
                    "/v1/search/properties", params=params | {"cursor": next_cursor}
                )
                timings.append(((time.perf_counter() - started) * 1_000, params | {"page": 2}))
                assert page.status_code == 200, page.text
        return timings

    settings = make_settings(database_url=own_database_url, redis_url=valkey_url)
    found = run_as_staff(settings, scenario)

    timings = [milliseconds for milliseconds, _ in found]
    p95 = statistics.quantiles(timings, n=20)[-1]
    slowest = sorted(found, key=lambda each: each[0], reverse=True)[:5]
    logging.getLogger(__name__).info(
        "search over %d listings: median %.0f ms, p95 %.0f ms, %d searches",
        LISTINGS,
        statistics.median(timings),
        p95,
        len(timings),
    )
    assert p95 < P95_LIMIT_MS, (
        f"p95 {p95:.0f} ms (median {statistics.median(timings):.0f} ms) over {len(timings)}"
        f" searches; slowest: {[(round(ms), params) for ms, params in slowest]}"
    )
