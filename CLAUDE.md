# PG booking platform — instructions for Claude Code

An online platform for booking PG (paying guest) beds in Delhi NCR, built by two founders. Students and parents find verified PGs on a map, book a visit, reserve a bed with a small refundable token, and move in. Owners pay a one-time placement fee; students pay nothing.

**Current focus: the booking system and dynamic pricing.** The map is the showcase feature. Everything else waits its turn in the build plan.

The brand name is **Fix Your Stay** (the founders' choice, 2026-10-28). It lives only in `apps/web/src/config/brand.ts` and `BRAND_NAME` in `apps/api/src/app/config.py`; never hardcode it anywhere else.

## Read before working
- `docs/PRODUCT_CONTEXT.md`: the business, its rules and why they exist. Read it before touching pricing, booking, payments or anything a student sees about money.
- `docs/ARCHITECTURE.md`: system design, data model, the booking state machine, the pricing algorithm, security and scaling specs.
- `docs/BUILD_PLAN.md`: phased steps. Work through them in order and tick them off.

## Business rules the code must enforce
These come from the founders. Never change one without asking.
1. **Students never pay a platform fee**: no booking, convenience or service fee on the student side.
2. **Placement fee = 30% of the room category's listed (base) monthly rent**, charged once per tenant placed, paid by the owner. Never compute it on a dynamic or peak price. Rate, basis and GST mode come from `fee_policies`, not constants.
3. **GST at 18%** applies to the fee. Inclusive vs exclusive is undecided: support both via `gst_mode`, default `exclusive`.
4. **All dynamic-pricing upside goes to the owner.** Platform revenue must not change when a rule raises a price.
5. **Price lock**: the monthly rent from the quote is fixed for the whole stay. Rule changes never touch existing quotes or bookings.
6. **Clamp** dynamic prices to the owner's min/max, the locality rent band (when configured) and the global premium/discount caps.
7. **No dark patterns** (CCPA guidelines): urgency and scarcity text only from real inventory and real rule changes; countdowns only for a real hold expiry; the full monthly price, deposit and mandatory charges shown before booking; nothing pre-ticked.
8. **Token**: default ₹2,000 (keep ≤ ₹2,000), counts toward the first month's rent. No money is earned until the student has moved in and the 24-hour check window passes without a dispute. If the room isn't as shown, release or refund the same day.
9. **Free cancellation** up to 7 days before move-in; late-cancel handling comes from `booking_policies.late_cancel_policy`.
10. **Never pool owners' money.** Money owed to owners moves only through the gateway's split settlement (Razorpay Route), never through our own bank account.
11. **Owner phone and exact address stay hidden** until a visit is scheduled or a booking is confirmed (`hide_owner_contact` flag).
12. **Money is integer paise** in the database, API and code. No floats. Round half-up only where the specs say.

## Stack (decided — ask before changing)
- **API** `apps/api`: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 async (asyncpg), Alembic, GeoAlchemy2; PostgreSQL 16+ with postgis, btree_gist, pg_trgm, citext; Redis for cache and rate limits; uv, ruff, mypy (strict), import-linter, pytest, hypothesis, testcontainers.
- **Jobs**: outbox table + worker (`SELECT … FOR UPDATE SKIP LOCKED`) + scheduler in `apps/api/src/app/worker.py`. No message broker.
- **Web** `apps/web`: Next.js App Router, TypeScript strict, Tailwind, shadcn/ui, TanStack Query, React Hook Form + Zod, nuqs; typed client generated into `packages/api-client` (never edit it by hand).
- **Integrations behind ports/interfaces with dev adapters**: Razorpay (`PaymentGateway`), maps (`MapProvider`, Google first), SMS/OTP, WhatsApp, email, object storage.
- **Hosting target**: Vercel (web), AWS ap-south-1 (API, worker, RDS, Redis, S3), Cloudflare (DNS, WAF, Turnstile). Keep everything 12-factor.

Use current stable versions and pin them in lockfiles. Before integrating any third-party API, read its current official docs instead of relying on memory.

## Commands
```
make setup        # install everything, set up pre-commit
make dev          # infra (docker compose) + API + worker + web
make check        # lint + typecheck + all tests + client staleness — run before finishing any step
make test-api     # pytest (unit + integration with testcontainers)
make test-web     # vitest
make e2e          # playwright
make migrate      # alembic upgrade head
make migration m="message"   # autogenerate a migration, then review it by hand
make seed         # sample data (fictional PGs, verified geo data)
make gen-client   # export OpenAPI and regenerate packages/api-client
```
If a command doesn't exist yet, create it in the Makefile as part of the step that needs it.

## Engineering rules
- **Modular monolith.** Each API module has `domain/` (pure: no FastAPI, SQLAlchemy, I/O or clock), `service.py` (use cases, owns transactions), `repository.py`, `router.py` (thin), `schemas.py`, `models.py`, `policies.py`. Modules interact through services or outbox events, never each other's tables.
- Every booking status change goes through `booking/domain/state_machine.py`. Every money movement writes balanced ledger entries in the same transaction.
- The double-booking guarantee is the exclusion constraint on `inventory_allocations`. Never bypass or weaken it.
- Every endpoint authorizes through policy functions; another user's resource returns 404. Update the authorization matrix test with every new route.
- Validate input with Pydantic (`extra="forbid"`) and Zod. **The server computes every price and amount**; the web app only displays quotes.
- Migrations: Alembic only, reversible, one per change, never edit an applied one, expand-then-contract for breaking changes.
- Time: `timestamptz` in UTC, move-in dates as `date` (Asia/Kolkata), "now" only from the injectable clock.
- Tests ship with the feature. Pricing, booking, payments and ledger need ≥ 90% branch coverage plus the property and concurrency tests named in the plan.
- No secrets in code, logs or commits; only `.env.example` files are committed. Mask phone numbers in logs.
- Never invent real-world data (coordinates, PG names, prices, legal text). Use clearly fictional sample data, or ask.
- Small commits with Conventional Commit messages; justify every new dependency in the commit message.

## How to work
- One build-plan step at a time: `/next-step`. Start with a short plan (files, migrations, endpoints, tests, risks); use plan mode for anything touching money, inventory or auth.
- Finish each step with `make check`, tick it in `docs/BUILD_PLAN.md`, add a one-line note, then stop for review. `/phase-review` checks a finished phase.
- Record real decisions as ADRs in `docs/adr/`.
- **Stop and ask the founders before**: choosing or signing up for a paid vendor; changing any business rule above; touching production data or live payment keys; deleting data; writing final legal text (terms, privacy notice, owner agreement — drafts are fine if marked DRAFT).
