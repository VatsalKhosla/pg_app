# ADR 0050: Moving in: the student says so from the day before the move-in, their 24 hours to check the room start on their word, ops can only ask them to, and a job settles the booking at the window's exact end

- Status: accepted
- Date: 2026-10-31
- Build step: 5.6 (check-in and the 24-hour window)

## Context

- **BUILD_PLAN 5.6:**
  - "I've moved in" (or ops-marked with student confirmation);
  - a real countdown for the window;
  - a job that makes the booking ACTIVE at the end.

  It's done when time-travel tests cover check-in, the window's end and the edge at exactly 24 hours.
- **Rule 8:** no money is earned until the student has moved in and the 24-hour check window passes without a dispute.
- **The state machine (ADR 0045)** already has these rules:
  - CONFIRMED → CHECKED_IN is the student's move, from the day before the move-in, and it sets the window's end from the booking's terms (`check_window_hours`, 24 by default).
  - CHECKED_IN → ACTIVE is the system's move once that end has come. It earns the token and invoices the owner, which are Phase 6 stubs until payments exist.
- **Rule 7 and ARCHITECTURE §8.5** allow a countdown only for a real hold's expiry, against false urgency. The build plan asks for a real countdown here too.

## Decision

1. **The student says they've moved in** with `POST /v1/bookings/{code}/check-in`.
   - The state machine decides when it's allowed: on a confirmed booking, from midnight in India on the day before the move-in. Anything else is 409 `INVALID_TRANSITION`, with the machine's reason.
   - Their window starts at that moment, and the owner gets a text with its exact end.
   - The student's booking now carries:
     - `checkInOpensOn` while it's confirmed;
     - `canCheckIn`, from a new pure `allows()` that asks the same `transition()`, so the page never offers what the API would refuse;
     - `checkWindowHours`, from the booking's terms;
     - `checkWindowEndsAt`.

   The owner and ops see when the student moved in and when the window ends.
2. **Ops can't move the booking for the student.** The window decides when the token is earned, so it starts on the student's own word.
   - Ops' `POST /v1/ops/bookings/{code}/move-in-reminder` texts the student to confirm, and the booking doesn't change.
   - It works only while the student may check in, at most once a day per booking (the outbox's dedupe key carries India's date). It answers `{"sent": false}` when the student was already asked that day.
   - Every press is audited, sent or not.
3. **`booking.check_windows` runs every five minutes.**
   - It moves every checked-in booking whose window has ended to ACTIVE through the state machine, 100 at a time, and the next run takes the rest.
   - A booking is due at exactly its `check_window_ends_at`, never a second before.
   - A second run finds nothing to do.
   - The student and the owner each get a text that the booking is settled.
   - Earning the token and the owner's invoice stay stubs until Phase 6, so no money moves.
4. **Texts use the booking's own terms:** the hours in the student's nudge, and the exact end in the owner's text. They don't assume 24.
5. **The web app:**
   - **Checking in:** a confirmed booking offers "I've moved in" once the API says so. The student is asked once more before it's sent, and the question says what it starts.
   - **The countdown:** while checked in, the page shows the window's end, and then how long is left in whole minutes rounded down. It updates every 15 seconds, shows no seconds, nothing flashes, and screen readers aren't interrupted.
   - **Why the countdown is allowed:** rule 7 and §8.5 forbid countdowns that pressure a purchase. This one shows the student how long they have to protect their own money, and it asks them to buy nothing. Its time-left text is formatted in the browser, through a scoped `NextIntlClientProvider` (ADR 0011).

## Consequences

- **"Done when."**
  - **Check-in:** time-travel API tests refuse it at 23:59:59 in India two days before the move-in and allow it one second later. Another student's booking is a 404, and a second check-in is refused.
  - **The settling job:** the booking stays checked in at 24 hours less one second and becomes ACTIVE at exactly 24 hours. A second run changes nothing.
  - **The nudge:** sent, then not sent the same day, then sent the next day. The booking is unchanged, and the nudge is refused once the student has said so.
  - **Unit tests:** `allows()` and `check_in_opens_on()`.
  - **Component tests:**
    - the check-in action in every status, axe included;
    - the confirm, not-yet, changed and failed flows;
    - the countdown, from 23 hours 59 minutes down to its last minute and past its end.
- **Disputes (5.7)** will use the same window: the "room not as shown" form shows only while `checkWindowEndsAt` is ahead.
- **The owner's money** still waits for Phase 6 and Razorpay Route (rule 10). Until then, ACTIVE only records that the token would now be earned.
