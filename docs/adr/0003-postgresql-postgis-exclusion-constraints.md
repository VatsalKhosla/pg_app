# ADR 0003: PostgreSQL with PostGIS, and exclusion constraints against double booking

- Status: accepted
- Date: 2026-10-19 (recorded in step 0.8; decided in the founders' planning, ARCHITECTURE §1, §6 and §7)
- Build step: 0.8 (ADRs and runbook stubs)

## Context

A bed must never be booked twice for overlapping dates, even when 50 students race for the last bed. Search is geographic (PGs within 2 km of a campus, pins inside the visible map) and fuzzy (PG and locality names). Money and idempotency also need hard guarantees. Application-level checks alone can't hold under concurrency, and a second datastore for geo search would be one more thing to run.

## Decision

1. **PostgreSQL** (18 locally, RDS in production; at least 16) with the `postgis`, `btree_gist`, `pg_trgm` and `citext` extensions. It is the only durable store: Redis holds nothing that exists only there.
2. **The database guards the invariants:**
   - **No double booking.** `inventory_allocations` has `EXCLUDE USING gist (bed_id WITH =, period WITH &&) WHERE (is_active)` over `daterange` periods `[move_in, move_out)`. This constraint is the guarantee; nothing may bypass or weaken it.
   - **Holding a bed is one transaction:**
     1. Lock the category's beds `FOR UPDATE`.
     2. Expire stale holds.
     3. Pick a free bed and insert the booking and its allocation.
     4. If the constraint fires anyway, answer `409 BED_UNAVAILABLE`.
   - **The ledger balances.** Debits equal credits per transaction, through a deferred constraint trigger (ADR 0004).
   - **Unique keys.** They make webhooks (`payment_events` per provider event), idempotency keys and scheduled job slots exactly-once.
   - **The audit log is append-only**, through a trigger (ADR 0010).
3. **Geography is stored natively.** Locations are `geography(Point, 4326)` with GiST indexes, and names have trigram GIN indexes.
4. **Booking state changes use compare-and-set updates** (`WHERE status = :expected AND version = :v`), driven by the pure state machine in `booking/domain/state_machine.py`.

## Consequences

- The code depends on PostgreSQL specifically, and that is accepted. Tests run against the same PostGIS image as local development (testcontainers, ADR 0008), never SQLite.
- Step 5 must prove the guarantee with the required concurrency test: 50 simultaneous holds on the last free bed give one HELD booking, 49 responses of 409, and no overlapping active allocations.
- Stay extensions and offline blocks go through the same constraint, so conflicts surface as clear errors instead of silent overlaps.
- Production needs point-in-time recovery and tested restores (runbook: restoring from a backup).
