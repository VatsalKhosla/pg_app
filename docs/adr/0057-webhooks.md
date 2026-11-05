# ADR 0057: Webhooks: each event stored once and answered at once, a job doing the work, one settlement for checkouts and webhooks, and a late token taking the bed back or going back

- Status: accepted
- Date: 2026-11-05
- Build step: 6.2 (webhooks and event processing)

## Context

- **BUILD_PLAN 6.2:** raw-body HMAC verification, `payment_events` with a unique provider event id, a fast 200, outbox processing, idempotent status mapping, and late payments revived or refunded (§7.4).
- **Razorpay's docs, read on 2026-11-05:**
  - It delivers at least once, and not always in order.
  - Anything but a 2xx within 5 seconds is a failure. It retries for 24 hours, then turns the webhook off.
  - `X-Razorpay-Event-Id` identifies an event, but the signature covers only the body.
  - Its payment entity holds the student's phone, email and UPI id.
- **A payment can arrive after its hold ended:** a bank can take up to three days to answer, and a student can pay while their hold runs out.

## Decision

1. **`POST /v1/webhooks/razorpay` does as little as it can.** It checks the signature on the raw body, stores the event once, queues a job in the same transaction, and answers. A duplicate answers 200 and stops, so Razorpay stops sending it.
2. **What's refused gets a 400 and leaves nothing stored:** a bad signature, a body that isn't an event, or an event more than 48 hours old. Razorpay retries for 24 hours, so anything much older is a replay. The age comes from the signed body, because the event id isn't signed.
3. **An event we don't act on is still answered 200 and kept.** That covers a kind we don't handle, a payment that can't be read and an order that isn't ours. Refusing them would only make Razorpay retry and eventually turn the webhook off. One that can't be read logs an error and is marked, so it can be looked at.
4. **Only what the rules need is stored:** the kind, the time, and the payment's id, order, amount, currency and status. The `signature_valid` column ARCHITECTURE §6 planned isn't needed, since an unsigned event is never stored.
5. **Checkouts and webhooks reach the same settlement,** `PaymentSettlements.apply`, with the payment's row locked. The checks are the same whichever way the word arrived, a payment only moves forward, and captured money moves its booking once.
6. **A token after the booking moved on (§7.4):**
   - **Hold ended, bed free, move-in not passed:** `late_payment_revive` takes the bed back, the owner hears and gets their deadline, and the student is told it's paid.
   - **Hold ended, bed gone:** `late_payment_refund`. The booking stays expired, the student is texted and shown PGs like it. If the free check loses a race, the exclusion constraint refuses the bed and this path runs instead.
   - **The move-in has passed:** the same refund, even with the bed free. §7.4 doesn't cover this. A booking can't start on a day that's over, so the bed counts as gone.
   - **Cancelled while the student paid:** the booking doesn't move, and the payment stays captured and marked late.
7. **`RAZORPAY_WEBHOOK_SECRET` is now required with Razorpay,** so a real gateway can't run with webhooks it can't verify.

## Consequences

- **"Done when."** Tests cover the same event twice and at once, two events about one payment, events out of order, a webhook and a checkout at once, forged and tampered events, replays, and each late path including the lost race.
- **Refunds are still stubs.** The late-refund text says the token is refunded, and no money moves yet, as with every refund until step 6.3. That step also has to refund a token that arrives after a cancellation, which has no state-machine event. Nothing here is reachable with real money before step 6.8.
- **Webhooks need a public address.** Staging's is the API's own, `https://fys-staging-api.onrender.com/v1/webhooks/razorpay`. An API asleep on the free plan misses the 5 seconds, and Razorpay's retries wake it.
