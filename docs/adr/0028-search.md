# ADR 0028: Search: a read model of live listings kept from the catalog's events, category filters on the price summaries, keyset pages in any order, distances from display points

- Status: accepted
- Date: 2026-10-27
- Build step: 3.2 (search API)

## Context

- **ARCHITECTURE §10.1** specifies `GET /v1/search/properties`:
  - one place to search: a campus with a radius, a locality, or a map area;
  - the move-in month, and a budget checked against that month's price summaries;
  - gender, occupancy, meals, AC, attached bath and amenities;
  - `verified_only`, true by default, and `available`;
  - text, matched by trigrams and full text on the name and locality;
  - four sorts, and cursor pages of up to 50.

  Each card shows the listing's name, locality and display point; its distance to the campus and to the nearest metro station; its price range for the month; badges; a cover photo; and how many beds are free.
- **BUILD_PLAN 3.2** is done when integration tests cover each filter, and p95 is under 300 ms on 3,000 seeded properties.
- **Constraints:**
  - modules never read each other's tables (ARCHITECTURE §5);
  - public distances are measured from display points (ADR 0021);
  - public responses never hold the exact point, the address or the owner's phone (ADR 0026).

## Decision

1. **The search module keeps its own read model**, `search_listings`.
   - It has one row per listing the public can find: published, with a verification that hasn't failed or been suspended.
   - The row holds public details only:
     - the display point, the locality and its name;
     - the gender policy, meals, and whether the listing is verified and licensed;
     - the amenities;
     - the first few photos' ids;
     - when the listing was first published.
   - Generated columns hold the name and locality as full text and as trigram text.
   - **Refreshing.**
     - The catalog's events keep it up to date. `catalog.listing_changed` is new and covers the listing's own details, status, verification, amenities and photos; `catalog.inventory_changed` comes from ADR 0027.
     - Either event refreshes the listing's whole entry together with its price summaries, as the nightly run does too. The jobs are renamed `search.refresh_listing` and `search.refresh_all`, and a migration drops any job still waiting under ADR 0027's names.
     - Whether only verified listings show is decided at each search from the flag, so switching `verified_only` needs no refresh.
2. **Category filters work on the price summaries.**
   - Each summary row now carries its category's occupancy, AC and attached bath.
   - A listing matches when one of its categories meets every category filter for the month: occupancy, AC, attached bath, a rent range that overlaps the budget, and a free bed.
   - The card shows the price range of those categories only.
3. **The query** applies the listing filters to the read model. Then, for each listing that is left, it looks up the matching categories laterally, by an index on listing and month.
   - The first version joined an aggregate of the whole month. The planner misjudged the map-area filter, chose a nested loop, and took 365 ms.
   - The lateral lookup grows only with the listings that are left, whatever the planner guesses.
4. **Text** finds listings by whole words (full text with the `simple` dictionary, since names and places aren't English) or by near misses (trigram word similarity, so one typo still finds the PG).
5. **Orders and pages.**
   - `recommended` means the best text match when words are searched, otherwise the nearest to the chosen campus, otherwise the newest.
   - The price sorts use each listing's lowest matching rent.
   - Pages are keyset: an opaque cursor carries the order, the last card's sort key and its id. A page never repeats or skips a listing while listings change.
   - A cursor from another order, or anything that isn't a cursor, is refused.
6. **Places and distances.**
   - A search names at most one place: a campus with a radius (200 m to 15 km, 3 km by default), a locality, or a map area inside NCR.
   - Distances to the campus and to the nearest metro station are measured from display points.
   - The geo module answers through `GeoLookup`: a campus by its slug, and the station nearest each point on a page, in one query.
7. **Free beds** show as a bucket: `none`, `few` (1 or 2), `some` (3 to 9) or `many` (10 or more). They come from real inventory, without exact counts (CLAUDE.md rule 7).
8. **Validation.**
   - Unknown parameters are refused with 422 `VALIDATION_ERROR`.
   - A search that can't be answered gets `422 SEARCH_INVALID`, naming every problem. That covers two places at once, a distance sort without a campus, a month without prices, a map area outside NCR, an unknown campus or locality, and a cursor that doesn't fit.
9. **Limits and caching.**
   - 600 searches per 10 minutes per IP. That is generous for shared college networks, and searches are let through if Redis is down.
   - Results are cached publicly for 30 seconds.
10. **Proof.**
    - Integration tests cover each filter, the sorts, the pages and a refresh after a change.
    - The privacy sweep (ADR 0026) now finds its listing through search.
    - A performance test seeds 3,000 fictional listings in a database of its own and times 253 searches of every kind through the API: median 29 ms, p95 65 ms, against a target of 300 ms.

## Consequences

- The map's pins (3.3) read the same read model and summaries.
- `available` excludes nothing until bookings (Phase 5) start taking beds: until then, every summarised category has a free bed.
- Phase 4's prices replace the summaries' base rents; nothing in search changes.
- **Founders' decision:** what `recommended` should weigh once there's data, such as verification, reviews, price and distance.
