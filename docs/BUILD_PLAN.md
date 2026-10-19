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
| Milestone | Phases | What the founders can do |
|---|---|---|
| **A — Show it** | 0–3 | Real verified PGs on a live map, PG pages, visit booking. Use it for the Gate 1 test with owners and students, taking tokens through payment links run by ops |
| **B — Sell it** | 4–6 | Dynamic prices, bed reservations with a protected ₹2,000 token, confirmations, check-in, refunds, owner invoices |
| **C — Run it** | 7–8 | Owners self-serve; the platform is hardened and load-tested for June–August 2027 |
| **D — Grow it** | 9 | Rent through the app, reviews, parent sharing, WhatsApp, price suggestions, new cities |

## Founders' parallel tasks (Claude Code can't do these)

Start the slow ones in week 1.
- [ ] Incorporate the company (needed for Razorpay, GST, DLT); pick the brand name and buy the domain.
- [ ] **SMS DLT registration**: entity, sender ID and OTP/notification templates. This takes time, so start early.
- [ ] Razorpay account and KYC. Activation needs the site's About, Contact, Pricing, Terms, Privacy and Refund pages (step 3.8). Later, ask Razorpay to enable UPI one-time mandates and Route.
- [ ] Google Maps Platform project, API keys restricted by HTTP referrer and API, billing budget alerts.
- [ ] Accounts: GitHub, Vercel, AWS (Mumbai), Cloudflare, Sentry, PostHog, an email sender (SES or Resend). Google Workspace for staff sign-in.
- [ ] GitHub repository settings (docs/ci.md): the branch ruleset for `main` with the required checks, secret scanning with push protection, Dependabot alerts, and the free Renovate GitHub App for dependency updates.
- [ ] Lawyer: Terms, Privacy notice (DPDP), Refund & Cancellation policy, owner agreement (30% fee, 90-day introduction clause, token set-off), E-Commerce Rules seller-disclosure question (hiding owner contacts), grievance officer.
- [ ] CA: GST registration, invoice format, whether the 30% includes GST, accounting for tokens and set-off.
- [ ] Field work for Gate 1: map every PG within 2 km of the first micro-market, sign owners, collect photos and verification data.

---

## Phase 0 — Foundations

- [x] **0.1 Monorepo scaffold.** Create the layout in ARCHITECTURE §4: `apps/api` (uv project), `apps/web` (Next.js, pnpm), `packages/api-client`, `infra/`, root `Makefile`, `.editorconfig`, `.gitignore`, pre-commit hooks (ruff, ruff-format, mypy, eslint, prettier, gitleaks). Add `.env.example` files.
  *Done when* `make setup`, `make lint` and `make typecheck` succeed on the empty skeleton.
  *Note (2026-10-18):* uv + Python 3.14, pnpm 12 (pins Node 24 itself), Next 16.4, TypeScript 6.0 and ESLint 9 (newer majors lack plugin support), a 7-day release cooldown and SHA-pinned hooks (ADR 0007). `make check` is lint + typecheck + test-api until test-web (0.5) and client staleness (0.6) exist; the API Dockerfile waits for 0.3.

- [x] **0.2 Local infrastructure.** `infra/docker-compose.yml` with PostGIS (extensions: postgis, btree_gist, pg_trgm, citext), Redis, MinIO (S3) and Mailpit. `make dev` starts infra, API (reload), worker and web together.
  *Done when* a fresh clone runs `make setup && make dev` and all services are healthy.
  *Note (2026-10-18):* PostgreSQL 18 + PostGIS 3.6 (own multi-arch image matching RDS), Valkey 8.1 for Redis, SeaweedFS 4.48 for S3 (MinIO no longer publishes images) and Mailpit, with loopback-only ports, digest-pinned images and health checks (ADR 0008). `make dev` runs a minimal API (`/healthz`) and heartbeat worker that 0.3 and 0.4 grow, and switches the web app to webpack on glibc < 2.29; `make health` passed on a fresh clone. Starlette's TestClient now wants `httpx2`; tests use httpx's ASGI transport until the founders approve adding it.

