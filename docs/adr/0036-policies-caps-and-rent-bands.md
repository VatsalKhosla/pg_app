# ADR 0036: Policies, caps and rent bands: versioned tables that never overlap in time, seeded from PRODUCT_CONTEXT §9, changed by admins from now on, audited, with the founders' rules as limits

- Status: accepted
- Date: 2026-10-30
- Build step: 4.1 (policies, caps and rent bands)

## Context

- **BUILD_PLAN 4.1** asks for tables `fee_policies`, `booking_policies`, `pricing_caps` and `rent_bands`, with an admin UI and an audit log.
  - **Defaults** are seeded from PRODUCT_CONTEXT §9: a 30% fee on the listed rent, 18% GST exclusive, a ₹2,000 token, a 15-minute hold, free cancellation up to 7 days, a 24-hour check window, a 12-hour confirmation deadline, `refund_full` for late cancellations, one active hold per user, caps of +40% and −30%, and rounding to ₹50.
  - **No official rent bands** are seeded.
  - It's done when every default is editable by admins only and every change is audited.
- **CLAUDE.md**: business policy lives in tables, never constants. Rule 5: a quote's price is fixed for the stay, and rule changes never touch existing quotes or bookings.
- **ARCHITECTURE §6** gives the columns, with `effective_from` and `effective_to`. Step 4.4's quotes will record the `fee_policy_id` they used.
- **Step 3.8** served the defaults from constants behind `GET /v1/policies` (ADR 0034), waiting for these tables.

## Decision

1. **Versions, never edits.**
   - Each table holds versions in force from `effective_from` until `effective_to` (open for the current one). A change ends the version in force at that moment and adds the next.
   - A gist **exclusion constraint** on `tstzrange(effective_from, effective_to)` keeps any two versions from overlapping. For rent bands, it applies per locality and occupancy, through btree_gist. So at any moment at most one version is in force.
   - Versions are never updated otherwise, so a quote can say which one priced it.
2. **The founders' rules as limits**, in the pure domain (`pricing/domain/policies.py`), with the database's checks behind them:
   - the token stays from ₹1,000 to ₹2,000 (rule 8, PRODUCT_CONTEXT §3);
   - the fee's basis is the listed rent only (rule 2);
   - rates stay from 0 to 100%, and the discount cap at 90% at most;
   - the rounding step is whole rupees, ₹1 to ₹1,000;
   - each booking term has a sensible range;
   - late cancellation can only be `refund_full` until payments go through Razorpay Route (PRODUCT_CONTEXT §9);
   - a band's lowest rent is above zero and at most its highest, and an official band needs its reference (the notification it comes from).

   A change that breaks one answers **422 `POLICY_INVALID`** with every problem. Sending the version already in force is refused too.
3. **Seeded by a data migration**, apart from the schema migration, with the values written out. The seeds are in force from 1 January 2026 and carry the note "The defaults in PRODUCT_CONTEXT §9.". The step 3.8 constants are gone.
4. **Admins only** (`can_manage_pricing_policies`: the admin role, in a staff session). The routes:
   - `GET /v1/admin/policies` and `/history`;
   - `POST /v1/admin/policies/fee`, `/booking` and `/caps`;
   - `GET` and `POST /v1/admin/rent-bands`, and `POST /v1/admin/rent-bands/{id}/end`.

   Every change writes an audit entry with what the policy was, what it became and the admin's note.
5. **One change at a time.** Each change takes an advisory lock for its table, so the next waits and then sees it.
   - If the version in force started the same instant (two admins at once), the second gets **409 `INVALID_TRANSITION`** and reloads.
   - Setting a band ends the band in force for its locality and occupancy.
6. **The public side.** `GET /v1/policies` reads the versions in force. A policy change asks the web app to revalidate the new `policies` cache tag, so the Pricing, token and refund pages say the new terms at once. If a version were missing, the API would answer **503 `PRICING_CONFIG_ERROR`** rather than guess.
7. **The admin console** is `/admin/policies` and `/admin/rent-bands`, with noindex and admins only (other staff go to the staff home).
   - A form per policy starts from the version in force: rates in %, amounts in ₹, terms in whole numbers, all converted without floating point.
   - Each policy shows its recent versions, with who set them.
   - Bands are set and ended per locality and occupancy.

## Consequences

- **Step 4.2's engine** takes these policies as values (`FeePolicy`, `BookingPolicy`, `PricingCaps`, `RentBand`) through `PricingContext`. Step 4.4's quotes store the versions' ids.
- **Changes take effect from now only.** A future-dated version isn't supported yet; an announced change is applied on its day.
- **The founders** can now change any default themselves, as admins, and every change is in the audit log. Phase 6's Route work should allow `forfeit_to_owner` and `split`.
