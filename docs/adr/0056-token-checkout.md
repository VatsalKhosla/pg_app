# ADR 0056: Paying a token: an order made when the student taps, checkout on a page of its own, and only the gateway's own word moving a booking

- Status: accepted
- Date: 2026-11-05
- Build step: 6.1 (gateway port and Razorpay adapter)

## Context

- **BUILD_PLAN 6.1:** a gateway port, `FakeGateway` with signed webhook fixtures, Razorpay orders for the exact token, web checkout and server-side signature checks, on test keys only.
- **ARCHITECTURE §9.2:** only a verified webhook or a server-side fetch moves a booking. The checkout signature alone doesn't.
- **The backend rules:** no outside call while holding row locks inside a transaction.
- **Razorpay's docs, read on 2026-11-05:**
  - A receipt must be unique, and a second order with the same one is refused.
  - Orders can be found by receipt.
  - Auto-capture is the default.
  - The signature is an HMAC of our own order id and the payment id.
  - There's no published list of what Checkout needs from a page's security policy.
- **There are no Razorpay keys yet,** and the company's account doesn't exist. The founders' personal account isn't to be wired into the product without asking.

## Decision

1. **A `payments` module calls bookings, never the other way round** (an import-linter contract). `BookingTokens` is all it asks of them: which token is due, whose booking it is, and that it came in.
2. **No SDK.** `RazorpayGateway` is two calls and two HMACs over the shared HTTP client, behind the `PaymentGateway` port. Refunds join the port in step 6.3, UPI mandates in 6.7 and split settlement in Phase 9, each as its step builds it.
3. **The order is made when the student taps Pay,** not during the hold: `POST /v1/bookings/{code}/payment`, a read, a gateway call and a write, with no lock across the call.
   - A hold nobody pays for makes no order.
   - The amount is the booking's. The request doesn't carry one.
   - **It's idempotent by its nature,** so this route takes no `Idempotency-Key`, unlike what §15 asks of other money routes. A booking has one payment per gateway (`idempotency_key`), and one receipt. A lost answer finds the same order by its receipt, and two requests at once keep whichever was saved first.
4. **What moves a booking:** `POST /v1/payments/{id}/checkout-callback` checks the signature against our own order id, then fetches the payment from the gateway outside any lock. Then, in one transaction with the payment's row locked:
   - **Paid** means captured, for this order, in its exact amount, in rupees. The payment is captured and the booking moves with it, through the state machine.
   - **Waiting** means created or authorized, or the gateway can't be reached. Nothing moves. The browser asks a few more times, and step 6.2's webhook settles it anyway.
   - **Not paid** means the gateway says failed or refunded. The student can try again.
   - **A mismatch** moves nothing, is audited and logged as an error, and answers 409 `PAYMENT_MISMATCH`.
   - A payment only moves forward, and a repeated answer changes nothing.
5. **The hold's end:** Checkout gets the hold's time left as its `timeout`, so it closes by then. A new payment can't start once the time is up. A payment already under way still counts while the booking is held, since the bed is still the student's. If the booking has moved on, the money stays recorded as captured and the student is told. Step 6.2 then revives the booking or refunds the money (§7.4).
6. **A fake gateway for everything without keys:** tests, local work and the test site.
   - It signs exactly as Razorpay does, so everything downstream is the real path.
   - Everything it knows is in its ids, so it needs no memory between processes.
   - `POST /v1/payments/{id}/test-checkout` is its bank page, and answers 404 with a real gateway.
   - **Production refuses it.** Keys can't mix either: `rzp_live_` only in production, and `rzp_test_` everywhere else.
7. **Checkout has a page of its own, `/bookings/{code}/pay`.** Razorpay needs a frame from `api.razorpay.com`, reports to `lumberjack.razorpay.com`, needs the `payment` permission in its frame, and may use popups (`Cross-Origin-Opener-Policy: same-origin-allow-popups`). The rest of the site keeps its stricter policy.
   - A browser takes a page's policy only on a full page load, so an in-app link to a widened page would still run under the old policy, and Checkout would be blocked. The booking page therefore links to it with a plain link, and goes back with a full page load too.
   - The origins come from running Razorpay's real script with a dummy key under this policy. A real payment may ask for more, and any violation reaches Sentry.

## Consequences

- **"Done when" isn't met yet.** A staging booking reaching TOKEN_SECURED through Razorpay's test mode needs test keys from the founders, so the plan's box stays open. Until then the test site uses the fake gateway. API tests run the whole way through Razorpay's adapter over a stand-in for its API, with its documented requests and answers.
- **Auto-capture is assumed.** It's Razorpay's default. A payment that stays authorized keeps its booking waiting, and Razorpay refunds it by itself after its timeout. Step 6.8's go-live checklist checks the dashboard's setting.
- **A locked read now returns the row as it is.** A session gives back the copy it already read unless told otherwise, so two callbacks at once both saw the payment as new. The concurrency test caught it. Payments and bookings both read with `populate_existing` under a lock.
- **Payments join the data export.** Nothing here has a retention rule yet: how long money records are kept is for the CA (founders' guide, section 8).
