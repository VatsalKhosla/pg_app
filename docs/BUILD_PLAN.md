# Build plan

The order to build the platform in. Each step is sized for one focused Claude Code session (some take two). Work top to bottom; don't start a step until the one before it is done, unless the step says it can run in parallel.

**The two pivots are Phase 4 (dynamic pricing) and Phase 5 (booking).** Phases 0–3 build the ground they stand on, and give the founders something real to show owners and students early.

## How to work through this plan (for Claude Code)

1. Run `/next-step` (or name a step: `/next-step 3.5`).
2. Read the step, the related sections of `docs/ARCHITECTURE.md`, and `docs/PRODUCT_CONTEXT.md` if the step touches money, pricing or booking.
3. Write a short plan: files, migrations, endpoints, tests, risks. Use plan mode for anything touching money, inventory or auth, and wait for approval.
4. Implement with tests. Run `make check`.
5. Tick the box, add a one-line note under the step (what was built, anything deferred), and stop for review.

### Definition of done (applies to every step)

- [ ] Tests written and passing; `make check` is green.
- [ ] Strict types, zero lint warnings, no `any`, no `# type: ignore` without a reason.
- [ ] Migrations reversible and tested up and down.
- [ ] New endpoints in OpenAPI, typed client regenerated, authorization policies and matrix tests updated.
- [ ] Logging and metrics for new flows and jobs; no PII in logs.
- [ ] UI is mobile-first with loading, empty and error states, and is axe-clean.
- [ ] Docs updated: this file (tick + note), ARCHITECTURE.md if the design changed, an ADR for any real decision.

### Milestones

| Milestone       | Phases | What the founders can do                                                                                                                                      |
| --------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A — Show it** | 0–3    | Real verified PGs on a live map, PG pages, visit booking. Use it for the Gate 1 test with owners and students, taking tokens through payment links run by ops |
| **B — Sell it** | 4–6    | Dynamic prices, bed reservations with a protected ₹2,000 token, confirmations, check-in, refunds, owner invoices                                              |
| **C — Run it**  | 7–8    | Owners self-serve; the platform is hardened and load-tested for June–August 2027                                                                              |
| **D — Grow it** | 9      | Rent through the app, reviews, parent sharing, WhatsApp, price suggestions, new cities                                                                        |

## Founders' parallel tasks (Claude Code can't do these)

Start the slow ones in week 1.

- [ ] Incorporate the company (needed for Razorpay, GST, DLT); pick the brand name and buy the domain.
- [ ] **SMS DLT registration**: entity, sender ID and OTP/notification templates. This takes time, so start early.
- [ ] Razorpay account and KYC. Activation needs the site's About, Contact, Pricing, Terms, Privacy and Refund pages (step 3.8). Later, ask Razorpay to enable UPI one-time mandates and Route.
- [ ] Google Maps Platform project, API keys restricted by HTTP referrer and API, billing budget alerts.
- [ ] Accounts: GitHub, Vercel, AWS (Mumbai), Cloudflare, Sentry, PostHog, an email sender (SES or Resend). Google Workspace for staff sign-in.
- [ ] GitHub repository settings (docs/ci.md): the branch ruleset for `main` with the required checks, secret scanning with push protection, Dependabot alerts, and the free Renovate GitHub App for dependency updates.
- [ ] Lawyer: Terms, Privacy notice (DPDP), Refund & Cancellation policy, owner agreement (30% fee, 90-day introduction clause, token set-off), E-Commerce Rules seller-disclosure question (hiding owner contacts), grievance officer. The drafts are in `apps/web/src/content/legal`, with the open questions in brackets.
- [ ] The facts the trust pages state (`apps/web/src/config/company.ts`): the registered name and office address, the phone line a person answers and its hours, the help email, the founders' names, roles and photos, and the grievance officer's name, designation and contact details. A production build waits for them (ADR 0034).
- [ ] CA: GST registration, invoice format, whether the 30% includes GST, accounting for tokens and set-off.
- [ ] Field work for Gate 1: map every PG within 2 km of the first micro-market, sign owners, collect photos and verification data.

---

## Phase 0 — Foundations

- [x] **0.1 Monorepo scaffold.** Create the layout in ARCHITECTURE §4: `apps/api` (uv project), `apps/web` (Next.js, pnpm), `packages/api-client`, `infra/`, root `Makefile`, `.editorconfig`, `.gitignore`, pre-commit hooks (ruff, ruff-format, mypy, eslint, prettier, gitleaks). Add `.env.example` files.
      _Done when_ `make setup`, `make lint` and `make typecheck` succeed on the empty skeleton.
      _Note (2026-10-18):_ uv + Python 3.14, pnpm 12 (pins Node 24 itself), Next 16.4, TypeScript 6.0 and ESLint 9 (newer majors lack plugin support), a 7-day release cooldown and SHA-pinned hooks (ADR 0007). `make check` is lint + typecheck + test-api until test-web (0.5) and client staleness (0.6) exist; the API Dockerfile waits for 0.3.

- [x] **0.2 Local infrastructure.** `infra/docker-compose.yml` with PostGIS (extensions: postgis, btree_gist, pg_trgm, citext), Redis, MinIO (S3) and Mailpit. `make dev` starts infra, API (reload), worker and web together.
      _Done when_ a fresh clone runs `make setup && make dev` and all services are healthy.
      _Note (2026-10-18):_ PostgreSQL 18 + PostGIS 3.6 (own multi-arch image matching RDS), Valkey 8.1 for Redis, SeaweedFS 4.48 for S3 (MinIO no longer publishes images) and Mailpit, with loopback-only ports, digest-pinned images and health checks (ADR 0008). `make dev` runs a minimal API (`/healthz`) and heartbeat worker that 0.3 and 0.4 grow, and switches the web app to webpack on glibc < 2.29; `make health` passed on a fresh clone. Starlette's TestClient now wants `httpx2`; tests use httpx's ASGI transport until the founders approve adding it.

- [x] **0.3 API skeleton.** App factory, pydantic-settings config, structlog JSON logging with request ids, RFC 9457 error handler, `/healthz` and `/readyz` (DB + Redis), CORS allowlist, security headers, OpenTelemetry and Sentry wiring (no-op without DSN), async SQLAlchemy session per request, Alembic initialised with a first migration that enables the extensions, import-linter contracts for the layer rules.
      _Done when_ `/readyz` reports DB and Redis OK, OpenAPI is served, and import-linter passes.
      _Note (2026-10-18):_ All of the above plus a 1 MiB body limit, phone masking in logs and Sentry, and a `system` module as the first layered module (ADR 0009). FastAPI 0.143 traces itself, so only SQLAlchemy and Redis instrumentation were added. 72 tests, including testcontainers runs of migrations up/down/up, `/readyz` and session rollback; import-linter has 3 contracts, proven to catch planted violations. Per-module protected contracts wait until a module has a repository.