- [x] **0.3 API skeleton.** App factory, pydantic-settings config, structlog JSON logging with request ids, RFC 9457 error handler, `/healthz` and `/readyz` (DB + Redis), CORS allowlist, security headers, OpenTelemetry and Sentry wiring (no-op without DSN), async SQLAlchemy session per request, Alembic initialised with a first migration that enables the extensions, import-linter contracts for the layer rules.
  *Done when* `/readyz` reports DB and Redis OK, OpenAPI is served, and import-linter passes.
  *Note (2026-10-18):* All of the above plus a 1 MiB body limit, phone masking in logs and Sentry, and a `system` module as the first layered module (ADR 0009). FastAPI 0.143 traces itself, so only SQLAlchemy and Redis instrumentation were added. 72 tests, including testcontainers runs of migrations up/down/up, `/readyz` and session rollback; import-linter has 3 contracts, proven to catch planted violations. Per-module protected contracts wait until a module has a repository.

- [x] **0.4 Core building blocks.** In `core/`: money (paise, bps, half-up rounding), injectable clock, ids (UUIDv7 public ids, booking codes), idempotency-key middleware and table, outbox table + `worker.py` (claim with SKIP LOCKED, retries with backoff, dead-lettering) + scheduler for periodic jobs, audit log helper, feature flags (table + cache), Redis rate limiter.
  *Done when* each block has unit/integration tests, including two workers never claiming the same job.
  *Note (2026-10-19):* All blocks built with 168 tests (Hypothesis for money; testcontainers for the outbox, scheduler, idempotency, audit, flags and limits), including two workers never claiming the same job and exactly-once idempotency under concurrency (ADR 0010). Idempotency lives in the service's transaction instead of middleware, so "work committed" and "response stored" are atomic. The audit log is append-only through a trigger; the restricted database role for the app comes with Phase 8. `SECRET_KEY` is now required (`make env` adds it to existing `.env` files).

- [x] **0.5 Web skeleton.** Next.js App Router, TypeScript strict, Tailwind, shadcn/ui, `src/config/brand.ts`, base layout (header, footer, mobile nav), CSP with nonces in middleware plus security headers, error and not-found pages, Sentry, PostHog stub, next-intl with English messages, PWA manifest.
  *Done when* Lighthouse mobile ≥ 90 on the placeholder home page and the browser console shows no CSP violations.
  *Note (2026-10-19):* Lighthouse mobile medians over three fresh-browser runs: 95 performance, 100 accessibility, best practices and SEO (`make lighthouse`). Every Playwright test fails on a console error or CSP violation, and pages pass axe (WCAG 2.2 AA) in light and dark mode (`make e2e`). Next.js 16's `src/proxy.ts` sets a per-request nonce CSP, so pages render per request until step 3.4 weighs hashes for ISR. Translations are typed and resolved on the server, and the phone menu loads on demand: the home page ships about 151 KB gzip of JavaScript. Sentry (minimal data collection) and the analytics stub stay off without keys (ADR 0011).

- [x] **0.6 Typed API client pipeline.** `make gen-client` exports OpenAPI from FastAPI and generates `packages/api-client` (openapi-typescript + openapi-fetch); a small wrapper in `apps/web/src/lib/api` handles cookies on the server, errors and problem+json.
  *Done when* the web home page calls `/healthz` through the typed client, and CI fails if the generated client is stale.
  *Note (2026-10-19):* The home page streams the API's liveness ("Online" with the API up, "Unavailable" without), and the API's log line carries the page's request id. `make check-client` (in `make check`) fails on drift, shown by a changed route summary. Every operation now declares its 4XX/5XX errors as problem+json, and FastAPI's unused `HTTPValidationError` is gone. Server calls forward only allow-listed API cookies (none until step 1.1) and time out after 3 s (ADR 0012).

