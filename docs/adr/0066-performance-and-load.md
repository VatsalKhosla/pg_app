# ADR 0066: Performance and load: k6 at the planning load on a private copy of the API, query plans at load scale, and Lighthouse budgets in CI

- Status: accepted
- Date: 2026-11-06
- Build step: 8.2 (performance and load)

## Context

- **BUILD_PLAN 8.2** asks for:
  - k6 at ARCHITECTURE §18's planning load, including the hold race;
  - `EXPLAIN ANALYZE` on the top queries;
  - caching verified;
  - Lighthouse budgets enforced in CI.
- **The planning load:**
  - 300 reads a second at peak, from search, the map and PG pages;
  - 20 writes a second;
  - 50 hold attempts on one popular PG at once.
- **The SLOs:** p95 under 300 ms for search and map pins, and under 400 ms for a quote or a hold, gateway time excluded.
- **No production-sized environment exists yet:** AWS comes in step 8.5. The test site runs on free plans that sleep, and the founders use it.

## Decision

1. **Load tests run against a private copy of the API**: `make load-test`, with k6 in its digest-pinned container.
   - **Data:** a database of its own, holding the geo data, the six sample PGs (made through the services, so quotes and holds work) and 3,000 fictional listings for search and the map.
   - **The API:** 4 workers, as a production container runs, beside the job worker.
   - **Visitors:** each simulated visitor comes from an address of its own, as through a load balancer, so per-address limits apply per visitor rather than to the test.
   - **Scenarios:** reads, writes (quotes) and the hold race, each with its SLO as a threshold.
2. **The top requests' queries are explained at that scale**: `python -m tests.load.explain`. It records each request's statements and runs `EXPLAIN (ANALYZE, BUFFERS)` on the reads, inside a rolled-back transaction.
3. **Lighthouse runs in CI on every push**, and staging deploys only after it passes:
   - the home page at 90 or above in every category;
   - a PG's page and search at 85 or above;
   - the median of five runs, because shared runners vary.
   - Search is report-only for now, the founders' choice on 2026-11-08: it scores 83 to 84 since the UI refresh (87 before it), and the refresh shouldn't wait on it. It still runs and shows a failure on every run, until search is back over 85.

## What it measured (2026-11-06)

This was a 4-vCPU development VM, shared by k6, the API and the database, so the figures are a floor.

- **Reads.** One 4-worker API sustains about 120 to 150 reads a second within its SLO. At 120 a second, p95 was 227 ms for search, 183 ms for map pins and 206 ms for PG pages. At 180 a second it saturated, with p95 over a second. The planning load's 300 reads a second therefore needs about three such containers, or bigger ones (sizing for 8.5).
- **The database isn't the limit.** At 3,006 listings, database time per request was:
  - 4 ms for search near a campus, 0.6 ms in a locality;
  - 14 ms for the map's pins;
  - 0.4 ms for a PG's page and 0.3 ms for a quote.

  The time goes into the API's own work. Search by name scanned the table for a broad term, which the fictional names (8 first words and 6 second words) make common. For a selective term, the planner combines the full-text and trigram GIN indexes.
- **Writes.** Quotes at 10 a second took 78 ms at p95, all made.
- **The hold race.** 50 students held one room type for the same move-in at once.
  - It was correct: 3 holds for its 3 free beds, 47 refused with 409, no errors.
  - It was slow: p95 1.65 s against 400 ms. Holds on a room type take its beds' locks one at a time (ARCHITECTURE §7.3), so the refused ones queue behind the winners just to learn the room is full.

## Consequences

- **Done: holds lock only the bed they take** (`FOR UPDATE SKIP LOCKED`; ARCHITECTURE §7.3).
  - `rank_free_beds` keeps `choose_bed`'s preference among beds nobody is taking, and the exclusion constraint stays the guarantee.
  - Holds run side by side, and once every bed is spoken for, the rest are refused at once. A racing hold that rolls back can cause a rare "try again".
  - The 50-concurrent-holds test passes. The race on this VM went from 1.65 s to 1.5 s at p95: it's now limited by CPU, not the lock.
  - A single hold in the race looked slow (about 330 ms on the server), but that was a cold worker's first request. Timed one after another on a warm API, holds take 40 to 90 ms.
  - The race's p95 here is 50 requests at once on 4 CPUs shared with the database and k6. On production instances, warmed up and with the database apart, it should come within its 400 ms; the 8.5 environment is where to confirm it.
- **Caching:** the scenarios pick random map areas and searches, so the figures above are close to a cache that never helps. Real traffic clusters around campuses and is cheaper. The cache's behaviour is proven by its own tests (ETags, invalidation on listing changes).
- **Production sizing (8.5)** takes about three 4-worker API containers for the planning load, with the database on its own instance.
- The load tests aren't run in CI: they need minutes of dedicated CPU. Run them before every peak season and major release (ARCHITECTURE §18).
