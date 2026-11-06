"""Seeds the load tests' database (step 8.2): `python -m tests.load.seed [count]`, with
DATABASE_URL naming a database of its own, as scripts/load-test.sh arranges. The six sample PGs come
first, through the services (`python -m app.manage catalog samples`), so quotes and holds have real
listings to work on; this adds `count` fictional listings (3,000 unless given) for search and the
map."""

import asyncio
import random
import sys

from app.config import Settings
from app.main import create_app
from tests.bulk_listings import add_listings


async def main(count: int) -> None:
    app = create_app(Settings())
    async with app.router.lifespan_context(app):
        await add_listings(
            app.state.sessionmaker,
            app.state.engine,
            now=app.state.clock.now(),
            # The same listings every run, so results compare.
            rng=random.Random(82),  # noqa: S311 - fictional data, not secrets
            count=count,
        )


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 3_000))
