# ADR 0027: Price summaries: a read model the search module owns, refreshed through the outbox after catalog changes and every night

- Status: accepted
- Date: 2026-10-27
- Build step: 3.1 (price summaries, base-rent version)
- Amended by [ADR 0028](0028-search.md): summaries also carry their category's occupancy, AC and attached bath; the jobs are now `search.refresh_listing` and `search.refresh_all`, and refresh a listing's search entry too; the lookup index is (listing, month).

## Context

- `property_price_summaries` feeds search's budget filter and price sort, and the map's price pins. It is worked out ahead of time, so neither prices a listing per request (ARCHITECTURE §6 and §18).
- **BUILD_PLAN 3.1** asks for summaries of the next six months, from base rents for now, recomputed on catalog changes through the outbox. It's done when summaries refresh within a minute of a rent change.
- Modules never read each other's tables (ARCHITECTURE §5).

## Decision

1. **The search module owns `property_price_summaries`.**
   - There is one row per room category and month, with the rent range, the free beds and when the row was worked out.
   - The database checks that the month is a first day, that 0 < minimum ≤ maximum, and that beds ≥ 0.
2. **This is the base-rent version.**
   - A month's range is the category's base rent at both ends, which is what a quote charges until the pricing engine arrives (Phase 4). The engine will then give each month its own range.
   - Every active bed counts as free until bookings exist (Phase 5).
   - Only active categories with an active bed are summarised, as the public listing shows them (ADR 0026).
3. **Seven months:** this one and the next six, in India's calendar. Six months ahead are there even on the morning a month turns, before the nightly refresh has run.
4. **Refreshing.**
   - **After a change:** the catalog writes `catalog.inventory_changed`, with the listing's id, in the same transaction as every change to a room category, a room or a bed. The worker polls every second and works out that listing's summaries again, so they follow a rent change within seconds.
   - **One job per change, with no dedupe key.** The outbox dedupes a key forever, so a key per listing would refresh each listing only once. Recomputing is idempotent and takes three queries.
   - **A listing's summaries are replaced as a whole** in one transaction, so search sees either the old set or the new one.
   - **Every night** at 00:30 IST, `search.recompute_all_price_summaries` adds one `search.recompute_price_summaries` job per listing, deduped by listing and date. The months roll forward, and anything missed is caught.
   - **A data migration** queues that nightly job once, so the listings that exist when this ships get their summaries straight away.
5. **The boundary.**
   - The search module reads rents and beds through the catalog's `CatalogLookup`, never through the catalog's tables.
   - The catalog doesn't know who handles its event; `app/jobs.py` wires that up.

## Consequences

- Search (3.2) and the map (3.3) take prices from here only.
- Phase 4 replaces `summarise` with the engine's ranges, and pricing rule changes will emit an event of their own. Phase 5 subtracts the beds that are allocated.
- Every catalog edit adds a job. At today's scale that costs nothing, and the nightly run limits how stale a summary can get if one job fails.
