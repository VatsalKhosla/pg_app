# ADR 0046: Holds: a bed held for a student's own quote, in one transaction that locks the room type, with the exclusion constraint as the last line

- Status: accepted
- Date: 2026-10-31
- Build step: 5.3 (holds)

## Context

- **BUILD_PLAN 5.3:** `POST /v1/bookings` with a quote id and an Idempotency-Key, per ARCHITECTURE §7.3:
  - locking, stale-hold expiry and bed choice;
  - the constraint as the last line of defence;
  - the active-hold limit, rate limits and error codes.

  It's done when 50 concurrent requests yield exactly one hold, and replaying an Idempotency-Key returns the same response.
- **What's already there:**
  - the state machine, with `hold` and `hold_expired` (ADR 0045);
  - allocations and their exclusion constraint (ADR 0044);
  - quotes that stand for 30 minutes and carry the booking terms they were made under (ADR 0039);
  - the idempotency keys of step 0.4.
- **Remote booking is behind a flag** (`remote_booking_enabled`, off by default): season one is visit-first, and on-spot booking from a visit comes in 5.9.

## Decision

1. **A booking module** owns two tables:
   - **`bookings`:** status, version, the stay, the facts the state machine reads, and the quote's money copied once (rule 5). It also keeps the terms the quote was made under, so a later change to the booking policy never alters a booking already made.
   - **`booking_events`:** a row per transition, which a trigger keeps append-only.

   A booking has a public code from `app.core.ids` (`BK-` and eight Crockford characters). The allocations' booking foreign key arrives with the table.
2. **A hold is one transaction**, in this order:
   1. **The Idempotency-Key** is claimed, so a retry gets the stored answer, marked `Idempotent-Replayed`. A failed attempt releases the key.
   2. **The quote** must be the student's own: another's, or one asked for signed out, is a 404. It must be unexpired (409 `QUOTE_EXPIRED`), including a move-in that passed since it was given. Its PG must still be public.
   3. **The student's holds** are locked with an advisory lock and counted. At the terms' limit the answer is 409 `HOLD_LIMIT_REACHED`. A quote makes one booking (409 `QUOTE_USED`).
   4. **The room type's active beds are locked** in id order (`FOR UPDATE`), so holds on it go one at a time and never deadlock. Holds on those beds past their expiry are expired through the state machine, and their beds freed.
   5. **A free bed is chosen** for the whole stay by the inventory domain's `choose_bed`. It takes a bed in a partly held room first, so whole rooms stay free for groups, then the room with the fewest free beds, then the lowest id. None free is 409 `BED_UNAVAILABLE`.
   6. **The booking is added**, HELD by the state machine's `hold`. A random code that clashes is drawn again. Then come its allocation (the constraint, should it fire, is answered as a held bed), its event row, an audit entry and a refresh of the PG's search entry and pages.
3. **Every later status change** goes through the state machine and is saved with a compare-and-set on status and version. Its effects are carried out in the same transaction, and it writes an event row and an audit entry. Effects that belong to later steps are stubs until then:
   - the payment order and its withdrawal (Phase 6);
   - notifications (5.4).
4. **The routes:**
   - `POST /v1/bookings` takes `{"quote": id}` with a required `Idempotency-Key` header, which the OpenAPI document declares so the typed client asks for it.
   - `GET /v1/bookings/{code}` returns the student's own booking; a code is read as typed, in any case.

   Both are for people signed in by phone. Staff sessions get 403, and an agent reserves for a student from their visit (5.9). Holds are limited to 10 per student an hour, on top of the active-hold limit. With remote booking off, a hold answers 409 `BOOKING_NEEDS_VISIT`.
5. **Inventory does the bed work for bookings** through `BedHolds`:
   - lock a room type;
   - choose a free bed;
   - hold it for a booking;
   - release a booking's bed.

   The catalog gives it the locked beds, so inventory still never reads the catalog's tables.

## Consequences

- **"Done when."**
  - Fifty students asking at once for the last free bed get one 201 and 49 409s with `BED_UNAVAILABLE`, with one HELD booking and no overlapping active allocations.
  - A retry with the same key gets the first answer, marked as a replay, and makes no second booking. The same key with another body is refused (422), and a hold without a key is 400.
  - **The other tests:**
    - a hold takes a partly held room's bed at the quote's price;
    - every refusal above;
    - an expired hold frees its bed at exactly its fifteenth minute;
    - a clashing code is drawn again;
    - `booking_events` refuses updates and deletes.
- **Occupancy for pricing** still counts only offline tenants. Bookings join from TOKEN_SECURED, when a token can first be secured (5.4 and Phase 6). Holds never count (§8.2).
- **Next:** 5.4 confirms and rejects, 5.5 builds the student's pages on `GET /v1/bookings/{code}`, and 5.8 expires holds on a schedule as well as when the next hold comes.
