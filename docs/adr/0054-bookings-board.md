# ADR 0054: The bookings board: what needs a person now and since when, a page per booking with whom to call and everything that happened, and every action the state machine would take from ops, each with a reason

- Status: accepted
- Date: 2026-11-04
- Build step: 5.10 (ops bookings board)

## Context

- **BUILD_PLAN 5.10:** a board by state with filters, SLA timers (unconfirmed over 2 hours, disputes), actions with reasons, and the full event history. It's done when ops can run a day of bookings from it without database access.
- **Rule 8:** if the room isn't as shown, release or refund the same day.
- **The state machine (ADR 0045)** already lets ops cancel for an owner and record a move-out, but no route did. Those two effects, flagging the owner and cutting the bed's stay short, had never been carried out.

## Decision

1. **The timers are a pure rule** (`booking/domain/board.py`), at India's day:
   - **Unconfirmed:** two hours from the token. Ops then call the owner; the booking still rejects itself at its own deadline.
   - **A dispute:** due by the end of the day it was reported (rule 8).
   - **A move-in:** due on its day, and late from the next, until the terms' wait ends it as a no-show.

   "Needs a person" means an owner past their two hours, any open dispute, or any move-in due. A token just in is the owner's to answer first, so it has a timer but doesn't need a person yet.
2. **Two new stamps run the timers by the app's clock:** `bookings.token_secured_at` and `disputes.opened_at`. A separate data migration fills them in for rows that exist already. `created_at` comes from the database's clock, so it can't drive a rule tested with time travel.
3. **The board** (`GET /v1/ops/bookings`, `GET /v1/ops/bookings/summary`):
   - **Filters:** by status, by the way it was made, or by what needs a person.
   - **Search:** a booking's code, a student's phone, or part of a PG's name.
   - **Order:** bookings still moving come oldest first, as a queue; the others newest first.
   - **Summary:** a count for every status, and for each kind of waiting.
   - **Queries:** the list reads in the same few queries however long the page (tested).
4. **A booking's page** (`GET /v1/ops/bookings/{code}`) has:
   - whom to call, with both phones;
   - how many bookings this owner has cancelled after taking them;
   - the money as stored, the placement fee and GST included;
   - the dispute and the visit it came from;
   - what it's waiting for;
   - the whole history, with who did each change and why.

   The owner's view gets none of these additions. `actions` is exactly what the state machine would take from ops now, so the page never offers what the API would refuse.
5. **Actions, each with a reason kept in the booking's history and the audit log:**
   - **Confirm for the owner** now requires a reason (a reviewed API change; the web app had no such button yet).
   - **Reject for the owner.**
   - **Cancel for the owner** (`owner-cancel`, new): the bed is freed, the token refunded in full (a stub until Phase 6), and the student texted and shown PGs like it. The flag on the owner is the row itself, cancelled by whom and how, and the board counts them. There's no new column for it.
   - **Record a move-out** (`move-out`, new): the booking ends and the bed is free from that day. A stay that ran past its planned end keeps its planned days, so another booking's days are never touched.
   - **Ask a student to say they've moved in** (ADR 0050) needs no reason: it's a text and changes nothing.

   Settling a dispute stays on its own page (ADR 0051), which the booking links to.
6. **The web app** (`/ops/bookings`, `/ops/bookings/[code]`): the console's new Bookings section opens on what needs a person. Each change that can't be undone asks why, then says what it will do before it's sent. Both pages re-render each minute while they're in view, so the timers stay current. [The runbook](../runbooks/bookings-board.md) says how to run a day from them.

## Consequences

- **"Done when."** API tests cover:
  - each timer at its edge in India;
  - what needs a person, and the summary's counts, moving as a booking does;
  - finding a booking each way, and paging in both orders;
  - the query count;
  - both new actions, with the bed, the texts, the stamps, the history and the audit;
  - a stay past its planned end.

  Unit tests cover the rule, and join `make coverage-money`. Component tests cover every action's flow, with axe. The phone browser test goes on from a booking made on the spot to the board and the booking's history.
- **The effects are now exhaustive.** Carrying out a booking's effects ends in `assert_never`, so a new effect the code doesn't handle fails the type-check.
- **Owners** get their own inbox in step 7.3, from the same desk. The fee and the two phones stay ops' own until then.
