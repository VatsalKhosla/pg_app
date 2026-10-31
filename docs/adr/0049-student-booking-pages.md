# ADR 0049: The student's booking pages: what happens next, what they pay and to whom, the address once confirmed, the history, and cancelling with the refund shown first

- Status: accepted
- Date: 2026-10-31
- Build step: 5.5 (student booking pages)

## Context

- **BUILD_PLAN 5.5:** a student's booking pages should show:
  - a timeline from `booking_events`;
  - what to pay at move-in and to whom, the deposit and the charges;
  - the exact address after confirmation;
  - cancelling, with the exact policy text and the refund amount shown before confirming;
  - a support contact.

  It's done when the UI shows the right actions for every state (component tests per state).
- **Rule 9:** free cancellation until 7 days before the move-in, then `late_cancel_policy`. Until payments go through Razorpay Route, refund in full is the only late rule a policy may take (PRODUCT_CONTEXT §9; `booking_problems`).
- **Rule 11:** the owner's phone and the exact address stay hidden until a visit is scheduled or a booking confirmed. The catalog asks a `ContactAccess` port, which visits answered alone (ADR 0026).
- **The browser never works out money** (CLAUDE.md): the refund must come from the API.

## Decision

1. **What cancelling would give back is a pure rule** (`booking/domain/cancellation.py`), and the state machine decides which kind applies. It tries `cancel`, then `cancel_late`, so it never disagrees with the machine's guards.
   - A hold gives nothing back, since nothing was paid.
   - From the token on and until the cutoff, the whole token comes back.
   - After the cutoff, the late-cancel rule decides: refund in full now; nothing if a later policy forfeits the token to the owner. A split refuses until the founders decide its shares.
2. **The student's booking** (`GET /v1/bookings/{code}`, and the hold's answer) now also carries:
   - its history from `booking_events`;
   - the owner's deadline once the token is in;
   - `cancellation`: what cancelling now gives back, and whether it's late; null once it can't be cancelled.

   `GET /v1/bookings` lists the student's bookings, newest first.
3. **Cancelling** (`POST /v1/bookings/{code}/cancel`) sends the refund the student was shown. If cancelling now means something else (the token came in, or the day turned past the cutoff), nothing changes and the answer is **409 `REFUND_CHANGED`**. The page then shows the new amount. The owner gets a text that the bed is free again.
4. **A confirmed booking shows the owner's contact.** The catalog's `ContactAccess` now asks both visits and bookings (`AnyOf`): a booking that's confirmed, moved in or finished there is enough. The booking page reads the address and phone through the PG's contact endpoint, which audits each look, as the visits page does.
5. **The web app** (`/bookings`, `/bookings/[code]`, linked from the account page) shows:
   - **next:** what happens next for each status, with the hold's real end time and the owner's deadline;
   - **the money:** the rent fixed for the stay, the token (it counts toward the first month), and what's paid to the owner directly at move-in (the rest of the first month, the deposit and the charges);
   - **where to go,** once confirmed;
   - **the history;**
   - **help:** a contact link with the booking's code. The company's support facts are still the founders' to give.

   The actions come from one rule (`actionsFor`), and the API decides whether cancelling is offered. Cancelling opens a confirmation with what it gives back, worded from the API's amount, and a link to the cancellation policy. Nothing is pre-ticked and nothing counts down but the real hold.

## Consequences

- **"Done when."**
  - Component tests render the actions for all 12 statuses, each passing axe (WCAG 2.2 AA). Only held, token-secured and confirmed bookings offer cancelling, and only bookings that ended early offer to find another PG.
  - Other tests cover:
    - the confirmation showing the refund before anything is sent, then sending the amount shown;
    - changing one's mind;
    - a refund that changed (the page looks again);
    - a failure.
  - API tests cover the history, the contact appearing only once confirmed, cancelling for free and late (at India's day), a changed refund, another student's booking, and the owner's text. The cancellation rule's unit tests join `make coverage-money`.
- **Paying the token** is Phase 6: until then a hold's page says paying online opens soon.
- **Checking in and disputes** add their actions to the same rule in 5.6 and 5.7.
