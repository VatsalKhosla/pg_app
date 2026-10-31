# ADR 0053: Reserving on the spot: at the visit, once the agent has checked in, the student reserves a bed from their own phone on the visit's day, whatever remote booking's flag says, and the visit log links to the booking

- Status: accepted
- Date: 2026-10-31
- Build step: 5.9 (on-spot booking from a visit)

## Context

- **BUILD_PLAN 5.9:** from a checked-in visit, the agent opens "Reserve now" for the student. The booking's channel is `on_spot`, it is linked by `visit_id`, and it is usually instant-confirm. It's done when the visit-to-booking path works on a phone and the visit log links to the booking.
- **ARCHITECTURE §11:** the agent opens **Reserve now** on the student's phone, and the student goes through quote, hold and token.
- **PRODUCT_CONTEXT:** season one is visit-first. Students pay the token on the spot after a visit with our field agent, and remote booking stays behind its flag (`remote_booking_enabled`, off).
- **The visit log is our proof of introduction** (the agent's check-in: time, GPS, distance; ADR 0033). The owner agreement charges the fee for any student we introduced.

## Decision

1. **The student reserves, from their own phone.**
   - The hold is the student's own request, as any hold is, with their own quote. It takes the student's visit (`POST /v1/bookings {quote, visit}`).
   - The agent's part is the check-in that proves they're both at the PG. The agent can't act for the student, and the student never hands over an account.
2. **When a visit allows it** is a pure rule in the visits domain (`on_spot_problem`):
   - the agent has checked in for it;
   - the student came (not cancelled, not a no-show);
   - it's still the visit's day in India.

   A recorded outcome doesn't stop it, so a student who says "interested" and decides an hour later can still reserve.

   The booking module asks visits through `VisitLookup.on_spot`, which locks the visit and answers:
   - **404** for anyone else's visit;
   - **409 `VISIT_NOT_ON_SITE`**, with the reason, for a visit that can't take a reservation;
   - also **409 `VISIT_NOT_ON_SITE`** for a quote for another PG.

   The dependency runs one way, booking to visits.
3. **A hold with a visit is `on_spot`** and carries the visit's id (the bookings table's check constraint already pairs them).
   - It doesn't need remote booking on. Without a visit, the flag still decides, and the answer is `BOOKING_NEEDS_VISIT`.
   - **Confirmation:** it follows the PG's own instant-confirm setting, which is "usually" yes for PGs with agents on the ground. Nothing is forced.
   - **Everything else is the hold of ADR 0046:** idempotency, limits, bed choice, the exclusion constraint.
4. **The visit log links to the booking.** In the same transaction, the visit records the booking's code (`visits.booking_code`, the latest if a student reserves again after a hold expired).
   - Ops' visit log shows "reserved a bed on the spot: booking BK-…".
   - The agent's visit page shows it.
   - The student's visit links to the booking.

   Bookings show their channel to the student, the owner and ops.
5. **The web app:**
   - **The student's visit** offers "Reserve a bed here" once the agent has checked in. It opens the PG's page with the visit in the link (`?visit=`).
   - **On the PG page,** checking a price there also offers "Reserve this bed".
   - **Retries:** each quote gets its own Idempotency-Key, so a retry of the same reservation replays its first answer rather than holding twice.
   - **Refusals:** each says why, with the API's reason where it has one.
   - **Success** opens the booking's page, where paying the token waits for Phase 6.

## Consequences

- **"Done when."**
  - **The phone browser test:** it now goes on from the agent's check-in. The student, on a phone, reserves a bed from their visit while remote booking is off and lands on the held booking. Ops' visit log shows the booking's code.
  - **API tests** cover:
    - a reservation refused before the check-in;
    - a hold without the visit refused while remote booking is off;
    - the on-spot booking linked both ways;
    - another student's visit, a quote for another PG, and the next morning, each refused.
  - **Unit tests** cover the rule at the day's end in India.
  - **A component test** covers the quote checker: no reservation away from a visit, reserving and opening the booking, a refusal with its reason, a retry with the same key, and a new key for a new price.
- **Paying the token on the spot** comes with Phase 6. Until then an on-spot hold expires like any other, freeing the bed, and the student can reserve again that day from the same visit.
- **The fee:** the owner agreement's 90-day introduction rule can now point at the visit and the booking it led to.
