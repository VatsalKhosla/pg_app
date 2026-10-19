# ADR 0002: FastAPI for the API, Next.js for the web app

- Status: accepted
- Date: 2026-10-19 (recorded in step 0.8; decided in the founders' planning, ARCHITECTURE §3)
- Build step: 0.8 (ADRs and runbook stubs)

## Context

Students from other cities find PGs through Google, Instagram and seniors, so public pages must be fast and indexable. Version 1 is a mobile website that installs as an app (PWA), not native apps. The same product also needs an owner dashboard and an ops console. One founder already works in FastAPI, and money and booking logic need strict typing and exhaustive tests.

## Decision

1. **API:** Python (3.14; at least 3.12), FastAPI, Pydantic v2 and SQLAlchemy 2 (async, asyncpg) with Alembic.
   - Request models reject unknown fields, and JSON is camelCase.
   - Errors are RFC 9457 problem details (ADR 0009).
   - Tooling: uv, ruff, mypy strict and pytest (ADR 0007).
2. **Web:** Next.js (App Router), React and TypeScript strict. One app holds the public site, the owner dashboard and the ops console, as route groups.
   - Server Components by default; Client Components only for interactive pieces.
   - Tailwind and shadcn/ui on Radix primitives; next-intl for translations (ADR 0011).
3. **The OpenAPI schema is the contract between them.** The web app calls the API only through a client generated from it, and CI fails when the client is stale or the schema breaks compatibility (ADR 0012, ADR 0013).
4. **Hosting:** Vercel for the web app (Mumbai functions region). AWS ap-south-1 for the API and worker, on ECS Fargate with RDS PostgreSQL. Cloudflare in front of both.

## Consequences

- Two languages and toolchains. The generated client and the contract checks keep them in step, and the Makefile gives both one interface.
- Next.js changes quickly, and its current version differs from most published examples, so the bundled docs in `node_modules/next/dist/docs/` are read first (apps/web/AGENTS.md).
- A per-request nonce CSP renders pages per request, which trades away static caching until step 3.4 decides on hashes for ISR pages (ADR 0011).
- Python carries the booking, pricing and ledger logic, where its typing, Hypothesis property tests and testcontainers integration tests matter most.
