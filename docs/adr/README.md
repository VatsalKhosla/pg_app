# Architecture decision records

One file per real decision: the context, what was decided and what follows from it. ADRs are never edited after the fact, except for links. A changed decision gets a new ADR that supersedes the old one, and the old one's status says so.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-modular-monolith.md) | A modular monolith: one API and one worker, boundaries enforced by import-linter | Accepted |
| [0002](0002-fastapi-and-nextjs.md) | FastAPI for the API, Next.js for the web app, OpenAPI as the contract between them | Accepted |
| [0003](0003-postgresql-postgis-exclusion-constraints.md) | PostgreSQL with PostGIS; an exclusion constraint makes double booking impossible | Accepted |
| [0004](0004-money-in-paise-and-the-ledger.md) | Money in integer paise; a double-entry ledger; owners' money never pooled | Accepted |
| [0005](0005-outbox-jobs-instead-of-a-broker.md) | Outbox jobs in PostgreSQL instead of a message broker | Accepted |
| [0006](0006-map-provider-behind-an-interface.md) | The map provider sits behind a `MapProvider` interface | Accepted |
| [0007](0007-toolchain-and-dependency-policy.md) | Toolchain pins and the dependency supply-chain policy (7-day cooldown) | Accepted |
| [0008](0008-local-infrastructure.md) | Local infrastructure: PostgreSQL + PostGIS, Valkey, SeaweedFS, Mailpit | Accepted |
| [0009](0009-api-foundations.md) | API foundations: settings, logging, problem details, security headers, probes | Accepted |
| [0010](0010-core-building-blocks.md) | Core building blocks: money, clock, ids, outbox, idempotency, audit, flags, limits | Accepted |
| [0011](0011-web-foundations.md) | Web foundations: nonce CSP, server-side translations, the JavaScript budget, tests | Accepted |
| [0012](0012-typed-api-client.md) | The typed API client: generated types, problem+json errors, the staleness check | Accepted; readonly types superseded by 0019 |
| [0013](0013-ci-and-supply-chain.md) | CI and supply-chain security: GitHub Actions, scanners, Renovate | Accepted |
| [0014](0014-sessions-and-csrf.md) | Sessions and CSRF: hashed opaque tokens, `__Secure-` cookies, sliding expiry, signed double-submit tokens | Accepted |
| [0015](0015-phone-sign-in.md) | Phone sign-in: HMAC-stored one-time codes, layered abuse limits, Turnstile bound to the form and site, SMS behind a port | Accepted |
| [0016](0016-staff-sign-in.md) | Staff sign-in: Google OIDC with PKCE and fully checked ID tokens, or a phone code plus an authenticator app; staff made only by operators; cursor pagination | Accepted |
| [0017](0017-authorization.md) | Authorization: the actor from core, policy functions, 401/403/404, and a hand-written matrix of every route and caller enforced in CI | Accepted |
| [0018](0018-consent-and-data-requests.md) | DPDP: consent per purpose and notice version, no account without it, exports and deletions with an ops queue, one retention schedule | Accepted |
| [0019](0019-web-sign-in.md) | Web sign-in: the browser talks to the API, one site for both, sessions checked once per page, safe `next`, browser tests against the real API | Accepted |
| [0020](0020-geo-reference-data.md) | Geo reference data: places chosen by hand, coordinates generated from OpenStreetMap and lines from Wikidata under their usage policies, loaded idempotently, served publicly | Accepted |
| [0021](0021-catalog-schema.md) | The catalog: paise checked twice, typed mandatory charges, the listing's state machine, beds capped by occupancy, display points from a CSPRNG and public distances only from them | Accepted |
| [0022](0022-media-pipeline.md) | Media: presigned uploads straight to storage, originals kept private and deleted, every variant re-encoded without metadata, videos remuxed without their location, signed links for private files | Accepted |
| [0023](0023-ops-console.md) | The ops console: `/v1/ops` answers with the whole listing and what may happen next, forms send only what changed, a pin by GPS, coordinates or a map behind `MapProvider` (MapLibre first, tiles as configuration), uploads straight to storage | Accepted |
| [0024](0024-field-verification.md) | Field verification: a visit booked by ops for one agent, reported from the building with the phone's position, the server's time and private photos; only an authorities' notice decides a fail; `verified_only` gates publishing | Accepted |
| [0025](0025-owner-agreement.md) | The owner agreement: versioned texts in the repository, click-wrap acceptance of the exact text (version and SHA-256), append-only evidence with the time, IP and user agent, accepted again for every new version; GSTINs' check character | Accepted |
| [0026](0026-location-privacy.md) | Location privacy: a public read that never loads the exact point, the address or the owner's account; contact details for someone signed in while `hide_owner_contact` is off or once entitled, audited; no phone numbers in public text; a sweep over every public route | Accepted |
| [0027](0027-price-summaries.md) | Price summaries: owned by the search module, one row per category and month for this month and the next six, base rents for now; refreshed through the outbox after every catalog change and nightly per listing; read through `CatalogLookup` | Accepted |
| [0028](0028-search.md) | Search: the search module's read model of live listings kept from the catalog's events, category filters on the price summaries, a lateral lookup per listing, keyset cursors in any order, distances from display points, `SEARCH_INVALID` | Accepted |
| [0029](0029-map-pins.md) | Map pins: compact pins at display points from search's read model, 2,000 at most with `truncated`, cached in Redis for a minute by the area snapped to the zoom's grid, the zoom and the filters, with ETags and 304s; best effort when Redis is down | Accepted |
| [0030](0030-pg-page.md) | The PG page: per-request rendering with its nonce from data cached across visitors, every charge and the deposit upfront, a safety summary from the last passing visit, the area as a circle, fictional sample PGs for local development, `make lighthouse-pg` | Accepted |
| [0031](0031-search-and-map-ui.md) | Search and its map: the URL holds the search (nuqs), the server paints the first page, TanStack Query does the rest; `MapView` with MapLibre (no Google adapter without the founders), pins as buttons, search as I move the map, a split view or a phone's list with a sheet over the map, the map's code only where it shows; `radix-ui` imported member by member, `make lighthouse-search` | Accepted |

0001–0006 were decided in the founders' planning (ARCHITECTURE.md) and written down in build step 0.8. The others were written in the step that made the decision.
