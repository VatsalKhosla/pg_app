# ADR 0001: A modular monolith

- Status: accepted
- Date: 2026-10-19 (recorded in step 0.8; decided in the founders' planning, ARCHITECTURE §1)
- Build step: 0.8 (ADRs and runbook stubs)

## Context

Two founders and Claude Code build and run the platform. Demand is seasonal: most of it lands between June and August, with a peak around DU's first allocation list in mid-July. The core use cases cut across several areas in one go. A booking moves inventory, records a payment, posts ledger entries and notifies people, and it must do so atomically. Splitting those areas into services would turn single database transactions into distributed ones, and add deployments, networking and on-call load the team can't carry.

## Decision

1. **Two processes from one codebase:** the API (`app.main`) and the worker (`app.worker`). The same container image runs both (ADR 0013). There are no microservices, Kubernetes, message broker or event sourcing.
2. **Business code lives in modules** (`app/modules/<name>/`), each with the same layers:
   - `router.py`: HTTP only.
   - `service.py`: use cases; it owns the transaction.
   - `domain/`: pure code, with no I/O and no clock.
   - `repository.py`: queries on the module's own tables.
   - `models.py`, `schemas.py` and `policies.py`.
3. **Tooling enforces the boundaries** (import-linter, part of `make lint`):
   - Layers only import downward.
   - Domain code imports no web framework, database, cache, HTTP client, settings or logging.
   - `app.config` and `app.core` never depend on modules or entrypoints.
4. **Modules talk through services or outbox events, never each other's tables.** Cross-module side effects, such as `booking.activated` leading to ledger postings and an owner invoice, are domain events written to the outbox in the same transaction (ADR 0005). An import-linter contract forbidding imports of other modules' repositories and models arrives with the second business module.
5. **Shared, cross-cutting code lives in `app/core`:** money, clock, ids, outbox, idempotency, audit log, flags and rate limits.

## Consequences

- One deploy, one database, ACID transactions across modules, and simple local development (`make dev`).
- Both processes are stateless and scale horizontally (ECS Fargate in production). PostgreSQL is the shared bottleneck. ARCHITECTURE §18 plans for it: 300 reads and 20 writes per second at peak, sized connection pools, and a read replica for search when needed.
- The boundaries hold only as long as the contracts are kept. Every new module joins the import-linter contracts.
- A module can be split out later if a real need appears. Its outbox events and service interface become the seam.
