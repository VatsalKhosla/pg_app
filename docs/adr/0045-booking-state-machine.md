# ADR 0045: The booking state machine: one pure table of the founders' rules, side effects as descriptors the services carry out, and a refusal for everything else

- Status: accepted
- Date: 2026-10-30
- Build step: 5.2 (booking state machine, pure)

## Context

- **BUILD_PLAN 5.2:** the transition table of ARCHITECTURE §7.2 with guards and side-effect descriptors; exhaustive tests over every (state, event) pair; property tests that random event sequences never break invariants, such as no money earned before ACTIVE.

  It's done when every allowed transition is tested and every other pair is rejected with `INVALID_TRANSITION`.
- **CLAUDE.md:** every booking status change goes through `booking/domain/state_machine.py`, saved with a compare-and-set on status and version and a `booking_events` row each time.
- **Rule 8:** no money is earned until the student has moved in and the 24-hour check window passes without a dispute. **Rule 9:** free cancellation up to 7 days before the move-in, then the late-cancel policy.
- **§7.4:** a payment that arrives after its hold expired takes the bed back if it's still free, and is refunded if it isn't.

## Decision

1. **One pure module.** It knows 12 statuses, 17 events and 4 parties: the student, the owner, ops, and the system (the jobs and the gateway's verified events).
   - `hold(now, terms)` opens a booking as HELD.
   - `transition(facts, event, party, moment, terms)` answers the next status and its side effects. Otherwise it raises `TransitionRefusedError`, which the services answer with **409 `INVALID_TRANSITION`** and the reason.
   - The facts are the booking's move-in, token, instant-confirm setting and deadlines. The moment is the time, plus what came with the event: a payment's amount, whether the bed is still free, a move-out day.
   - Date guards use India's day, taken from the moment.
2. **The table is §7.2's and §7.4's rows, and nothing else.** A test holds it equal to the spec. The machine refuses in this order, and each refusal says why in words:
   - a pair the table doesn't have ("A checked-in booking can't be cancelled.");
   - a party the row doesn't name;
   - a guard that doesn't hold.

   The guards:
   - the payment is the booking's token;
   - the hold or the confirmation deadline has run out;
   - free cancellation lasts until the day the terms say, and a late cancellation is any day after it;
   - checking in opens the day before the move-in;
   - a no-show comes after the terms' days;
   - a dispute is inside the check window, and the window's end is reached;
   - a move-out comes after the move-in.
3. **Side effects are descriptors.** The services carry them out in the transaction of the status change:
   - **the bed:** activate, deactivate, or cut short at the move-out;
   - **deadlines:** the hold's expiry, the owner's confirmation deadline, the check window's end;
   - **the payment:** request it, withdraw it;
   - **money:** token received, refunded, settled by the late-cancel policy, earned, the owner's invoice;
   - **disputes:** open and close;
   - **people:** flag an owner who cancels, suggest similar PGs, and say who hears about each change.

   **`EarnToken` and `IssueOwnerInvoice` appear only on the way into ACTIVE**: the one place a booking makes money. The ledger, refunds and invoices that carry these out come in Phase 6; until then their hooks are stubs.
4. **Where §7.2 leaves room, the stricter reading.** None of these changes a founders' rule:
   - **Ops-marked move-ins.** The row says "student; or ops, then student confirms". Ops may mark a move-in (5.6), but only the student's confirmation sends `check_in`. The check window, which decides when the token is earned, therefore starts on the student's word.
   - **Auto-confirm.** For a PG that confirms its bookings itself, a secured token asks for `confirm` at once, from the system, as its own transition with its own event row. For any other PG, the system can't confirm.
   - **The owner's deadline.** It is set when the token is secured, for the terms' hours (12 now). `confirm_timeout` is refused before it.
   - **A cancelled hold** withdraws its unpaid order or UPI block, as an expired hold does.
   - **Late payments** are two system events.
     - `late_payment_revive`: the bed is held again and the booking goes on as if the token had come in time.
     - `late_payment_refund`: the payment is recorded and refunded at once, with similar PGs suggested, and the booking stays EXPIRED.
   - **A move-out** is recorded once its day has come, and frees the bed from that day.

## Consequences

- **"Done when."**
  - All 816 (status, event, party) triples are tested: each allowed one reaches the spec's status, each other pair is refused, and so is each wrong party.
  - Every guard is tested at its edge: a hold and a deadline at their exact second, and free cancellation at 23:59 and at 00:00 in India. Then a check-in the day before the move-in, a no-show on the terms' last day and the day after, and the check window at exactly 24 hours.
  - A property test plays random histories of up to 60 events: 200 locally, 10,000 in CI, steered along the happy path a third of the time so they reach disputes, move-outs and late payments. After every step it checks:
    - money is earned only on the way into ACTIVE, at most once, with one invoice;
    - the bed is held exactly in HELD through COMPLETED;
    - the token is kept exactly from TOKEN_SECURED to DISPUTED, and refunded or settled only when kept;
    - every countdown ends in the future;
    - a final status takes nothing.
  - Branch coverage is 100%, now part of `make coverage-money`.
- **Step 5.3** adds the bookings table with its status, version and these facts, plus `booking_events`. Its services apply transitions with a compare-and-set and answer refusals with 409. Each booking keeps the terms (booking policy version) its quote carries, so a later change to the terms never alters a booking already made.
- **Later steps** send these events: the confirmation flow (5.4), check-in (5.6), disputes (5.7), the booking jobs (5.8) and the gateway's events (Phase 6).
