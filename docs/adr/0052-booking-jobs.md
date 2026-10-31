# ADR 0052: The booking jobs: four scheduled runs that each move a batch of due bookings through the state machine at the exact moment, change nothing when run twice, and count what they moved

- Status: accepted
- Date: 2026-10-31
- Build step: 5.8 (booking jobs)

## Context

- **BUILD_PLAN 5.8** asks for the four jobs in ARCHITECTURE §7.5, idempotent, observable and with metrics:
  - `expire_holds`: every minute;
  - `confirm_timeouts`: every 5 minutes;
  - `check_windows`: every 5 minutes;
  - `no_shows`: daily at 10:00 IST.

  It's done when running each job twice in a row changes nothing the second time.
- **Two already ran:** step 5.4 brought `booking.confirmation_timeouts` (ADR 0048) and step 5.6 `booking.check_windows` (ADR 0050).
- **Holds already expired, but only lazily:** a new hold on the same beds expired them (ADR 0046). A hold whose bed nobody wanted stayed HELD, and its bed stayed taken for search and pricing.
- **No-shows didn't end:** nothing ended a confirmed booking whose student never came.
- **§19** asks for bookings by state, transitions per hour and the hold expiry rate. The outbox already measures each job's runs, failures and lag (ADR 0007), but neither process sent metrics anywhere, and the worker didn't report errors to Sentry.

## Decision

1. **The four jobs** are all scheduled in `app/jobs.py`:

   | Job | When | Does |
   |---|---|---|
   | `booking.expire_holds` | every minute | HELD past `hold_expires_at` becomes EXPIRED; the bed is free again |
   | `booking.confirmation_timeouts` | every 5 minutes | TOKEN_SECURED past `confirm_by` becomes REJECTED |
   | `booking.check_windows` | every 5 minutes | CHECKED_IN past `check_window_ends_at` becomes ACTIVE |
   | `booking.no_shows` | daily, 10:00 IST | CONFIRMED past the move-in and the terms' wait becomes NO_SHOW |

   Each takes the earliest due first, locks its rows with `SKIP LOCKED` so a concurrent run or a new hold leaves them to the other, and moves each booking through the state machine as the system. The machine's guards decide the exact moment:
   - a hold ends at its expiry to the second;
   - a no-show comes the day after move-in plus `no_show_days`, by India's date, as each booking's own terms say;
   - the query only narrows the candidates.

   **Why it's idempotent:** a second run finds nothing due, because every change moves the booking out of the status the query looks for. A compare-and-set on status and version keeps two runs from moving one booking twice.
2. **A no-show:**
   - The bed is released.
   - The late-cancel rule decides the token. It's a stub until payments, and refund in full is the only rule a policy may take until Razorpay Route.
   - The student and the owner each get a text naming the last day the student could have arrived.
   - The student's text says whether the token comes back, from the same `late_refund` the cancellation page uses.
3. **Partial indexes** serve each scan:
   - `bookings(confirm_by) WHERE status = 'token_secured'`;
   - `bookings(check_window_ends_at) WHERE status = 'checked_in'`;
   - `bookings(move_in) WHERE status = 'confirmed'`.

   Holds had theirs already.
4. **Metrics**, through OpenTelemetry like the outbox's:
   - `booking.transitions`: every status change, by event, from, to and who sent it. This gives transitions per hour and the hold expiry rate.
   - `booking.job.changes`: what each job moved, by job.

   With `OTEL_EXPORTER_OTLP_ENDPOINT` set, the API and the worker each export their metrics every minute over OTLP/HTTP, labelled by process. Without it they stay off, like tracing. The worker now also starts Sentry, so a failing job reaches it.

## Consequences

- **"Done when."**
  - **Expiry:** a hold is still held a second before its expiry and ends at the second itself, with its bed released. A second run changes nothing.
  - **No-shows:** a booking is untouched on the last day of its wait and ends the next morning, with its bed released, stamped as ended by the system, and both texts sent. A second run changes nothing.
  - **The other two:** already tested twice by steps 5.4 and 5.6.
  - **Schedule:** a test checks each job's cadence against §7.5.
  - **Metrics:** a test reads `booking.transitions` and `booking.job.changes` through an in-memory reader.
- **The kept-token text** for a no-show is ready for a later policy that keeps the token. Its test stands in for that rule, which policies refuse today.
- **The bookings board (5.10)** can read these counts from the metrics backend once the founders choose one. That's a vendor choice, so nothing is wired to one yet.