- [x] **0.4 Core building blocks.** In `core/`: money (paise, bps, half-up rounding), injectable clock, ids (UUIDv7 public ids, booking codes), idempotency-key middleware and table, outbox table + `worker.py` (claim with SKIP LOCKED, retries with backoff, dead-lettering) + scheduler for periodic jobs, audit log helper, feature flags (table + cache), Redis rate limiter.
      _Done when_ each block has unit/integration tests, including two workers never claiming the same job.
      _Note (2026-10-19):_ All blocks built with 168 tests (Hypothesis for money; testcontainers for the outbox, scheduler, idempotency, audit, flags and limits), including two workers never claiming the same job and exactly-once idempotency under concurrency (ADR 0010). Idempotency lives in the service's transaction instead of middleware, so "work committed" and "response stored" are atomic. The audit log is append-only through a trigger; the restricted database role for the app comes with Phase 8. `SECRET_KEY` is now required (`make env` adds it to existing `.env` files).

- [x] **0.5 Web skeleton.** Next.js App Router, TypeScript strict, Tailwind, shadcn/ui, `src/config/brand.ts`, base layout (header, footer, mobile nav), CSP with nonces in middleware plus security headers, error and not-found pages, Sentry, PostHog stub, next-intl with English messages, PWA manifest.
      _Done when_ Lighthouse mobile ≥ 90 on the placeholder home page and the browser console shows no CSP violations.
      _Note (2026-10-19):_ Lighthouse mobile medians over three fresh-browser runs: 95 performance, 100 accessibility, best practices and SEO (`make lighthouse`). Every Playwright test fails on a console error or CSP violation, and pages pass axe (WCAG 2.2 AA) in light and dark mode (`make e2e`). Next.js 16's `src/proxy.ts` sets a per-request nonce CSP, so pages render per request until step 3.4 weighs hashes for ISR. Translations are typed and resolved on the server, and the phone menu loads on demand: the home page ships about 151 KB gzip of JavaScript. Sentry (minimal data collection) and the analytics stub stay off without keys (ADR 0011).

- [x] **0.6 Typed API client pipeline.** `make gen-client` exports OpenAPI from FastAPI and generates `packages/api-client` (openapi-typescript + openapi-fetch); a small wrapper in `apps/web/src/lib/api` handles cookies on the server, errors and problem+json.
      _Done when_ the web home page calls `/healthz` through the typed client, and CI fails if the generated client is stale.
      _Note (2026-10-19):_ The home page streams the API's liveness ("Online" with the API up, "Unavailable" without), and the API's log line carries the page's request id. `make check-client` (in `make check`) fails on drift, shown by a changed route summary. Every operation now declares its 4XX/5XX errors as problem+json, and FastAPI's unused `HTTPValidationError` is gone. Server calls forward only allow-listed API cookies (none until step 1.1) and time out after 3 s (ADR 0012).

