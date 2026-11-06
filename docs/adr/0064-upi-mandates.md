# ADR 0064: Tokens blocked by a UPI one-time mandate: secured on the gateway's word, debited once after the notice when the booking settles, and released when it ends first

- Status: accepted
- Date: 2026-11-06
- Build step: 6.7 (UPI one-time mandate mode, flagged)

## Context

- **PRODUCT_CONTEXT §3, "Block, don't take":** where the gateway allows, the token stays blocked in the student's own account and is debited once, after move-in and the 24 hours to check the room (rule 8). Otherwise it's a normal payment held until then.
- **BUILD_PLAN 6.7:** mandate create, capture and release in the adapter; a validity check against move-in and the window; a fallback to payment mode; behind `token_mode`, built once the founders confirmed Razorpay enabled mandates (they did, 2026-11-06).
- **Razorpay's one-time mandate** (its docs, read 2026-11-06):
  - a customer, and an order with `method: upi` and a `token` (`max_amount`, `expire_at`, `frequency: one_time`), authorised at checkout with `recurring: 1`. The authorisation is a "dummy" payment that names the mandate (its token);
  - the bank blocks the amount until the mandate is debited or expires, and unblocks anything not debited;
  - a debit takes its own order with a `notification` (`token_id`, `payment_after`), which sends the student the notice NPCI asks for, then `POST /payments/create/recurring`;
  - `PUT .../tokens/:id/cancel` cancels the mandate;
  - its token webhooks are `token.confirmed`, `token.rejected`, `token.cancelled` and `token.paused`.

## Decision

1. **A token is taken by mandate only when** `token_mode` is `upi_mandate`, the gateway takes mandates, and the mandate can last until it's needed: the end of the last day the student may still move in, plus the check window, the 26-hour notice and a day's margin, no more than `UPI_MANDATE_MAX_DAYS` (90) away. Otherwise it's a normal payment, as before.
2. **Blocked, not taken.** The gateway's word that the mandate is confirmed secures the booking, exactly as a captured payment does. That word comes from its webhook, the checkout's own check, or reconciliation. Nothing is posted to the books, because no money has moved. The browser asks the API about the block whatever checkout hands back (`POST /v1/payments/{id}/mandate-check`), since the authorisation shows up as a failed "dummy" payment. Webhooks come in any order: a `token.confirmed` that arrives before the payment event naming its mandate finds nothing to move, so when a payment event first names a mandate, a job (`payments.mandate_ask`) asks the gateway whether it's confirmed.
3. **Debited once, when earned.** A settling booking announces its earned token through the outbox (`booking.token_earned`), as bookings ask for refunds: bookings never call payments. A job orders the debit, which sends the notice, and another debits after it. The capture posts the token as received, as a paid token's does, so the books are the same either way once it's in.
4. **Given back when the booking ends first.** A full refund releases the block, and the bank unblocks the money. A partial one (the late-cancel rule) debits only the part kept, and the bank unblocks the rest. Each decision is saved before the call that carries it out, so a job that dies is tried again, and the gateway's own `token.cancelled` after our debit or release changes nothing.
5. **Ops hear** of a debit the bank refuses, or a mandate cancelled or paused before we debited it, as reconciliation issues (ADR 0062). Reconciliation also asks about a block or a debit that hasn't come back.
6. **The fake gateway takes mandates too**, so the test bank and the tests run the real path.

## Consequences

- **Open until verified in Razorpay's test mode** (the step's "done when"): set `TEST_SITE_TOKEN_MODE` to `upi_mandate` on the test site and reserve, pay, settle and cancel there. Points to confirm then:
  - The authorisation order's amount: we send the token as both the amount and the `max_amount`.
  - The debit's email: students sign in by phone, so we send Razorpay's `void@razorpay.com`.
  - The token webhooks' payload shape.
  - Whether banks take a 90-day mandate: `UPI_MANDATE_MAX_DAYS` says how long we ask for.
- Between settling and the debit, about a day, the token is applied on the books before it's received: the students' tokens account shows it due from the gateway until the debit comes in, and an issue if it doesn't.
