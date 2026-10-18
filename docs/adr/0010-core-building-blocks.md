# ADR 0010: Core building blocks

- Status: accepted
- Date: 2026-10-19
- Build step: 0.4 (core building blocks)

## Context

Booking, pricing and payments (Phases 4–6) rely on a handful of guarantees: money is exact, time can be controlled in tests, background work happens exactly when the change that caused it commits, retried requests don't create things twice, staff actions can't be erased, and abuse is throttled without storing personal data in the cache. ARCHITECTURE §5 lists these blocks. This ADR records how they are built.

## Decision

1. **Money is integer paise and integer basis points**, with one rounding rule: half-up, ties away from zero, applied only where a spec says so. It is checked against Python's `Decimal` `ROUND_HALF_UP` with property tests (200 cases locally, 10,000 in CI). `format_inr` exists for server-written text; people see amounts formatted by the web app.
2. **One clock.** `Clock.now()` is the only way to read the time, and ruff bans `datetime.now`, `date.today` and `time.time` everywhere except `core/clock.py`. Domain code gets times and dates as arguments, and calendar dates are dates in India. The `tzdata` package ships the time-zone database so slim containers have Asia/Kolkata.
3. **Outbox, not a broker.** Jobs are rows written in the caller's transaction.
   - Claiming uses `FOR UPDATE SKIP LOCKED` plus a lease, so a crashed worker's job is taken over without a supervisor.
   - The handler's work and the "done" mark share one transaction, and a worker that lost its lease rolls its work back.
   - Retries back off exponentially with jitter, and jobs go `dead` after 10 attempts.
   - Error text is masked for phone numbers and capped at 2,000 characters.
   - Metrics use the OpenTelemetry API, a no-op until a meter provider exists (Phase 8).
4. **The scheduler needs no leader election.** Each periodic slot is a job with a unique dedupe key, so whichever worker enqueues it first wins. A slot missed while every worker was down runs once, not once per missed slot.
5. **Idempotency inside the transaction.**
   - The key is claimed with `INSERT … ON CONFLICT DO NOTHING` in the same transaction as the work, and the response is stored before commit.
   - A concurrent duplicate blocks on the key's row and then replays, so the work runs exactly once.
   - A failed attempt rolls back and releases the key.
   - This is stronger than the middleware the plan sketched, which can't make "work committed" and "response stored" atomic.
   - Keys are scoped per sender (the user from step 1.1).
6. **The audit log is append-only in the database.** A trigger refuses UPDATE, DELETE and TRUNCATE for every role, so even an application bug or a stolen app credential can't edit history. A database role with no UPDATE or DELETE privilege on the table is added with the production roles in Phase 8.
7. **Feature flags are typed in code** (`Flag` enum and `FLAGS` defaults). The table only overrides values and is seeded by a data migration kept apart from the schema migration. Reads never fail and cache for 30 seconds.
8. **Rate limits:**
   - A sliding-window log per subject in a Redis sorted set, updated atomically in Lua using the injectable clock's time.
   - Subjects are HMAC digests under `SECRET_KEY`, so Redis never holds phone numbers or IP addresses. An unkeyed hash of a 10-digit phone number could be reversed by brute force.
   - Every limit says whether it fails open or closed when Redis is down.
9. **`SECRET_KEY`** (at least 32 characters) is a required setting from this step. `make env` adds settings that `.env.example` gained to a developer's `.env` without printing or changing existing values.
10. **Migrations are checked against the models.** An integration test runs `alembic check` after upgrading. Autogenerate ignores tables owned by extensions (`spatial_ref_sys`), so it never proposes dropping them.

## Consequences

- Jobs are at-least-once for external effects, so every handler must be idempotent; notification jobs get dedupe keys per (event, recipient, channel).
- The outbox table keeps 7–30 days of finished jobs. Throughput is bounded by PostgreSQL, which is ample for the planned 20 writes per second.
- Fail-open limits can be bypassed while Redis is down; abuse-prone routes (OTP sends, holds) must use fail-closed limits.
- Rotating `SECRET_KEY` resets rate-limit windows (new digests). OTP codes hashed with it (step 1.2) are short-lived, so a rotation only invalidates codes in flight.