- [x] **0.7 CI and security scanning.** GitHub Actions: `ci.yml` (lint, typecheck, API tests with a PostGIS service, web unit tests, web build, client staleness, oasdiff), `security.yml` (CodeQL, gitleaks, pip-audit, pnpm audit, Trivy on the API image). Renovate or Dependabot. Actions pinned by SHA. Branch protection documented.
  *Done when* a pull request shows every check green.
  *Note (2026-10-19):* All 13 checks passed on their first run, on the push of 7f64411 ([CI](https://github.com/VatsalKhosla/pg_app/actions/runs/39217998691), [Security](https://github.com/VatsalKhosla/pg_app/actions/runs/39217998658)). Pull requests run the same two workflows; the only difference is that oasdiff compares against the target branch. No pull request was opened, because `gh` isn't signed in here, so the first one will confirm the pull request view. Beyond the plan: Playwright E2E, workflow linting (actionlint, zizmor) and the API image (`apps/api/Dockerfile`, non-root, pip removed). Renovate was chosen over Dependabot, which lacks pnpm 12 and uv 0.13 support (ADR 0013). Branch protection is documented in docs/ci.md, and setting it up is a founders' task.

- [x] **0.8 ADRs and runbook stubs.** `docs/adr/0001` modular monolith, `0002` FastAPI + Next.js, `0003` PostgreSQL + PostGIS + exclusion constraints, `0004` money in paise and the ledger, `0005` outbox jobs instead of a broker, `0006` map provider behind an interface. Runbook stubs for webhook failures, dead jobs and restoring from a backup.
  *Done when* the files exist and match ARCHITECTURE.md.
  *Note (2026-10-19):* ADRs 0001–0006 record the planning decisions, each checked against ARCHITECTURE.md and linked to the code that now enforces it. An index (docs/adr/README.md) lists all 13 ADRs. The runbooks are in docs/runbooks/. The dead-jobs one is already usable (queries and a safe requeue against the real `outbox_jobs` columns). The webhook and restore ones mark what steps 6.x and 8.x must fill in.

## Phase 1 — Identity and access

- [x] **1.1 Users, roles, sessions.** Tables from ARCHITECTURE §6; opaque session tokens (hash stored), cookie flags, rotation, logout, log out everywhere, session list, CSRF double-submit protection.
  *Done when* tests check cookie flags, rotation, revocation and CSRF rejection.
  *Note (2026-10-19):* Built as the `identity` module, with `users`, `user_roles` and `sessions` tables. 16 integration tests cover:
  - cookie flags and the parent domain;
  - sliding 30-day and absolute 12-hour expiry;
  - rotation, and the replaced session ending at sign-in;
  - logout, log out everywhere, ending one device, and 404 for another user's session;
  - suspension, and retention;
  - CSRF rejection, including a token bound to another session.

  CSRF is a signed double-submit token, bound to the session and enforced app-wide. A test sweeps every unsafe route; FastAPI 0.143 nests included routers, so the sweep walks `iter_route_contexts` (ADR 0014). Sign-in itself arrives with OTP in 1.2.

- [ ] **1.2 Phone OTP login.** Request and verify endpoints; HMAC-stored codes; expiry, attempt limits, resend cooldown, per-phone and per-IP limits; Turnstile check; `OtpSender` port with a console adapter (dev) and an adapter for the founders' chosen DLT provider (ask before picking).
  *Done when* login works end to end in dev, and abuse tests pass (sixth attempt locked, rate limit returns 429, expired code rejected).

- [ ] **1.3 Staff sign-in.** Google OIDC restricted to an allowed domain or email list (OTP + TOTP fallback); staff roles; 12-hour sessions.
  *Done when* a non-allowed Google account is refused and staff routes reject non-staff.

- [ ] **1.4 Policies and the authorization matrix.** `policies.py` pattern; FastAPI dependencies for the current actor; a matrix test that enumerates every route × role and asserts the expected status (404 for other users' objects).
  *Done when* the matrix runs in CI and fails if a new route lacks an entry.

- [ ] **1.5 Consent and data requests (DPDP).** Versioned privacy notice acceptance at signup, `consents` table, data export and deletion request endpoints with an ops queue, retention job skeleton.
  *Done when* signup can't complete without consent, and an export request produces a downloadable file for that user only.

- [ ] **1.6 Web auth flows.** Phone → OTP → profile (name, college or workplace, gender for PG eligibility, with consent); session-aware header; protected route handling; staff login page.
  *Done when* Playwright covers login, logout and protected-route redirects on mobile viewport.

## Phase 2 — Catalog and ops console

- [ ] **2.1 Geo seed.** Cities, localities (start with North Campus, Satya Niketan and Old Rajinder Nagar areas; then Gurugram and Noida hubs), campuses and metro stations. Source coordinates from OpenStreetMap (with attribution) or official sources; **never invent coordinates** — if unsure, leave the row out and list it in the step note. Idempotent seed command.
  *Done when* `make seed` loads geo data and a distance query from a campus returns sensible results.

- [ ] **2.2 Catalog schema.** Owners, properties (exact and display location, gender policy, meals, verification and licence status, society permission, status), room categories (the pricing unit, with base rent, owner min/max, deposit, mandatory charges), rooms, beds, amenities. Constraints and indexes from ARCHITECTURE §6.
  *Done when* migrations apply cleanly and repository tests cover create, update, publish and geo queries.

- [ ] **2.3 Media pipeline.** Presigned uploads, worker processing (magic bytes, EXIF/GPS stripping, WebP/AVIF variants, video poster), moderation status, `verified_capture` flag, CDN and signed URLs.
  *Done when* an uploaded phone photo comes out with no GPS EXIF in all variants, and a private document needs a signed URL.

- [ ] **2.4 Ops console: listings.** `/ops` screens to create and edit properties, room categories, rooms and beds; pin picker (drag the pin, or use the agent's GPS); amenities and house rules; photo and video upload with ordering; publish and unpause; full audit trail.
  *Done when* ops can create a complete listing from a phone in under 10 minutes.

- [ ] **2.5 Field verification workflow.** Mobile checklist for agents: building age and condition, cracks, exits, extinguishers, CCTV, warden, women's-safety features, licence number, society permission; GPS and time captured; result sets `verification_status`. Unverified properties can't be published while `verified_only` is the default.
  *Done when* a property moves unverified → scheduled → verified with a stored report and photos.

- [ ] **2.6 Owner records and agreements.** Owner profiles, business name, GSTIN (optional), versioned agreement text with click-wrap acceptance (version, document hash, timestamp, IP, user agent).
  *Done when* acceptance is recorded and visible in ops, and a new agreement version asks owners to accept again.

- [ ] **2.7 Location privacy and contact hiding.** Generate and store `display_location` (random 80–150 m offset, stable); public APIs expose only display data; the owner phone and exact address are hidden behind `hide_owner_contact`.
  *Done when* tests prove public endpoints never return the exact point, the address line or the owner's phone.

## Phase 3 — Discovery: search, PG pages, map, visits → **Milestone A**

- [ ] **3.1 Price summaries (base-rent version).** `property_price_summaries` for the next six months, filled from base rents for now (Phase 4 switches it to the engine). Recomputed on catalog changes through the outbox.
  *Done when* summaries refresh within a minute of a rent change.

- [ ] **3.2 Search API.** Filters, sorting, text search (trigram + full-text) and cursor pagination per ARCHITECTURE §10.1, using summaries for budget and price sort; distance to the chosen campus and nearest metro.
  *Done when* integration tests cover each filter, and p95 < 300 ms on a seeded set of 3,000 properties.

- [ ] **3.3 Map pins API.** Bbox + filters → compact pins with price ranges from summaries; Redis cache with ETags; 2,000-pin cap.
  *Done when* a pan across NCR returns correct pins, and repeated calls hit the cache.

- [ ] **3.4 PG detail page.** ISR page per ARCHITECTURE §10.6: gallery with verified-photo labels, video, safety summary, room categories with prices (base rent until Phase 4), deposit and mandatory charges shown upfront, amenities, rules, small embedded map at the display location, distances, owner business name, "Book a visit" CTA.
  *Done when* the page passes Lighthouse mobile ≥ 85 and shows no hidden charges.

- [ ] **3.5 Search + map UI (the showcase).** Split view on desktop; list-first on mobile with a map toggle and draggable bottom sheet; price pins with ranges; clustering; "search as I move the map"; filters in the URL (nuqs); hover sync between cards and pins; campus rings and metro overlay; NCR bounds lock; lazy-loaded map behind the `MapProvider` interface (Google adapter first); skeletons and empty states; keyboard-accessible pins.
  *Done when* Playwright covers filter → pan → select pin → open PG page on mobile and desktop, and the map bundle loads only on the map view.

- [ ] **3.6 Landing pages and SEO.** `/pg-near/[campus]`, `/pg-in/[locality]`, JSON-LD, canonical URLs, sitemap, robots, dynamic OG images, on-demand revalidation from the API.
  *Done when* Google's Rich Results Test validates a PG page and the sitemap lists every published PG.

- [ ] **3.7 Visits.** Request with up to three slots; ops scheduling and agent assignment; SMS confirmations and reminders (T−24 h, T−2 h); agent check-in with GPS and time (the visit log); outcome capture; limits and rate limits. The exact address is revealed to the student once a visit is scheduled.
  *Done when* a student books a visit on a phone, the agent checks in, and ops see the visit log.

- [ ] **3.8 Trust and legal pages.** About (founders' names and faces), Contact (a phone line staffed by a person), Pricing ("students pay nothing; owners pay a one-time 30% placement fee"), Terms, Privacy notice, Refund & Cancellation policy, Grievance officer with a ticket form (acknowledge ≤ 48 h, resolve ≤ 1 month), "How your token is protected". Mark legal texts **DRAFT — needs lawyer review**.
  *Done when* every page is linked from the footer and the grievance form issues a ticket number.

- [ ] **3.9 Analytics and install.** Funnel events (search → PG view → visit request → visit done → reservation), PII-masked; PWA installability; web-vitals reporting.
  *Done when* the funnel shows in PostHog from a staging run and the site installs on Android Chrome.

**Milestone A check**: a student can find a verified PG on the map, see honest prices, and book a visit from a phone; ops can create and verify listings and run visits; security baseline (headers, CSRF, rate limits, authorization matrix) passes. Ship to production and tell the founders.

## Phase 4 — Dynamic pricing engine (**pivot 1**)

- [ ] **4.1 Policies, caps and rent bands.** Tables `fee_policies`, `booking_policies`, `pricing_caps`, `rent_bands` with an admin UI and audit log; seed defaults from PRODUCT_CONTEXT §9 (fee 30% of listed rent, GST 18% exclusive, token ₹2,000, hold 15 min, free cancel 7 days, check window 24 h, confirm deadline 12 h, late cancel `refund_full`, one active hold per user, caps +40% / −30%, rounding ₹50). No official bands seeded.
  *Done when* every default is editable by admins only and every change is audited.

- [ ] **4.2 Pricing engine (pure).** `pricing/domain/engine.py` per ARCHITECTURE §8: rule kinds with typed params, the algorithm, clamping, rounding, fee/GST/token maths, explainable adjustments, `engine_version`. Hypothesis tests for every invariant in §8.8 (≥ 10,000 cases in CI) plus table tests including the worked example.
  *Done when* all invariants hold and branch coverage of the engine is ≥ 95%.

- [ ] **4.3 Rule sets and versioning.** Draft → active → archived; activation is atomic, creates an immutable version and is audited; validation (overlapping seasons, band conflicts, impossible bounds) returns readable errors.
  *Done when* activating a new version never changes existing quotes or bookings (tested).

- [ ] **4.4 Quotes API.** `POST /v1/quotes` and `GET /v1/quotes/{id}`: occupancy from real allocations (HELD excluded), persisted breakdown, 30-minute expiry, inputs hash, human explanation string. Rate-limited.
  *Done when* the quote's numbers equal the engine's for the same inputs, and expired quotes are refused by later steps.

- [ ] **4.5 Price calendar and honest urgency.** Calendar endpoint (weekly move-ins, 12 weeks, cached) and UI on the PG page ("Move in by 15 Jun: ₹9,500 · from 1 Jul: ₹11,000"); "only N beds left" only from real availability (N ≤ 3); a "price fixed for your whole stay" badge; quotes show the full breakdown.
  *Done when* tests prove every urgency message is backed by data, and the PG page shows quote-consistent prices.

- [ ] **4.6 Pricing editor (ops first).** Rule list, add/edit forms per kind, live preview (pick a move-in date and stay → breakdown), 12-week price chart, band and median shown, activate with confirmation. Owners get the same editor in Phase 7.
  *Done when* ops can set a July peak rule and an early-bird rule and see both in preview, on the calendar and on the map.

- [ ] **4.7 Summaries from the engine.** Switch `property_price_summaries` to engine output per month; recompute on `pricing.rules_changed`, allocation changes and band changes.
  *Done when* map pins and search budgets match PG-page prices for the same month.

- [ ] **4.8 Integrity alerts.** Ops alerts when listed rent is > 25% below the locality median, when clamps fire on > 20% of a property's weekly quotes, and on frequent rule churn.
  *Done when* seeded scenarios trigger each alert exactly once.

## Phase 5 — Booking system (**pivot 2**)

- [ ] **5.1 Inventory allocations and availability.** The `inventory_allocations` table with the exclusion constraint; availability queries per category and period; offline-tenant and maintenance blocks (ops now, owners in Phase 7).
  *Done when* overlapping active allocations are impossible (constraint test) and availability numbers match allocations.

- [ ] **5.2 Booking state machine (pure).** Transition table per ARCHITECTURE §7.2 with guards and side-effect descriptors; exhaustive tests over every (state, event) pair; property tests that random event sequences never break invariants (e.g., no money earned before ACTIVE).
  *Done when* every allowed transition is tested and every other pair is rejected with `INVALID_TRANSITION`.

- [ ] **5.3 Holds.** `POST /v1/bookings` (quote id + Idempotency-Key) per §7.3: locking, stale-hold expiry, bed choice, constraint as the last line of defence, active-hold limit, rate limits, error codes.
  *Done when* the 50-concurrent-requests test yields exactly one hold, and replaying the same Idempotency-Key returns the same response.

- [ ] **5.4 Confirmation flow.** Owner/ops confirm or reject; `instant_confirm` per property; confirmation deadline job → REJECTED (refund hooks are stubs until Phase 6); notifications.
  *Done when* all three paths work end to end with notifications.

- [ ] **5.5 Student booking pages.** Booking timeline from `booking_events`; what to pay at move-in and to whom; deposit and charges; exact address after confirmation; cancel with the exact policy text and the refund amount shown before confirming; support contact.
  *Done when* the UI shows the right actions for every state (component tests per state).

- [ ] **5.6 Check-in and the 24-hour window.** "I've moved in" (or ops-marked with student confirmation), a real countdown for the window, job → ACTIVE at the end.
  *Done when* time-travel tests cover check-in, window expiry and the edge at exactly 24 h.

- [ ] **5.7 Disputes.** "Room not as shown" form with photos inside the window; ops queue; resolve refund (release + rebooking help with similar PGs) or uphold; audited.
  *Done when* both resolutions update booking, allocation and notifications correctly.

- [ ] **5.8 Booking jobs.** expire_holds, confirm_timeouts, check_windows, no_shows (§7.5) — idempotent, observable, with metrics.
  *Done when* running each job twice in a row changes nothing the second time (tested).

- [ ] **5.9 On-spot booking from a visit.** From a checked-in visit, the agent opens "Reserve now" for the student (channel `on_spot`, linked `visit_id`), usually instant-confirm.
  *Done when* the visit → booking path works on a phone and the visit log links to the booking.

- [ ] **5.10 Ops bookings board.** Board by state with filters, SLA timers (unconfirmed > 2 h, disputes), actions with reasons, full event history.
  *Done when* ops can run a day of bookings from it without database access.

## Phase 6 — Payments and ledger → **Milestone B**

- [ ] **6.1 Gateway port and Razorpay adapter.** Port per ARCHITECTURE §9.1; `FakeGateway` with signed webhook fixtures; Razorpay orders for the exact token amount; web checkout; server-side checkout-signature verification. **Read Razorpay's current docs first.** Test keys only.
  *Done when* a staging booking reaches TOKEN_SECURED through Razorpay test mode.

- [ ] **6.2 Webhooks and event processing.** Raw-body HMAC verification, `payment_events` with a unique provider event id, fast 200 response, outbox processing, idempotent status mapping, late-payment revive or auto-refund (§7.4).
  *Done when* duplicate, out-of-order and late webhooks are all handled correctly in tests.

- [ ] **6.3 Refunds.** Automatic refunds on reject, timeout, free cancellation, hold-expired payments and resolved disputes; manual refunds by ops with a reason and two-person approval above the threshold; refund webhooks.
  *Done when* every refund path is tested and visible to the student with a status.

- [ ] **6.4 Ledger.** Chart of accounts and postings per §9.4 for every money event, in the same transaction; deferred balance check; ops ledger view.
  *Done when* a test replays a full booking life cycle and the trial balance is zero.

- [ ] **6.5 Owner invoices.** On ACTIVE: fee, GST (per `gst_mode`), token applied, balance due; sequential numbering per financial year; PDF; balance via Razorpay payment link; paid by webhook.
  *Done when* the ₹10,000 example produces an invoice of ₹3,540 with ₹2,000 applied and ₹1,540 due.

- [ ] **6.6 Reconciliation.** 15-minute stuck-payment checks; daily settlement matching; mismatch alerts and an ops dashboard.
  *Done when* a seeded mismatch raises exactly one alert.

- [ ] **6.7 UPI one-time mandate mode (flagged).** Mandate create, capture and release in the adapter; validity check against move-in + window; fall back to payment mode. Build only after the founders confirm Razorpay has enabled it.
  *Done when* the full flow passes in test mode behind `token_mode = upi_mandate`.

- [ ] **6.8 Payments go-live checklist.** Live keys in the secret manager, webhook secret set, a ₹1 live payment and refund, alerts on payment failures, a refund runbook.
  *Done when* the founders sign off the checklist.

**Milestone B check**: a real student reserves a bed in production with a ₹2,000 token, is confirmed, checks in, and the token is earned or refunded correctly; the ledger balances and reconciliation is clean.

## Phase 7 — Owner dashboard

- [ ] **7.1 Owner onboarding.** OTP login as owner, profile, agreement acceptance, licence and society-permission uploads.
- [ ] **7.2 Occupancy calendar.** Per-bed calendar; block beds for offline tenants or maintenance (the exclusion constraint applies); upcoming move-ins and visits.
- [ ] **7.3 Bookings inbox.** Confirm or reject within the deadline; reminders; history.
- [ ] **7.4 Owner pricing editor.** The Phase 4 editor for owners, with caps, bands and the median visible, and preview before activation.
- [ ] **7.5 Invoices.** List, download, pay the balance.
- [ ] **7.6 Insights.** Views, visit requests, conversion, occupancy, own price vs locality median.
  *Done when* (for the whole phase) an owner can run their PG's bookings and pricing from a phone without calling ops.

## Phase 8 — Launch hardening (finish before June 2027)

- [ ] **8.1 Security review.** STRIDE threat model for auth, booking and payments; ASVS L2 checklist; ZAP baseline and Schemathesis on staging; authorization matrix complete; dependency and image scans clean; secrets rotated.
- [ ] **8.2 Performance and load.** k6 at the planning load (ARCHITECTURE §18), including the hold race; `EXPLAIN ANALYZE` on top queries; caching verified; Lighthouse budgets enforced in CI.
- [ ] **8.3 Observability and runbooks.** Dashboards and alerts from ARCHITECTURE §19; a runbook per alert.
- [ ] **8.4 Compliance pass.** DPDP (notice, consent, retention, export/delete, breach plan), grievance SLAs, a dark-pattern audit of every screen, lawyer-reviewed legal pages and owner agreement.
- [ ] **8.5 Production infrastructure.** Terraform for AWS Mumbai (network, RDS with PITR, Redis, ECS services for API and worker, S3 + CloudFront, Secrets Manager, alarms), Vercel project, Cloudflare WAF and Turnstile; staging mirrors production at a smaller size.
- [ ] **8.6 Go-live rehearsal.** Restore from backup into a fresh environment, roll back a release, simulate a peak day on staging.
  *Done when* (for the whole phase) the go-live checklist is signed off by the founders.

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