- [x] **0.7 CI and security scanning.** GitHub Actions: `ci.yml` (lint, typecheck, API tests with a PostGIS service, web unit tests, web build, client staleness, oasdiff), `security.yml` (CodeQL, gitleaks, pip-audit, pnpm audit, Trivy on the API image). Renovate or Dependabot. Actions pinned by SHA. Branch protection documented.
      _Done when_ a pull request shows every check green.
      _Note (2026-10-19):_ All 13 checks passed on their first run, on the push of 7f64411 ([CI](https://github.com/VatsalKhosla/pg_app/actions/runs/39217998691), [Security](https://github.com/VatsalKhosla/pg_app/actions/runs/39217998658)). Pull requests run the same two workflows; the only difference is that oasdiff compares against the target branch. No pull request was opened, because `gh` isn't signed in here, so the first one will confirm the pull request view. Beyond the plan: Playwright E2E, workflow linting (actionlint, zizmor) and the API image (`apps/api/Dockerfile`, non-root, pip removed). Renovate was chosen over Dependabot, which lacks pnpm 12 and uv 0.13 support (ADR 0013). Branch protection is documented in docs/ci.md, and setting it up is a founders' task.

- [x] **0.8 ADRs and runbook stubs.** `docs/adr/0001` modular monolith, `0002` FastAPI + Next.js, `0003` PostgreSQL + PostGIS + exclusion constraints, `0004` money in paise and the ledger, `0005` outbox jobs instead of a broker, `0006` map provider behind an interface. Runbook stubs for webhook failures, dead jobs and restoring from a backup.
      _Done when_ the files exist and match ARCHITECTURE.md.
      _Note (2026-10-19):_ ADRs 0001–0006 record the planning decisions, each checked against ARCHITECTURE.md and linked to the code that now enforces it. An index (docs/adr/README.md) lists all 13 ADRs. The runbooks are in docs/runbooks/. The dead-jobs one is already usable (queries and a safe requeue against the real `outbox_jobs` columns). The webhook and restore ones mark what steps 6.x and 8.x must fill in.

## Phase 1 — Identity and access

- [x] **1.1 Users, roles, sessions.** Tables from ARCHITECTURE §6; opaque session tokens (hash stored), cookie flags, rotation, logout, log out everywhere, session list, CSRF double-submit protection.
      _Done when_ tests check cookie flags, rotation, revocation and CSRF rejection.
      _Note (2026-10-19):_ Built as the `identity` module, with `users`, `user_roles` and `sessions` tables. 16 integration tests cover:
  - cookie flags and the parent domain;
  - sliding 30-day and absolute 12-hour expiry;
  - rotation, and the replaced session ending at sign-in;
  - logout, log out everywhere, ending one device, and 404 for another user's session;
  - suspension, and retention;
  - CSRF rejection, including a token bound to another session.

  CSRF is a signed double-submit token, bound to the session and enforced app-wide. A test sweeps every unsafe route; FastAPI 0.143 nests included routers, so the sweep walks `iter_route_contexts` (ADR 0014). Sign-in itself arrives with OTP in 1.2.

- [x] **1.2 Phone OTP login.** Request and verify endpoints; HMAC-stored codes; expiry, attempt limits, resend cooldown, per-phone and per-IP limits; Turnstile check; `OtpSender` port with a console adapter (dev) and an adapter for the founders' chosen DLT provider (ask before picking).
      _Done when_ login works end to end in dev, and abuse tests pass (sixth attempt locked, rate limit returns 429, expired code rejected).
      _Note (2026-10-19):_ Codes are HMACs bound to their challenge. Abuse controls run in order: per-IP limits, then Turnstile (bound to the form's action and the web app's hostnames), then a per-phone cooldown under an advisory lock, then 5 codes per phone per hour, then 5 tries per code. 17 integration tests cover:
  - sign-in end to end, and the same account on the next sign-in;
  - the sixth attempt locked, and expired and replaced codes;
  - the cooldown's and the hourly limit's 429s;
  - an immediate retry after a failed SMS;
  - suspended accounts, and staff roles dropped from phone sessions;
  - hashed storage, and 7-day retention.

  A real sign-in against the local API worked, with the code read from the console sender's log. Deployed environments run `OTP_SENDER=unavailable` (503) until the founders choose the DLT SMS provider, which is a paid vendor (ADR 0015).

- [x] **1.3 Staff sign-in.** Google OIDC restricted to an allowed domain or email list (OTP + TOTP fallback); staff roles; 12-hour sessions.
      _Done when_ a non-allowed Google account is refused and staff routes reject non-staff.
      _Note (2026-10-19):_ Only an operator makes someone staff (`python -m app.manage staff …`, audited); a staff session lasts 12 hours and works only while its user is staff.
  - Google sign-in is OIDC with PKCE. The sign-in keeps no server state (a `__Host-` cookie holds a login id the state, nonce and verifier are derived from). The ID token's RS256 signature and claims are checked. Accounts are allowed by Workspace domain (the `hd` claim) or by exact address, and linked by Google's `sub`.
  - The fallback is a phone code, then a TOTP code from an authenticator app enrolled from the command line. The secrets are derived from `SECRET_KEY`, never stored.
  - `GET /v1/admin/staff` (admins only, cursor-paginated) is the first staff route: 401 without a session, 403 for phone sessions and non-admin staff.

  20 integration tests cover the done criterion and the edges: tampered, stale, replayed and other-browser sign-ins; replaced Google accounts; codes reused or over the limit; constant queries per page; and the operator commands. Google itself waits for the founders' OAuth client (docs/runbooks/staff-access.md, ADR 0016).

- [x] **1.4 Policies and the authorization matrix.** `policies.py` pattern; FastAPI dependencies for the current actor; a matrix test that enumerates every route × role and asserts the expected status (404 for other users' objects).
      _Done when_ the matrix runs in CI and fails if a new route lacks an entry.
      _Note (2026-10-19):_ `CurrentActor` and `OptionalActor` now come from `app.core.current_actor`. The identity module supplies the session check through `app.state.authenticate`, so other modules never import identity. Policy functions are pure `can_…` functions; a missing role answers 403 `FORBIDDEN`, and another user's record 404.

  The matrix (`apps/api/tests/authorization.py`) is written by hand and covers 14 routes against 8 callers: anonymous, student, parent, owner, an admin signed in by phone, and field agent, ops and admin staff sessions. A unit test fails when a route has no entry (checked with a stand-in route), and an integration test makes all 112 calls (ADR 0017).

- [x] **1.5 Consent and data requests (DPDP).** Versioned privacy notice acceptance at signup, `consents` table, data export and deletion request endpoints with an ops queue, retention job skeleton.
      _Done when_ signup can't complete without consent, and an export request produces a downloadable file for that user only.
      _Note (2026-10-19):_
  - Consent is recorded per purpose (`account` required, `marketing` optional) and per `PRIVACY_NOTICE_VERSION`. A first sign-in without it answers `CONSENT_REQUIRED`, and the code stays usable. `/v1/me` says `consentRequired` when the notice changes.
  - Exports are built by an outbox job from every module's part (listed in `app/jobs.py`). They download as JSON for 7 days, for their owner only: 404 for anyone else, staff included.
  - Deletions wait in an audited ops queue. One daily retention job runs every module's rules.

  Tests cover signing up with and without consent, a changed notice, withdrawal, the export through the real worker, the queue, and retention. The matrix now has 23 routes.

  Waiting for the founders (ADR 0018): the notice's text (step 3.8, with a lawyer), what a deletion erases versus keeps, and the remaining retention periods.

- [x] **1.6 Web auth flows.** Phone → OTP → profile (name, college or workplace, gender for PG eligibility, with consent); session-aware header; protected route handling; staff login page.
      _Done when_ Playwright covers login, logout and protected-route redirects on mobile viewport.
      _Note (2026-10-19):_
  - `/sign-in` runs phone, code, consent (only when the API asks; nothing pre-ticked), then profile. `/account` has the profile, the offers toggle, data requests and sign-out. `/staff/sign-in` offers Google, or phone plus authenticator.
  - The header knows the session. The proxy and the pages both guard `/account` and `/staff`, and `next` can't leave the site.
  - The API gained `PATCH /v1/me` (college or workplace, and gender, optional and used only for PG eligibility).

  The browser tests now run against the real API on its own database (`scripts/e2e-api.sh`), on phone and desktop. They cover sign-up, sign-out, the resend wait, a returning sign-in and the redirects, and they caught Zod's eval probe breaking the CSP (now jitless).

  The generated client is no longer readonly: openapi-fetch's `Readable` breaks readonly arrays (ADR 0019).

## Phase 2 — Catalog and ops console

- [x] **2.1 Geo seed.** Cities, localities (start with North Campus, Satya Niketan and Old Rajinder Nagar areas; then Gurugram and Noida hubs), campuses and metro stations. Source coordinates from OpenStreetMap (with attribution) or official sources; **never invent coordinates** — if unsure, leave the row out and list it in the step note. Idempotent seed command.
      _Done when_ `make seed` loads geo data and a distance query from a campus returns sensible results.
      _Note (2026-10-21):_
  - **Seeded:** 3 cities (Delhi, Gurugram, Noida); 13 localities around North Campus and Satya Niketan, 10 with boundaries; 19 campuses (North Campus as a whole, 11 North Campus colleges and departments, 7 South Campus colleges); 14 metro stations on 6 lines.
  - **Sources:** a hand-written manifest names each place's OpenStreetMap element, and `make geo-refresh` fetches the coordinates through Nominatim and the metro lines from Wikidata, under both services' usage policies. No coordinate was typed in (ADR 0020).
  - **Left out, for want of a source:**
    - Old Rajinder Nagar: OpenStreetMap has no place, boundary or address by that name. Its stations, Rajendra Place and Karol Bagh, are in.
    - The Gurugram and Noida hubs: not named yet.
    - South Campus as a whole: no single feature covers it, so its colleges stand for it.
  - **Loading:** `make seed` loads the data idempotently. It writes only rows that changed, and audits a load that changes something.
  - **API:** public `GET /v1/cities`, `/v1/localities`, `/v1/campuses`, `/v1/campuses/{slug}` and `/v1/metro-stations`.
  - **Distances:** every campus's nearest metro station is 245 m to 1.5 km away, and the tests check each one against an independent haversine distance.

- [x] **2.2 Catalog schema.** Owners, properties (exact and display location, gender policy, meals, verification and licence status, society permission, status), room categories (the pricing unit, with base rent, owner min/max, deposit, mandatory charges), rooms, beds, amenities. Constraints and indexes from ARCHITECTURE §6.
      _Done when_ migrations apply cleanly and repository tests cover create, update, publish and geo queries.
      _Note (2026-10-21):_
  - **The catalog module:** owners, properties, room categories, rooms, beds and amenities (seeded by a separate data migration).
  - **Money:** integer paise, checked by the domain and again by named database CHECKs (base > 0, owner min ≤ base ≤ owner max, deposit ≥ 0). Mandatory charges are typed: monthly, metered with a monthly estimate, or one-time.
  - **A listing's life:** draft → published ⇄ paused, any → delisted, delisted → draft. Publishing needs an active category with an active bed; step 2.5 adds the verification gate.
  - **Rooms** take no more beds than their occupancy, under a row lock.
  - **Display points** are made from a CSPRNG and moved only when the exact point moves. Public geo queries measure from them, to prevent trilateration (ADR 0021).
  - **Shared geometry** moved to `app.core.geometry` and `app.core.postgis`.
  - **No routes yet:** the ops console (2.4) adds them.

- [x] **2.3 Media pipeline.** Presigned uploads, worker processing (magic bytes, EXIF/GPS stripping, WebP/AVIF variants, video poster), moderation status, `verified_capture` flag, CDN and signed URLs.
      _Done when_ an uploaded phone photo comes out with no GPS EXIF in all variants, and a private document needs a signed URL.
      _Note (2026-10-21):_
  - **Uploads:** the browser posts files straight to the private bucket through presigned POSTs, and storage itself enforces the type and the size.
  - **The worker:** checks the real type, then re-encodes every photo variant (WebP and AVIF at four sizes) without metadata. Videos are remuxed without their location, with a clean poster. The original is deleted afterwards.
  - **Serving:** listing media from the public bucket (the CDN), private files only through 5-minute signed links.
  - **Tested end to end against SeaweedFS:** no EXIF, GPS or XMP in any variant; no location in videos; private files 403 without a signature.
  - **Dependencies:** Pillow, PyAV and boto3, behind an `ObjectStorage` port.
  - **Not accepted:** HEIC (iPhones send JPEG when it isn't offered).
  - **Local buckets:** `make seed` creates them (ADR 0022).

- [x] **2.4 Ops console: listings.** `/ops` screens to create and edit properties, room categories, rooms and beds; pin picker (drag the pin, or use the agent's GPS); amenities and house rules; photo and video upload with ordering; publish and unpause; full audit trail.
      _Done when_ ops can create a complete listing from a phone in under 10 minutes.
      _Note (2026-10-25):_
  - **API:** `/v1/ops/*` for ops and admins in a staff session. Owners are added by phone. A new draft lists listings pinned within 30 m as possible duplicates. Every change answers with the whole listing, including the statuses it can move to (`nextStatuses`) and what stops it being published.
  - **Pages:** listings by status or search; a new listing (owner, locality, building); and the listing's page (status, details, rooms and beds with their charges, amenities, photos and videos, history).
  - **Forms** send only what changed, so the audit history says what changed. The API's field errors show next to their fields. The browser only turns typed rupees into paise.
  - **The pin:** GPS, coordinates or a map. The map is behind `MapProvider`: MapLibre 6 with raster tiles, OpenStreetMap's for local development only. A deployed site has no map until the founders choose a provider (ADR 0023).
  - **Photos and videos** go straight to storage, join the listing when the worker has prepared them, and are ordered with the first as the cover.
  - **Tested on a phone:** the browser test signs in as ops with an authenticator, builds and publishes a complete listing, photo included, in under a minute, and axe checks the pages.

- [x] **2.5 Field verification workflow.** Mobile checklist for agents: building age and condition, cracks, exits, extinguishers, CCTV, warden, women's-safety features, licence number, society permission; GPS and time captured; result sets `verification_status`. Unverified properties can't be published while `verified_only` is the default.
      _Done when_ a property moves unverified → scheduled → verified with a stored report and photos.
      _Note (2026-10-26):_
  - **Visits:** ops book a visit for one field agent; the property is then `scheduled`. A passed report verifies it and a failed one rejects it; a cancelled visit puts the status back. Ops can suspend a verification, and a failed or suspended listing that is live is paused at once.
  - **The report:** every checklist question answered, the phone's position with its accuracy, the server's time, the distance from the pin (the agent may move the pin there), and at least one private photo. The only rules that decide it: a building with an authorities' notice can't pass, and a failed visit says why (ADR 0024).
  - **Publishing:** needs a passed verification while `verified_only` is on, the default.
  - **Screens:** a Verification section on the ops listing page, and `/field/visits` for agents.
  - **Tested end to end on phones:** ops book the visit, the agent reports from another phone with a photo, then ops publish. The API tests cover every rule and each role's access, and the authorization matrix covers the 8 new routes.
  - **Local development:** `make dev-staff` and `make staff-code` sign staff in without an authenticator app.

- [x] **2.6 Owner records and agreements.** Owner profiles, business name, GSTIN (optional), versioned agreement text with click-wrap acceptance (version, document hash, timestamp, IP, user agent).
      _Done when_ acceptance is recorded and visible in ops, and a new agreement version asks owners to accept again.
      _Note (2026-10-27):_
  - **The agreement:** one Markdown file per version in the repository; `OWNER_AGREEMENT_VERSION` picks the current one, and production refuses a draft. `draft-1` is a DRAFT for the founders and a lawyer to review. An acceptance names the version and the SHA-256 of the text shown, or is refused (`409 AGREEMENT_CHANGED`). Each one keeps the time, IP and user agent in an append-only table, and goes into the audit log and the owner's data export (ADR 0025).
  - **Owners:** a new version sends every owner back to the agreement. Ops edit owners' details, and GSTINs must pass their check character. An account ops made now asks for privacy consent at its person's first sign-in.
  - **Web:** the owner area (`/owner`, with the agreement and a click-wrap whose box starts unticked); the console's Owners list and each owner's page with every acceptance; runbook `docs/runbooks/owner-agreement.md`.

- [x] **2.7 Location privacy and contact hiding.** Generate and store `display_location` (random 80–150 m offset, stable); public APIs expose only display data; the owner phone and exact address are hidden behind `hide_owner_contact`.
      _Done when_ tests prove public endpoints never return the exact point, the address line or the owner's phone.
      _Note (2026-10-27):_
  - **The public read:** `GET /v1/properties/{slug}` gives a live listing with its display point (made in step 2.2, stable unless the pin moves). It reads neither the exact point, nor the address, nor the owner's account, so it can't return them. Not live, or not verified while `verified_only` is on, means 404.
  - **The contact details:** `GET /v1/properties/{slug}/contact` gives the phone, address and exact point to someone signed in, while `hide_owner_contact` is off or once entitled. Visits (3.7) and bookings (Phase 5) will entitle; until then nobody is. Otherwise `403 CONTACT_HIDDEN`. Each look is audited and rate-limited.
  - **Proof:** a sweep calls every public route, as anyone and as a student, and fails on the address, the phone or any point within 80 m of the building; a planted leak was caught. Public listing text can't carry a phone number (ADR 0026).

## Phase 3 — Discovery: search, PG pages, map, visits → **Milestone A**

- [x] **3.1 Price summaries (base-rent version).** `property_price_summaries` for the next six months, filled from base rents for now (Phase 4 switches it to the engine). Recomputed on catalog changes through the outbox.
      _Done when_ summaries refresh within a minute of a rent change.
      _Note (2026-10-27):_
  - **The table:** the new search module owns it, with one row per room category with a bed to sell and month, for this month and the next six (India's calendar). Each row has the base rent as its range and the active beds as free.
  - **Refreshes:** `catalog.inventory_changed`, written with every category, room or bed change, refreshes that listing within seconds; a test drives a rent change through the real worker. Every night at 00:30 IST each listing is queued once more, so the months roll forward. A data migration fills the listings that already exist. Search reads rents through `CatalogLookup`, not the catalog's tables (ADR 0027).

- [x] **3.2 Search API.** Filters, sorting, text search (trigram + full-text) and cursor pagination per ARCHITECTURE §10.1, using summaries for budget and price sort; distance to the chosen campus and nearest metro.
      _Done when_ integration tests cover each filter, and p95 < 300 ms on a seeded set of 3,000 properties.
      _Note (2026-10-27):_
  - **The API:** `GET /v1/search/properties` covers every parameter in §10.1 and refuses any other. It reads the search module's own entries for live listings, kept from the catalog's events, and the price summaries, which now carry each category's features. Distances to the campus and the nearest metro are measured from display points. Free beds show as a bucket, and cursors carry their order. A search that can't be answered gets `422 SEARCH_INVALID` (ADR 0028).
  - **Proof:** integration tests cover each filter, sorting, paging and the refresh after a change. Over 3,000 seeded fictional listings, 253 searches of every kind took a median of 29 ms and a p95 of 65 ms. A first query was 365 ms on map-area searches until each listing's month was looked up laterally.

- [x] **3.3 Map pins API.** Bbox + filters → compact pins with price ranges from summaries; Redis cache with ETags; 2,000-pin cap.
      _Done when_ a pan across NCR returns correct pins, and repeated calls hit the cache.
      _Note (2026-10-27):_
  - **The API:** `GET /v1/map/pins` takes the map's area and zoom and search's filters, and gives pins at display points with the month's price range, at most 2,000 (`truncated` says there were more). The area is snapped outwards to the zoom's grid, so small pans repeat the same request (ADR 0029).
  - **The cache:** answers are kept in Redis for a minute, as the exact JSON sent, with an ETag; `If-None-Match` gets a 304. While Redis is down, pins come from the database.
  - **Proof:** a test pans a map area across Delhi, from South Campus to North Campus, and finds each fictional listing inside the snapped areas, at its display point. A repeated request runs no database query at all.

- [x] **3.4 PG detail page.** ISR page per ARCHITECTURE §10.6: gallery with verified-photo labels, video, safety summary, room categories with prices (base rent until Phase 4), deposit and mandatory charges shown upfront, amenities, rules, small embedded map at the display location, distances, owner business name, "Book a visit" CTA.
      _Done when_ the page passes Lighthouse mobile ≥ 85 and shows no hidden charges.
      _Note (2026-10-27):_
  - **The page:** `/pg/[slug]` renders per request with its CSP nonce, from listing data cached for a minute across visitors. It shows photos as `<picture>` elements (with verified-photo labels), every room's rent, deposit and charges with their totals, the safety summary from the last passed visit, amenities, rules, and the area as a circle on a lazily loaded map with distances to campuses and metro stations. "Book a visit" leads to a page that says it opens soon (step 3.7) (ADR 0030).
  - **Sample PGs:** `make seed` adds six fictional live PGs with generated photos, built through the real services; it refuses anywhere deployed.
  - **Proof:** a browser test checks every amount against the API's listing. `make lighthouse-pg` (mobile) scored performance 90 and 100 in every other category.

- [x] **3.5 Search + map UI (the showcase).** Split view on desktop; list-first on mobile with a map toggle and draggable bottom sheet; price pins with ranges; clustering; "search as I move the map"; filters in the URL (nuqs); hover sync between cards and pins; campus rings and metro overlay; NCR bounds lock; lazy-loaded map behind the `MapProvider` interface (Google adapter first); skeletons and empty states; keyboard-accessible pins.
      _Done when_ Playwright covers filter → pan → select pin → open PG page on mobile and desktop, and the map bundle loads only on the map view.
      _Note (2026-10-28):_
  - **The page:** `/search` keeps the search in the URL (nuqs) and renders its first page of results on the server, so a shared link shows them before any script runs. After that the browser asks the API through TanStack Query and cancels requests it no longer needs. A desktop shows the list beside the map. A phone shows the list first, then the map on request, with the list in a bottom sheet that can be dragged or stepped by tapping its handle. The header, the footer and the home page link to it (ADR 0031).
  - **The map:** `MapView` joins the `MapProvider` interface, with a MapLibre adapter.
    - Price pins are buttons, and clusters show their count and lowest price.
    - The chosen campus gets its name and 1 km and 2 km rings; campuses and metro stations are dots. The map is locked to NCR.
    - Search as I move the map is on to begin with. Cards and pins light up together, and a selected pin opens a preview.
    - The map's code loads only where the map shows.
  - **Speed:** `radix-ui` had shipped every primitive on every page. It's now imported member by member, so the home page's client JavaScript fell from 228 KB to 152 KB gzipped, and search ships 197 KB. `make lighthouse-search` (mobile) scored 89 for performance and 100 in every other category.
  - **Deferred:** a Google adapter (a paid vendor, so the founders' choice) and locality outlines (localities have no boundaries yet).
  - **Proof:** a browser test runs filter → pan → select pin → open the PG's page on a phone and a desktop. It checks that a phone's list view fetches none of the map's code, and runs axe on the way.

- [x] **3.6 Landing pages and SEO.** `/pg-near/[campus]`, `/pg-in/[locality]`, JSON-LD, canonical URLs, sitemap, robots, dynamic OG images, on-demand revalidation from the API.
      _Done when_ Google's Rich Results Test validates a PG page and the sitemap lists every published PG.
      _Note (2026-10-28):_
  - **Landing pages:** a page for each campus and locality, rendered on the server from `GET /v1/search/places` (where the verified live PGs are, with counts and the month's rents) and search's first page. Each has its PGs, the numbers in words, a way onto the map, the places nearby and four questions answered from live data. A place without PGs says so and is `noindex`. The home page links to the places with the most PGs (ADR 0032).
  - **Search engines:**
    - JSON-LD: `LodgingBusiness` with an `Offer` per room on PG pages, with the locality and display point but never the address; `ItemList`, `BreadcrumbList` and `FAQPage` on landing pages; `Organization` on the home page.
    - Canonical URLs everywhere, Open Graph images drawn from live data, and a sitemap of every PG the public may see, with each listing's last change (`GET /v1/search/sitemap`). robots.txt names it.
  - **Revalidation:** after every catalog event the worker posts the listing's cache tags to the web app, signed with `REVALIDATE_SECRET`, and the next visit fetches fresh data.
  - **Proof:** browser tests check the structured data, the sitemap against the API's list, the Open Graph image, and a listing edit showing on its cached page within seconds.
  - **Deferred:** Google's Rich Results Test itself needs a public URL, so it runs on staging once deployed.

- [x] **3.7 Visits.** Request with up to three slots; ops scheduling and agent assignment; SMS confirmations and reminders (T−24 h, T−2 h); agent check-in with GPS and time (the visit log); outcome capture; limits and rate limits. The exact address is revealed to the student once a visit is scheduled.
      _Done when_ a student books a visit on a phone, the agent checks in, and ops see the visit log.
      _Note (2026-10-29):_
  - **Students** ask for a visit at up to three times (on the hour or half past, 9 am to 7 pm, from 3 hours to 2 weeks ahead) and see and cancel their visits. There are at most 5 open at once, one per PG, and 10 requests a day.
  - **Ops** book one of those times or another, with a field agent. The student is texted, and reminded 24 hours and 2 hours before, through the outbox; a cancelled or rebooked visit's old texts don't go.
  - **Field agents** check in from their phone at the building: the server's time, the position, its accuracy and the distance from the exact point make the visit log. They then record how it went.
  - **The address:** a booked visit lets the student see the address and the owner's phone, through the audited contact endpoint (ADR 0033).
  - **Deferred:** the SMS provider is the founders' choice. Until then texts go to the log locally and are off when deployed.
  - **Proof:** a browser test on phones: a student signs up and asks, ops book it with an agent, the agent checks in by GPS and records the outcome, and ops see the log.

- [x] **3.8 Trust and legal pages.** About (founders' names and faces), Contact (a phone line staffed by a person), Pricing ("students pay nothing; owners pay a one-time 30% placement fee"), Terms, Privacy notice, Refund & Cancellation policy, Grievance officer with a ticket form (acknowledge ≤ 48 h, resolve ≤ 1 month), "How your token is protected". Mark legal texts **DRAFT — needs lawyer review**.
      _Done when_ every page is linked from the footer and the grievance form issues a ticket number.
      _Note (2026-10-29):_
  - **Pages:** About, Contact, Pricing, How your token is protected, Terms, Privacy notice, Refund and cancellation policy, and Grievances, all in the footer's Company and Policies groups.
  - **Placeholders:** facts only the founders can give (names and photos, the registered name and address, the phone line, the grievance officer) show as visible placeholders from `src/config/company.ts`. Those pages stay out of search engines meanwhile.
  - **Legal texts** are DRAFTs, with their open legal questions in brackets.
  - **Live figures:** fee rates, the token and the cancellation terms come from the API's new `GET /v1/policies`, never from the pages.
  - **Complaints:** anyone may complain (signed out, with the human check) and gets a `GR-` ticket number. Ops acknowledge within 48 hours and resolve within a month in `/ops/grievances`, with late ones marked; signed-in complainants are texted and see the replies.
  - **Launch guard:** a production build refuses placeholders and drafts (ADR 0034).
  - **Proof:** browser tests follow every footer link with axe checks, and take a complaint from the form to its ticket number, then through ops acknowledging and resolving it.

- [x] **3.9 Analytics and install.** Funnel events (search → PG view → visit request → visit done → reservation), PII-masked; PWA installability; web-vitals reporting.
      _Done when_ the funnel shows in PostHog from a staging run and the site installs on Android Chrome.
      _Note (2026-10-29):_
  - **Browser events:** searches, PG views and visit requests, plus each page's web vitals, go to the site's own `/api/events`. It passes them on to PostHog personless and without the visitor's IP, after strict checks.
  - **What they carry:** a random id that lasts only while the tab is open, never a name, number, typed words or map coordinates. Do Not Track and Global Privacy Control turn them off.
  - **Later steps:** "visit done" comes from the API, under the id the student's tab asked with; "reservation" joins with booking (Phase 5).
  - **Install:** the manifest already meets Chrome's install criteria; a browser test asks Chromium.
  - **Deferred:** the founders' PostHog account, its region and the staging run, and the lawyer's view on consent (ADR 0035).
  - **Proof:** a browser test sees one anonymous journey from search to visit done arrive, in order, at a stand-in PostHog.

**Milestone A check**: a student can find a verified PG on the map, see honest prices, and book a visit from a phone; ops can create and verify listings and run visits; security baseline (headers, CSRF, rate limits, authorization matrix) passes. Ship to production and tell the founders.

## Phase 4 — Dynamic pricing engine (**pivot 1**)

- [x] **4.1 Policies, caps and rent bands.** Tables `fee_policies`, `booking_policies`, `pricing_caps`, `rent_bands` with an admin UI and audit log; seed defaults from PRODUCT_CONTEXT §9 (fee 30% of listed rent, GST 18% exclusive, token ₹2,000, hold 15 min, free cancel 7 days, check window 24 h, confirm deadline 12 h, late cancel `refund_full`, one active hold per user, caps +40% / −30%, rounding ₹50). No official bands seeded.
      _Done when_ every default is editable by admins only and every change is audited.
      _Note (2026-10-30):_
  - **Tables:** `fee_policies`, `booking_policies`, `pricing_caps` and `rent_bands` hold versions in force from a moment until the next. Exclusion constraints keep versions from overlapping, per locality and occupancy for bands.
  - **Defaults:** PRODUCT_CONTEXT §9's are seeded by a data migration; no band is seeded.
  - **Admins only:** they change each policy from now on in `/admin/policies` and set or end bands in `/admin/rent-bands`. Every change is audited with before, after and a note.
  - **Limits:** the founders' rules (a ₹1,000–2,000 token, the fee on the listed rent, `refund_full` until Route) refuse what they don't allow.
  - **Public pages:** `GET /v1/policies` reads the tables, and a change refreshes the public pages that state them (ADR 0036).
  - **Proof:** API tests for each change, refusal and two admins at once, plus a browser test of an admin changing a cap and setting and ending a band.

- [x] **4.2 Pricing engine (pure).** `pricing/domain/engine.py` per ARCHITECTURE §8: rule kinds with typed params, the algorithm, clamping, rounding, fee/GST/token maths, explainable adjustments, `engine_version`. Hypothesis tests for every invariant in §8.8 (≥ 10,000 cases in CI) plus table tests including the worked example.
      _Done when_ all invariants hold and branch coverage of the engine is ≥ 95%.
      _Note (2026-10-30):_
  - **Engine:** `quote(context)` is pure and typed. It handles the six rule kinds (with their own checks), caps, owner and band bounds (impossible ones refused), rounding kept inside the bounds, the fee on the listed rent only, both GST modes, the token and an explanation of each adjustment and clamp (ADR 0037).
  - **Proof:** the worked example and every edge by hand, plus every §8.8 invariant as a Hypothesis property (10,000 cases each in CI).
  - **Coverage gate:** `make coverage-money`, now in `make check` and CI, holds the pricing domain at 95% branch coverage; it stands at 99.7%.

- [x] **4.3 Rule sets and versioning.** Draft → active → archived; activation is atomic, creates an immutable version and is audited; validation (overlapping seasons, band conflicts, impossible bounds) returns readable errors.
      _Done when_ activating a new version never changes existing quotes or bookings (tested).
      _Note (2026-10-30):_
  - **Sets:** each PG has at most one draft and one active set. A draft starts as a copy of the set in force, and only a draft's rules change.
  - **Activation:** it checks the set, then archives the set in force and activates the draft in one transaction, audited (ADR 0038).
  - **Checks:** overlapping seasons or overrides for a category, overrides outside the band, bounds that leave no rent, and rules for room categories the PG doesn't have. Each is a readable `RULE_SET_INVALID` problem, shown on the draft before activation too.
  - **Immutability:** database triggers refuse any change to a set once it has been in force.
  - **Proof:** a set's prices are the same before and after the next version goes in, its rules read back unchanged, and the database refuses edits behind the API's back. Step 4.4 adds the same check on stored quotes.

- [x] **4.4 Quotes API.** `POST /v1/quotes` and `GET /v1/quotes/{id}`: occupancy from real allocations (HELD excluded), persisted breakdown, 30-minute expiry, inputs hash, human explanation string. Rate-limited.
      _Done when_ the quote's numbers equal the engine's for the same inputs, and expired quotes are refused by later steps.
      _Note (2026-10-30):_
  - **Quoting:** `POST /v1/quotes` prices a room for a move-in (today to 120 days) and a stay (1 to 36 months) with the engine. It uses the policies in force, the PG's active rule set, the band and the owner's bounds.
  - **Stored:** the breakdown, the explanation line, the deposit and every charge, the versions that priced it and a SHA-256 of all inputs. A trigger refuses any change (ADR 0039).
  - **Life:** a quote stands 30 minutes; after that `usable` answers `QUOTE_EXPIRED` for Phase 5's booking. Quotes are rate-limited, and the owner's fee is never shown to students.
  - **Occupancy:** behind a `BedsTaken` port, zero until Phase 5's allocations exist.
  - **Proof:** a test rebuilds the inputs from the database, and the engine gives the stored numbers and digest. A new rule version leaves an old quote unchanged.

- [x] **4.5 Price calendar and honest urgency.** Calendar endpoint (weekly move-ins, 12 weeks, cached) and UI on the PG page ("Move in by 15 Jun: ₹9,500 · from 1 Jul: ₹11,000"); "only N beds left" only from real availability (N ≤ 3); a "price fixed for your whole stay" badge; quotes show the full breakdown.
      _Done when_ tests prove every urgency message is backed by data, and the PG page shows quote-consistent prices.
      _Note (2026-10-30):_
  - **Calendar:** `GET /v1/properties/{slug}/price-calendar` gives each room's rent for 12 weekly move-ins (to the booking horizon) as a quote would say, with its free beds. It's cached five minutes (ADR 0040).
  - **PG page:** it reads only that calendar: the soonest rent with a "price fixed for your whole stay" badge, "Move in by …: ₹A · from …: ₹B" only where the calendar changes, and "Only N beds left" only for 1 to 3 free beds. "Check your price" shows a quote's full breakdown.
  - **Proof:** each calendar week equals a quote (API test); changes and scarcity come only from the data (unit tests); the page shows exactly the calendar's numbers, and the checker a quote's (browser test).

- [x] **4.6 Pricing editor (ops first).** Rule list, add/edit forms per kind, live preview (pick a move-in date and stay → breakdown), 12-week price chart, band and median shown, activate with confirmation. Owners get the same editor in Phase 7.
      _Done when_ ops can set a July peak rule and an early-bird rule and see both in preview, on the calendar and on the map.
      _Note (2026-10-30):_
  - **API:** a version's preview (any move-in up to a year ahead, the owner's fee included, nothing stored), its weekly chart with the limits that held each week back, and the market beside a PG's rents: each room's band, the locality's median listed rent and the caps (ADR 0041). All are built the way quotes are.
  - **Editor:** `/ops/listings/{id}/pricing` has the versions, a draft's rules with a form per kind, its problems, the market, a live preview, and one small chart per room with a table. Putting a draft in force or discarding it needs a confirmation.
  - **Proof:** before activation the version in force previews as today's quote, and after it the draft's preview equals the new quote. The chart of the version in force equals the PG page's calendar. A July peak and an early-bird both show in next July's preview and, once in force, on the PG page's calendar (API tests). A browser test drives the editor end to end.
  - **The map:** it shows engine prices from step 4.7, which switches its summaries to the engine; that step's test repeats the July scenario on the map.

- [ ] **4.7 Summaries from the engine.** Switch `property_price_summaries` to engine output per month; recompute on `pricing.rules_changed`, allocation changes and band changes.
      _Done when_ map pins and search budgets match PG-page prices for the same month.

- [ ] **4.8 Integrity alerts.** Ops alerts when listed rent is > 25% below the locality median, when clamps fire on > 20% of a property's weekly quotes, and on frequent rule churn.
      _Done when_ seeded scenarios trigger each alert exactly once.

## Phase 5 — Booking system (**pivot 2**)

- [ ] **5.1 Inventory allocations and availability.** The `inventory_allocations` table with the exclusion constraint; availability queries per category and period; offline-tenant and maintenance blocks (ops now, owners in Phase 7).
      _Done when_ overlapping active allocations are impossible (constraint test) and availability numbers match allocations.

- [ ] **5.2 Booking state machine (pure).** Transition table per ARCHITECTURE §7.2 with guards and side-effect descriptors; exhaustive tests over every (state, event) pair; property tests that random event sequences never break invariants (e.g., no money earned before ACTIVE).
      _Done when_ every allowed transition is tested and every other pair is rejected with `INVALID_TRANSITION`.

- [ ] **5.3 Holds.** `POST /v1/bookings` (quote id + Idempotency-Key) per §7.3: locking, stale-hold expiry, bed choice, constraint as the last line of defence, active-hold limit, rate limits, error codes.
      _Done when_ the 50-concurrent-requests test yields exactly one hold, and replaying the same Idempotency-Key returns the same response.

- [ ] **5.4 Confirmation flow.** Owner/ops confirm or reject; `instant_confirm` per property; confirmation deadline job → REJECTED (refund hooks are stubs until Phase 6); notifications.
      _Done when_ all three paths work end to end with notifications.

- [ ] **5.5 Student booking pages.** Booking timeline from `booking_events`; what to pay at move-in and to whom; deposit and charges; exact address after confirmation; cancel with the exact policy text and the refund amount shown before confirming; support contact.
      _Done when_ the UI shows the right actions for every state (component tests per state).

- [ ] **5.6 Check-in and the 24-hour window.** "I've moved in" (or ops-marked with student confirmation), a real countdown for the window, job → ACTIVE at the end.
      _Done when_ time-travel tests cover check-in, window expiry and the edge at exactly 24 h.

- [ ] **5.7 Disputes.** "Room not as shown" form with photos inside the window; ops queue; resolve refund (release + rebooking help with similar PGs) or uphold; audited.
      _Done when_ both resolutions update booking, allocation and notifications correctly.

- [ ] **5.8 Booking jobs.** expire_holds, confirm_timeouts, check_windows, no_shows (§7.5) — idempotent, observable, with metrics.
      _Done when_ running each job twice in a row changes nothing the second time (tested).

- [ ] **5.9 On-spot booking from a visit.** From a checked-in visit, the agent opens "Reserve now" for the student (channel `on_spot`, linked `visit_id`), usually instant-confirm.
      _Done when_ the visit → booking path works on a phone and the visit log links to the booking.

- [ ] **5.10 Ops bookings board.** Board by state with filters, SLA timers (unconfirmed > 2 h, disputes), actions with reasons, full event history.
      _Done when_ ops can run a day of bookings from it without database access.

## Phase 6 — Payments and ledger → **Milestone B**

- [ ] **6.1 Gateway port and Razorpay adapter.** Port per ARCHITECTURE §9.1; `FakeGateway` with signed webhook fixtures; Razorpay orders for the exact token amount; web checkout; server-side checkout-signature verification. **Read Razorpay's current docs first.** Test keys only.
      _Done when_ a staging booking reaches TOKEN_SECURED through Razorpay test mode.

- [ ] **6.2 Webhooks and event processing.** Raw-body HMAC verification, `payment_events` with a unique provider event id, fast 200 response, outbox processing, idempotent status mapping, late-payment revive or auto-refund (§7.4).
      _Done when_ duplicate, out-of-order and late webhooks are all handled correctly in tests.

- [ ] **6.3 Refunds.** Automatic refunds on reject, timeout, free cancellation, hold-expired payments and resolved disputes; manual refunds by ops with a reason and two-person approval above the threshold; refund webhooks.
      _Done when_ every refund path is tested and visible to the student with a status.

- [ ] **6.4 Ledger.** Chart of accounts and postings per §9.4 for every money event, in the same transaction; deferred balance check; ops ledger view.
      _Done when_ a test replays a full booking life cycle and the trial balance is zero.

- [ ] **6.5 Owner invoices.** On ACTIVE: fee, GST (per `gst_mode`), token applied, balance due; sequential numbering per financial year; PDF; balance via Razorpay payment link; paid by webhook.
      _Done when_ the ₹10,000 example produces an invoice of ₹3,540 with ₹2,000 applied and ₹1,540 due.

- [ ] **6.6 Reconciliation.** 15-minute stuck-payment checks; daily settlement matching; mismatch alerts and an ops dashboard.
      _Done when_ a seeded mismatch raises exactly one alert.

- [ ] **6.7 UPI one-time mandate mode (flagged).** Mandate create, capture and release in the adapter; validity check against move-in + window; fall back to payment mode. Build only after the founders confirm Razorpay has enabled it.
      _Done when_ the full flow passes in test mode behind `token_mode = upi_mandate`.

- [ ] **6.8 Payments go-live checklist.** Live keys in the secret manager, webhook secret set, a ₹1 live payment and refund, alerts on payment failures, a refund runbook.
      _Done when_ the founders sign off the checklist.

**Milestone B check**: a real student reserves a bed in production with a ₹2,000 token, is confirmed, checks in, and the token is earned or refunded correctly; the ledger balances and reconciliation is clean.

## Phase 7 — Owner dashboard

- [ ] **7.1 Owner onboarding.** OTP login as owner, profile, agreement acceptance, licence and society-permission uploads.
- [ ] **7.2 Occupancy calendar.** Per-bed calendar; block beds for offline tenants or maintenance (the exclusion constraint applies); upcoming move-ins and visits.
- [ ] **7.3 Bookings inbox.** Confirm or reject within the deadline; reminders; history.
- [ ] **7.4 Owner pricing editor.** The Phase 4 editor for owners, with caps, bands and the median visible, and preview before activation.
- [ ] **7.5 Invoices.** List, download, pay the balance.
- [ ] **7.6 Insights.** Views, visit requests, conversion, occupancy, own price vs locality median.
      _Done when_ (for the whole phase) an owner can run their PG's bookings and pricing from a phone without calling ops.

## Phase 8 — Launch hardening (finish before June 2027)

- [ ] **8.1 Security review.** STRIDE threat model for auth, booking and payments; ASVS L2 checklist; ZAP baseline and Schemathesis on staging; authorization matrix complete; dependency and image scans clean; secrets rotated.
- [ ] **8.2 Performance and load.** k6 at the planning load (ARCHITECTURE §18), including the hold race; `EXPLAIN ANALYZE` on top queries; caching verified; Lighthouse budgets enforced in CI.
- [ ] **8.3 Observability and runbooks.** Dashboards and alerts from ARCHITECTURE §19; a runbook per alert.
- [ ] **8.4 Compliance pass.** DPDP (notice, consent, retention, export/delete, breach plan), grievance SLAs, a dark-pattern audit of every screen, lawyer-reviewed legal pages and owner agreement.
- [ ] **8.5 Production infrastructure.** Terraform for AWS Mumbai (network, RDS with PITR, Redis, ECS services for API and worker, S3 + CloudFront, Secrets Manager, alarms), Vercel project, Cloudflare WAF and Turnstile; staging mirrors production at a smaller size.
- [ ] **8.6 Go-live rehearsal.** Restore from backup into a fresh environment, roll back a release, simulate a peak day on staging.
      _Done when_ (for the whole phase) the go-live checklist is signed off by the founders.

## Phase 9 — Growth features (in priority order)

Pick the next item with the founders; each needs its own plan before work starts.

1. **Rent through the app**: the rest of the first month paid through us; Razorpay Route sends the owner their share minus our fee (owner linked accounts and KYC). Enables `forfeit_to_owner` late-cancel policy.
2. **Move-in report and deposit help**: dated photo inventory signed by student and owner; mediation at move-out.
3. **Shortlist, compare and share with parents**: compare up to three PGs; signed read-only links; a parent can pay the token.
4. **Verified-resident reviews**: only after 30 days of an ACTIVE booking; moderation; owner replies.
5. **WhatsApp notifications** through a BSP, with approved templates.
6. **Bed alerts**: "tell me when a bed under ₹9,000 opens near North Campus".
7. **Book with a friend**: hold two beds in the same room at once.
8. **Commute and neighbourhood**: walking time to campus and metro (cached routing), nearby essentials.
9. **Hindi** interface.
10. **Price suggestions for owners** from a season of demand data (ARCHITECTURE §8.9); owners approve every change.
11. **Owner software subscription** (about ₹499/month), licensing-help workflow, partner services (tiffin, laundry, movers) with commission.
12. **New cities**: Gurugram and Noida in depth, then Bengaluru or Pune, as configuration.

---

## Kickoff prompt

Paste this into Claude Code in the repository root:

> Read CLAUDE.md, docs/PRODUCT_CONTEXT.md, docs/ARCHITECTURE.md and docs/BUILD_PLAN.md. Then start Phase 0 with step 0.1. Show me your plan for the step before writing code, and after each step run `make check`, tick the step in BUILD_PLAN.md and stop for my review. Ask me before choosing any paid vendor, changing a business rule, or touching real money or production data.
