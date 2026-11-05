# ADR 0059: Refunds: saved first and sent by a job, asked for by bookings through the outbox, a second person above the threshold, and the gateway's word recorded either way

- Status: accepted
- Date: 2026-11-05
- Build step: 6.3 (refunds)

## Context

- **BUILD_PLAN 6.3:** automatic refunds on reject, timeout, free cancellation, hold-expired payments and resolved disputes; manual refunds by ops with a reason and two-person approval above the threshold; refund webhooks. It's done when every path is tested and visible to the student with a status.
- **Bookings never call payments** (ADR 0056), but the state machine says when money goes back.
- **Razorpay's docs, read on 2026-11-05:**
  - A refund's `receipt` works as its idempotency key: a repeated one is refused as a duplicate.
  - Refunds take `speed`: `normal` takes 5-7 working days, and `optimum` is instant where it can be. The refunds page lists no fee for either.
  - It refunds uncaptured payments by itself, and sends `refund.*` webhooks for those too.

## Decision

1. **Bookings ask through the outbox.** Carrying out `RefundToken`, or the late-cancel rule, queues `booking.refund_due` in the booking's own transaction, with the amount the booking's terms say. The job in the payments module finds the token that came in and saves the refund. A booking with no captured token has nothing to give back.
2. **A refund is saved, then a separate job sends it,** so no gateway call happens inside a change, and none is lost if the process dies.
   - A failure that may pass raises, and the outbox retries with backoff. The receipt makes that safe: a repeat finds the first refund.
   - A refusal is final. The refund is marked failed with Razorpay's words, and an error is logged.
   - A refund that failed or was declined stops counting against the payment, so ops can give the money back another way.
3. **Only what's left can go back.** Anything but a failed or declined refund counts against the payment, under the payment's row lock, so two refunds can't take the same money.
4. **A token after its booking moved on goes back too.** One from a hold that ended comes through `late_payment_refund`. One after a cancellation has no state-machine event, so the settlement asks for it directly (ADR 0057).
5. **Ops' refunds take a reason.** Above ₹5,000 (`REFUND_SECOND_PERSON_ABOVE_PAISE`, per ARCHITECTURE §17) a refund waits for a second person, who can approve or decline it. The person who asked can't approve it, and a database check enforces that as well. They can withdraw it by declining.
6. **The gateway's word is recorded either way.** Refund webhooks move a refund forward by its id or its receipt, whichever arrives first. A refund nobody here asked for, from Razorpay itself or its dashboard, is recorded by its payment or order, and counts against what's left.
7. **Students see it on their booking** (`GET /v1/bookings/{code}/payments`): what came in, each refund's status, and the bank's reference once there is one. They're texted once a refund is processed. A refund waiting for approval or declined isn't shown to them.
8. **`normal` speed by default** (`REFUND_SPEED`). Rule 8's "the same day" is met by issuing the refund the same day; the bank then takes its 5-7 working days. Instant refunds may cost more, and Razorpay's refunds page doesn't say, so that's the founders' choice once they've seen the price.

## Consequences

- **"Done when."** API tests cover each way a booking ends, a dispute, a late token, a token after cancelling, a gateway out of reach, a refusal, a pending refund and its webhook, a webhook before the answer, refunds nobody here asked for, what's left, the two-person rule, and the queue. A phone browser test follows a rejected booking's refund to the student's page.
- **The ledger comes next.** Step 6.4 posts these refunds' entries in the same transactions.
- **A failed refund needs a person.** It shows on the Refunds page and logs an error. Step 6.6's reconciliation adds the alert for one stuck over 24 hours.
