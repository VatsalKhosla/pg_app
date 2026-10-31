# ADR 0051: Disputes: a student reports a room that isn't as shown inside their 24 hours, with their own private photos; ops settle it as a refund or an upheld booking; and a refund offers PGs like it

- Status: accepted
- Date: 2026-10-31
- Build step: 5.7 (disputes)

## Context

- **BUILD_PLAN 5.7** asks for:
  - a "room not as shown" form, with photos, inside the check window;
  - an ops queue;
  - resolving as a refund (the bed released, with help to book again with similar PGs) or as upheld;
  - an audit of every step.

  It's done when both resolutions update the booking, the allocation and the notifications correctly.
- **Rule 8:** if the room isn't as shown, release or refund it the same day. No money is earned until the 24-hour window passes without a dispute.
- **The state machine (ADR 0045)** already has the rules:
  - `dispute` is the student's, while the window is open.
  - `resolve_refund` and `resolve_uphold` are ops'.
  - The effects are OpenDispute and CloseDispute; a refund also releases the bed, refunds the token and suggests similar PGs.
- **ARCHITECTURE §6** names a `disputes` table. **§13:** dispute photos are private files behind links signed for five minutes.

## Decision

1. **The data:**
   - **`disputes`:** one per booking (unique). It holds the reason (`not_as_shown`, `unsafe`, `other`), the student's description, the status (`open`, `resolved_refund`, `resolved_uphold`) and, once settled, who settled it, when, and ops' notes. A check constraint keeps "open" and "settled" consistent.
   - **`dispute_photos`:** a row per photo with its position, in place of §6's `media_ids` array, as verification photos do. A database can then hold each photo to a real media asset.
   - **Queue index:** a partial index on open disputes serves ops' queue.
2. **The student reports with `POST /v1/bookings/{code}/disputes`.**
   - **The report:** a reason, 10 to 2,000 characters in their own words, and up to six photos.
   - **Photos:** each photo must be the student's own `dispute_photo` and ready, or the answer is 422 `DISPUTE_INVALID`, naming every problem.
   - **Timing:** the state machine decides when: only while checked in, before the window's exact end. Otherwise the answer is 409 `INVALID_TRANSITION`.
   - **What happens:** the booking becomes DISPUTED, so the settling job leaves it alone, and the owner gets a text.
   - **One transaction:** the dispute's row is written in the same transaction as the change.
3. **Students may upload one kind of file.** People signed in by phone may start uploads of `dispute_photo` only, 20 tries an hour (a refused try counts). These photos are private: the student and ops see them, nobody else does.
4. **Ops settle a dispute.**
   - `GET /v1/ops/disputes` is the queue, oldest first, cursor-paged, with a fixed number of queries however long the page.
   - `GET /v1/ops/disputes/{id}` shows:
     - the student's words;
     - their photos, behind links signed for five minutes;
     - the booking;
     - the student's phone, to call them.
   - `POST /v1/ops/disputes/{id}/resolve` takes the outcome and notes. It locks the booking, so a second answer finds the dispute settled.
     - **Refund:** the booking becomes REFUNDED and its bed is released. The token refund is a Phase 6 stub.
     - **Uphold:** the booking becomes ACTIVE and the token is earned (also a Phase 6 stub).

   Each outcome texts the student and the owner. The notes go to the booking's events and the audit log, never to the owner.
5. **Help to book again** is where the state machine's SuggestSimilar points: after a rejection, a confirmation timeout, or a refunded dispute.
   - The student's booking then carries `rebook`: a search for PGs in the same locality, with the same sharing and gender rule, a bed free for the month they need (the later of the move-in and today), and up to a fifth above the booked rent.
   - That ceiling is a search filter. It is never a price.
   - The booking page runs that search through the public search API and shows up to three PGs, with a link to the full search.
6. **The web app:**
   - **The student's booking page:** shows the report form while `canDispute` holds, and the report's status once sent. The form uploads private photos, can remove them, and explains a refusal.
   - **Ops' pages:** the console gains `/ops/disputes` (a status filter) and `/ops/disputes/[id]`. Settling asks once more what the outcome means, because neither outcome can be undone.

## Consequences

- **"Done when."**
  - **A refund:** the booking is REFUNDED and the bed released. The texts are the owner's on the report, then both sides' on the refund. The history ends with `dispute` and `resolve_refund`. The audit holds ops' note, a second answer is refused, and the student sees PGs like it.
  - **Upheld:** the booking is ACTIVE from that moment and the bed stays held. The settling job later changes nothing.
  - **The window's edge:** a report at its exact end is refused, and a second before it is taken.
  - **Photos:** another student's, a still-processing and a wrong-purpose photo are each refused.
  - **Uploads:** students may upload dispute photos only, 20 tries an hour.
  - **The queue:** pages oldest first.
  - **Component tests** cover:
    - the report form: validation, photos in order, removing one, a refused upload, too late, a refused photo;
    - ops' settling: both outcomes confirmed first, going back, settled already, failure, axe.
- **Money** is still Phase 6. Refunding and earning the token stay stubs, and no money moves until payments go through the gateway (rule 10).
- **The 5.10 ops board** will show the open disputes with the other bookings needing attention.
