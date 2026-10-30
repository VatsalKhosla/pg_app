# ADR 0044: Inventory allocations: a bed held for a period, by a booking, an offline tenant or maintenance, never two at once; availability and occupancy counted from them

- Status: accepted
- Date: 2026-10-30
- Build step: 5.1 (inventory allocations and availability)

## Context

- **BUILD_PLAN 5.1:** the `inventory_allocations` table with its exclusion constraint; availability queries per room type and period; offline-tenant and maintenance blocks, for ops now and owners in Phase 7.

  It's done when overlapping active allocations are impossible (a constraint test) and availability numbers match the allocations.
- **ARCHITECTURE §6:** the table, its `daterange` period `[move_in, move_out)` and the constraint `EXCLUDE USING gist (bed_id WITH =, period WITH &&) WHERE (is_active)`: the double-booking guarantee, never worked around.
- **§7.3 and §7.4:** a hold locks the room type's beds before choosing one; an offline block that meets a hold fails on the constraint, and the owner sees what holds the bed.
- **§8.2:** occupancy counts tenants and bookings from the token on, never holds. Until now, pricing's occupancy port said no bed was ever taken, and free beds were every active bed (ADRs 0039, 0040).

## Decision

1. **A new `inventory` module** owns the table. A row holds one bed for a half-open period of days, `[start, end)`. An open end means "until further notice", and a period always has a start. Its kind is:
   - a **booking**: its `booking_id` gets its foreign key with the bookings table in 5.3;
   - an **offline tenant** the owner placed without us;
   - **maintenance**.

   The database checks the kind, that only a booking has a `booking_id`, and the period. The exclusion constraint keeps two active allocations of one bed from sharing a day. An allocation ends by shortening its period or going inactive, and is never deleted.
2. **The domain says what a bed and a room are.** It is pure and holds:
   - the period and its overlap rule;
   - a stay's days (whole months, clamped to a month's last day);
   - what ops may block (at most two years ahead, a closed block at most five years);
   - **free beds** by their plain definition: those no allocation holds on any day of the period;
   - **occupancy** as tenants' beds over active beds, rounded down.

   The database's answers are tested against these definitions.
3. **Ops place and end blocks:**
   - `POST /v1/ops/beds/{id}/blocks` holds a bed for an offline tenant or maintenance. The bed's row is locked (§7.3) and checked for anything holding it then, with the constraint behind both. A clash answers **409 `BED_UNAVAILABLE`** saying what holds the bed and when; an impossible block answers **422 `BLOCK_INVALID`**.
   - `POST /v1/ops/blocks/{id}/end` frees the bed from a day, sooner or later than planned, checked again for a later end. On or before the block's first day, it cancels the block instead. A booking's allocation changes only with its booking (409).
   - `GET /v1/ops/properties/{id}/inventory?from=&days=` lists every bed with what holds it in the window, and each room type's beds free for all of it.

   Ops and admins only; every change is audited. Each change also writes `inventory.allocations_changed`, so search, the PG's pages and its prices follow.
4. **Other modules read availability through inventory's lookup.** The catalog gives inventory a PG's bed layout and a locked bed, so inventory never reads the catalog's tables:
   - the **PG page's calendar** and the editor's chart count free beds for a whole stay from the first move-in shown, so "only N beds left" counts tenants and maintenance too;
   - **search's summaries** count each month's free beds for a stay from its first move-in day;
   - **pricing's occupancy port** now reads a room type's tenants once per pricing pass and answers any move-in in memory. Offline tenants count now, bookings from the token on in 5.3, and maintenance and holds never do.

## Consequences

- **"Done when."**
  - A constraint test stores overlapping, adjacent, inactive and open-ended allocations straight into the table: only the overlapping active ones are refused.
  - Thirty ops asking for one bed at once get one 201 and 29 409s, with one active allocation left.
  - Forty random scenarios, each rolled back, find the database's free beds equal to the domain's count for random stays.
  - Another test shows an offline tenant filling a room to 50% and lifting a quote by the occupancy rule while maintenance doesn't, and the PG page and search following.
  - A browser test holds a bed from the ops console and ends it.
- **Step 5.3** adds the bookings table, the allocation's foreign key and the hold flow, and counts bookings from the token on in occupancy.
- **Phase 7** gives owners the same blocks for their own PGs.
