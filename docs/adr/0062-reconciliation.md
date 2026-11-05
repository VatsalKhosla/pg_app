# ADR 0062: Reconciliation: the gateway asked about what hasn't come back, its settlement reports matched line by line, and what doesn't match kept for ops

- Status: accepted
- Date: 2026-11-06
- Build step: 6.6 (reconciliation)

## Context

- **BUILD_PLAN 6.6:** 15-minute stuck-payment checks; daily settlement matching; mismatch alerts and an ops dashboard.
- **Webhooks can be late or lost.** Razorpay retries for 24 hours and then turns a webhook off. A checkout's callback can be lost with the student's network.
- **Razorpay's settlement report** (`/settlements/recon/combined`) lists each payment with the fee it kept (GST included), each refund it took back from a payout, and transfers and adjustments.

## Decision

1. **Every 15 minutes, the gateway is asked about what hasn't come back,** and its answer goes through the same path a webhook's would:
   - a token whose checkout is 5 minutes to 3 days old (5 minutes leaves time to secure the booking inside its 15-minute hold): the order's attempts, a captured one settled as a checkout would be;
   - an owner's payment link made in the last 3 days, and every open link once a day;
   - a refund the gateway has and the bank hasn't confirmed.
   At most 50 of each per run, and a gateway out of reach ends the run quietly: the next one tries again.
2. **Every morning, the last three days' settlement reports,** line by line. Reading a day again is harmless:
   - a payment we captured, for the same amount: its fee posted (`payment_fees` against gateway clearing) and the payout (`bank` against gateway clearing), each once by its key;
   - a refund we processed: what the payout lost to it (gateway clearing against `bank`);
   - anything else, an issue: a payment or refund we have no record of, a different amount, one not captured or processed here, and transfers and adjustments, which come with split settlement in Phase 9.
3. **A captured payment no report has settled in a week** is an issue, once the gateway is one that pays a bank (the fake gateway doesn't).
4. **Issues are kept, once each,** by kind and the gateway's reference: logged as errors, so they alert, counted in a metric, and shown at `/ops/reconciliation` until ops close each with what they did (audited). So are a payment the bank said yes to that nobody captured within an hour, a refund not taken by the gateway within an hour or not sent within a week, and a link paid other than as asked.
5. **Every payment row records when it was asked for, by the app's clock** (`made_at`), so the checks never mix the database's clock with the app's.

## Consequences

- With the fake gateway nothing is ever stuck or unsettled: it says only what a test tells it, so on the test site an abandoned checkout stays unpaid.
- **The GST on the gateway's fee** is posted inside the fee for now; whether it's claimed as input credit is for the accountant.
- Tests cover a lost checkout found at the gateway, a payment authorized and never captured, a refund that arrives late, a report posted once with what doesn't match closed by ops, and a payment no report settled.
