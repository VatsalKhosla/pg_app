# ADR 0048: The confirmation flow: the owner (or ops) answers a booking with the token in, a PG that confirms itself does so at once, and silence past the deadline rejects it

- Status: accepted
- Date: 2026-10-31
- Build step: 5.4 (confirmation flow)

## Context

- **BUILD_PLAN 5.4:**
  - owner or ops confirm or reject;
  - `instant_confirm` per property;
  - a confirmation-deadline job → REJECTED, with refund hooks stubbed until Phase 6;
  - notifications.

  It's done when all three paths work end to end with notifications.
- **The state machine** (ADR 0045) already has these rows:
  - `token_secured` sets the owner's deadline (`confirm_deadline_hours`, 12 now) and asks for auto-`confirm` when the PG confirms itself;
  - `confirm` and `reject` come from the owner or ops;
  - `confirm_timeout` comes from the system once the deadline passes.
- **A token is secured by a verified gateway event, which is Phase 6.** Nothing in the API secures one yet.
- **Texts go through the `Texts` port**, as visits' do: a DLT-registered template per message, a provider the founders choose, and the log or nothing until then (ADR 0033).

## Decision

1. **One core carries out every status change** (`booking/service/transitions.py`), for holds and everything after:
   - the state machine's answer, or 409 `INVALID_TRANSITION`;
   - a compare-and-set on status and version, with what the effects set: the hold's expiry, the owner's deadline, the check window;
   - what the new status stamps: when the booking was confirmed, checked in, became active or completed; or, when it ended early, when, by which party and by which event;
   - the effects carried out;
   - a `booking_events` row (with a note, such as a rejection's reason) and an audit entry.

   An instant-confirm PG's `confirm` follows as a step of its own, from the system.
2. **Effects that belong to later steps are stubs** that leave the money untouched:
   - the payment order and its withdrawal;
   - recording, refunding or settling the token (Phase 6, with the ledger);
   - finding similar PGs (5.7; the student's text promises help).
3. **The desk** (`BookingDesk`) is where an owner or ops see a booking and answer it:
   - `GET`, `POST …/confirm` and `POST …/reject` (with a reason of up to 500 characters) under `/v1/owner/bookings/{code}` and `/v1/ops/bookings/{code}`;
   - an owner reaches only their own PGs' bookings, and anyone else's is a 404;
   - ops answer any booking, audited as themselves;
   - the row is locked while it changes, so a second answer finds the booking answered (409).

   The view shows the room, the bed, the money, the deadline and the student's first name. Their number waits for the student's pages and the ops board (5.5, 5.10).
4. **What the system does** (`BookingSystem`), in the caller's transaction:
   - `secure_token(booking, paid_paise)` is what Phase 6's verified payment will call. The amount must be the booking's token. Tests use it now.
   - `time_out_confirmations()` rejects bookings past their deadline, the most overdue first. It locks with SKIP LOCKED, so two runs never take the same booking. A job runs it every five minutes (§7.5).
5. **Texts** go through a `booking.notify` job per party a transition names. When it runs, it sends only if the booking is still in the status the transition left it in. Ops get no texts: they work from the bookings board (5.10). The templates are in `booking/texts.py`:
   - **to the owner, as the token comes in:** the room type, the move-in day and the deadline. A PG that confirms itself gets a "new booking, confirmed" text instead.
   - **to the student, once confirmed:** the move-in day and **the exact address**, which they get only now (rule 11).
   - **to the student, if rejected or not confirmed in time:** a full refund and help to find another PG.
   - **to the owner, if they missed the deadline:** the booking is cancelled and the student refunded.
6. **The student's data export** gains their bookings: the money each fixed, and every change, from the hold on. Bookings were personal data from 5.3, and this closes that gap.

## Consequences

- **"Done when."** End-to-end tests cover:
  - an owner confirming once the token is in (not before, and not twice);
  - ops rejecting with a reason, after which the bed is free for the next student;
  - silence for 12 hours less a second, then one second more, after which a second run of the job changes nothing;
  - an instant-confirm PG confirmed by the system as the token comes in.

  Each test checks the texts sent, the booking's history and its stamps. The authorization matrix and a test of who may answer what (another owner 404, a student 403, the wrong console 403) cover access. A short payment doesn't secure the token.
- **Owners answer through the API until their dashboard** (Phase 7); ops have it through theirs once 5.10 builds the board.
- **Occupancy for pricing** still waits for TOKEN_SECURED to happen for real (Phase 6).
