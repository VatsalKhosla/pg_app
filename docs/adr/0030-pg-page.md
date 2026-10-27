# ADR 0030: The PG page: rendered per request with its nonce from data cached across visitors, every charge upfront, the area as a circle, and fictional sample PGs to try it on

- Status: accepted
- Date: 2026-10-27
- Build step: 3.4 (PG detail page)
- Amends: [ADR 0011](0011-web-foundations.md), which left this step to choose between hash-based CSP and nonces.

## Context

- **ARCHITECTURE §10.6** describes `/pg/[slug]`: a gallery with "verified photo" labels, video, a safety summary, room categories with prices, the deposit and mandatory charges shown upfront, amenities, house rules, a small map at the display point, distances, the owner's business name, and a "Book a visit" call to action.
- **BUILD_PLAN 3.4** is done when the page scores at least 85 on Lighthouse mobile and shows no hidden charges (CLAUDE.md rule 7: the full price, the deposit and mandatory charges, all before booking).
- **The CSP.** ADR 0011 makes every page render per request with a fresh CSP nonce, and keeps ISR off until this step. This step's options were Next's experimental hash-based CSP (SRI) or nonces on dynamic routes only.

## Decision

1. **Nonces stay on every page, and the data is cached instead of the HTML.**
   - Next's SRI is experimental and hashes only external script files. The App Router still inlines each page's data scripts, which a static header couldn't allow without `'unsafe-inline'`.
   - So the page renders per request, and the listing it needs comes from Next's data cache (`unstable_cache`, tagged `listings` and `listing:<slug>`), fetched without the visitor's cookies and fresh within a minute, as the API's own `Cache-Control` says.
   - Rendering a cached listing takes about 90 ms locally. Step 3.6 adds revalidation on demand by tag.
   - Cache Components (`use cache`) would bring partial prerendering, which nonce-based CSP rules out.
2. **No hidden charges.**
   - For each room category, the page shows the rent per bed per month, the security deposit, and every mandatory charge:
     - monthly charges, with their amount;
     - metered charges, with their rate and the monthly estimate;
     - one-time charges.
   - It also shows the totals the API works out, so nothing is computed in the browser.
   - A browser test reads the listing from the API and checks that each of those amounts is on the page.
3. **The safety summary** comes from the last field visit that passed the building (`GET /v1/properties/{slug}` gains `safety`), with the visit's date. It shows:
   - the exits;
   - fire extinguishers, CCTV and a warden at night, each yes or no;
   - the features for women that the agent saw;
   - the licence status and the housing society's permission.

   The building's condition, cracks and age stay out of the summary: they are judgements for the agent (ADR 0024), easy to misread out of context.
4. **Where it is.**
   - A small map shows the display point as a circle about 150 m across, never a pin, beside a sentence saying the exact address comes with a booked visit.
   - The campuses within 5 km and the two nearest metro stations are listed with distances from the display point, which the API now gives (`campusesNearby`, `stationsNearby`).
   - The map is a new `LocationMap` behind the `MapProvider` interface (ADR 0006). Its MapLibre code loads only when the map scrolls near the screen.
5. **Photos** are plain `<picture>` elements with AVIF and WebP `srcset`s of the pipeline's sizes, so no image script runs on the page. The first photo loads at once, being the page's largest paint; the rest load lazily. Videos load only when played.
6. **"Book a visit"** links to `/pg/[slug]/visit`, which says that booking opens soon, until step 3.7 builds it there.
7. **Fictional sample PGs.**
   - `python -m app.manage catalog samples`, which `make seed` now runs, adds six live PGs around the seeded campuses, with names that say they are fictional and generated photos.
   - They are built through the same services ops and field agents use: owner, listing, rooms, photos (uploaded and processed), a passed visit, and publishing.
   - A second run adds nothing, and the command refuses anywhere deployed.
   - They give local development, the browser test and Lighthouse something real to show.
8. **`make lighthouse-pg`** audits a sample PG's page on Lighthouse's mobile profile, against the browser tests' API, and fails below 85. The first run scored 90 for performance (runs of 92, 90 and 88) and 100 for accessibility, best practices and SEO.

## Consequences

- HTML isn't cached at the edge. Each view costs a render of cached data, and time to first byte stays worth watching (ADR 0011).
- A listing's change reaches its page within a minute, until step 3.6's revalidation on demand.
- JSON-LD, Open Graph images and landing pages are step 3.6. Visits are step 3.7.
- **Founders' decision:** which of the checklist's findings the public summary shows. The building's condition and age could be added if they help students.
