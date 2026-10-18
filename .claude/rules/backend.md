---
paths:
  - "apps/api/**"
---

# Backend rules (apps/api)

- **Layers**: a router parses the request, resolves the actor, checks the policy and calls one service method. Services own the transaction and orchestrate domain functions, repositories, ports and outbox events. `domain/` stays pure: no FastAPI, SQLAlchemy, httpx, environment access or clock reads. import-linter enforces this.
- **Sessions**: one `AsyncSession` per request or job. Services commit or roll back; repositories never commit. No autocommit.
- **Queries**: SQLAlchemy 2.0 `select()` style. Eager-load explicitly (`selectinload`/`joinedload`) and assert query counts in tests for list endpoints. Paginate every list with cursors.
- **Schemas**: request models use `ConfigDict(extra="forbid")`. JSON is camelCase via an alias generator. Public responses never include internal ids, exact coordinates, address lines or owner phone numbers.
- **Errors**: raise domain exceptions and map them to RFC 9457 problem+json in one place. Use the stable `code` values from ARCHITECTURE §15; add new codes there too.
- **Outbound HTTP**: one shared `httpx.AsyncClient` per provider with timeouts (connect 3 s, read 10 s). Retry only idempotent calls, with backoff. Never make external calls while holding row locks inside a transaction.
- **Jobs**: every outbox handler is idempotent and uses a dedupe key. Long or CPU-heavy work (image processing) runs only in the worker.
- **Migrations**: autogenerate, then review by hand. Name constraints and indexes explicitly. Keep data migrations separate from schema migrations. Test downgrade. Never edit an applied migration.
- **Typing**: `mypy --strict` passes. No `Any` in `domain/`. Use `NewType` for paise and ids where it prevents mix-ups.
- **Tests**: domain unit tests without a database; integration tests on testcontainers PostGIS; the frozen-clock fixture for anything time-based; polyfactory factories; `FakeGateway` instead of real payment calls. Never hit real third-party APIs in tests.
- **Logging**: structlog with request id and internal user id; mask phone numbers (last 4 digits only); never log tokens, OTPs, secrets or full webhook payloads containing personal data.
