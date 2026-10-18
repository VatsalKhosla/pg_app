---
paths:
  - "apps/api/src/app/modules/pricing/**"
  - "apps/api/src/app/modules/booking/**"
  - "apps/api/src/app/modules/payments/**"
  - "apps/api/src/app/modules/ledger/**"
  - "apps/api/src/app/core/money.py"
  - "apps/web/src/features/booking/**"
  - "apps/web/src/features/pricing/**"
---

# Money, pricing and booking rules

Re-read the business rules in CLAUDE.md and `docs/PRODUCT_CONTEXT.md` §3–6 before changing code here. **If a change would alter what a student pays, what an owner pays, or when money moves, stop and ask the founders.**

- **Fee**: rate from `fee_policies` × the room category's **base** rent. Any change near fee code needs a test proving that pricing rules, occupancy and dates don't change the fee.
- **Prices** come only from the pricing engine through stored quotes. Bookings copy the quote's money fields and are never re-priced.
- **Engine purity**: `pricing/domain/engine.py` takes everything through `PricingContext`, with no I/O and no clock. Keep the Hypothesis invariants in ARCHITECTURE §8.8 passing; add one for every new rule kind.
- **Occupancy** for pricing counts TOKEN_SECURED-or-later bookings and offline tenants, never HELD beds.
- **State changes** only through `booking/domain/state_machine.py`, persisted with compare-and-set on status and version, with a `booking_events` row each time.
- **Inventory**: the exclusion constraint on `inventory_allocations` is the guarantee. After any change to hold logic, rerun the 50-concurrent-holds test.
- **Payments**: amounts are computed server-side. Only a verified webhook or a server-side fetch moves a booking; the browser callback just triggers verification. Processing is idempotent on the provider event id.
- **Ledger**: every money event is a balanced transaction written in the same database transaction as the state change. Never update or delete ledger rows; correct mistakes with reversing entries.
- **Refunds** always go through the `refunds` table and the gateway, with a reason and an audit entry.
- **Owner money** is never pooled: transfers to owners only through Razorpay Route (Phase 9).
- **Rounding**: integers only, half-up, at the points defined in ARCHITECTURE §8.3.
- **UI**: show the breakdown the server returns ("Base ₹10,000 · Peak season +15% · …"), the "price fixed for your stay" badge, and urgency text only when the API says it is backed by data.
