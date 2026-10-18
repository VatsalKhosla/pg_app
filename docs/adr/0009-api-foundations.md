# ADR 0009: API foundations

- Status: accepted
- Date: 2026-10-18
- Build step: 0.3 (API skeleton)

## Context

Every later module (identity, catalog, pricing, booking, payments) builds on the same request pipeline, error format, logging, telemetry and database access. Choices here are expensive to change once dozens of endpoints and the generated web client depend on them, and several touch security and personal data (ARCHITECTURE §12, §15, §17, §19).

## Decision

1. **Errors are RFC 9457 problem documents** (`application/problem+json`), built in one place (`app/core/errors.py`). The body is `{type, title, status, code, detail, errors[], requestId, traceId}`, and `type` stays `about:blank` until problem pages exist. Code raises `AppError` subclasses with a stable `code`. Validation errors list each field with a JSON Pointer (`/moveIn`) or a parameter name and never echo the rejected input. Unexpected errors are logged and sent to Sentry, but the client sees only `INTERNAL_ERROR` and the request id.
2. **One request id per request**: a well-formed incoming `X-Request-ID` (8–64 safe characters) is kept, otherwise a UUIDv7 is generated. It is bound to every log line, returned in the response header and included in every problem document.
3. **Structured logging with structlog**: JSON when deployed, readable lines locally, the same pipeline for uvicorn, SQLAlchemy and Alembic. Phone numbers are masked to their last four digits in every log line and Sentry event, tracebacks included (`app/core/pii.py`). The middleware writes one access line per request with the route template (`/v1/bookings/{code}`), never the raw path, and logs probes at debug level.
4. **Telemetry is off until configured.** FastAPI 0.143 traces requests itself into whatever tracer provider exists, so the separate FastAPI instrumentation package is not used (it would trace requests twice). An OpenTelemetry SDK provider exporting over OTLP/HTTP, plus SQLAlchemy and Redis spans, is set up only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Sentry starts only with a DSN, reports errors only (`traces_sample_rate` 0 by default) and sends no default PII.
5. **HTTP hardening by default**:
   - Security headers: a strict CSP (`default-src 'none'`), `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, COOP and CORP, and `Cache-Control: no-store` unless a route sets its own. HSTS only in staging and production.
   - The interactive docs only outside production; the OpenAPI schema everywhere.
   - Request bodies limited to 1 MiB, whether or not a Content-Length is sent (uploads go straight to object storage).
   - CORS for exact origins only, which must be `https` in deployed environments.
6. **Database access**:
   - Async SQLAlchemy 2.1 with asyncpg and one session per request, with no autocommit: services commit, and anything left uncommitted is rolled back when the session closes.
   - Connections run in UTC with a 15 s statement timeout and an application name; constraint names follow a fixed naming convention.
   - Migrations are Alembic, run as their own step (`make migrate`; `make dev` runs it first) without a statement timeout. The first migration enables postgis, btree_gist, pg_trgm and citext.
   - Every migration must have a single head and a real downgrade (unit test), and the history is migrated up, down and up again against a real database (integration test).
7. **Settings in three layers** (`LoggingSettings` → `DatabaseSettings` → `Settings`), so the worker and migrations ask only for what they use. Connection URLs and the Sentry DSN are `SecretStr`, so they never appear in logs or reprs. `make setup` creates `apps/api/.env` readable only by its owner.
8. **Module layout enforced by import-linter** in `make lint`:
   - Each module is layered `router > service > schemas | policies | repository > models > domain`.
   - Domain code may not import FastAPI, Starlette, SQLAlchemy, asyncpg, Redis, httpx, settings or logging.
   - `app.core` and `app.config` never import business modules or the entrypoints.
   - The `system` module (`/healthz`, `/readyz`) is the first module built this way.
9. **Tests**:
   - Unit tests build settings that ignore the environment and `.env` (`IsolatedSettings`) and drive the app in-process through httpx's ASGI transport.
   - Integration tests run real PostgreSQL (the image `make dev` builds) and Valkey (the image in the Compose file) with testcontainers.
   - Starlette's TestClient is avoided because Starlette 1.7 deprecates it with httpx in favour of `httpx2`, which the founders haven't approved yet.

## Consequences

- New endpoints get consistent errors, logs, traces, headers and limits without extra code; new error codes go into ARCHITECTURE §15.
- `make test-api` needs Docker for the integration tests; `make test-api-unit` doesn't.
- Some structural rules (one module may not use another module's repository or models) need a protected contract per module; add one when a module gains a repository.
- Revisit the TestClient choice if `httpx2` is approved.
