# ADR 0033: Visits: up to three times from the student, a time and an agent from ops, texts and reminders through the outbox, a check-in that is the visit log, and the address once booked

- Status: accepted
- Date: 2026-10-29
- Build step: 3.7 (visits)

## Context

- **BUILD_PLAN 3.7** asks for:
  - a visit request with up to three slots, and ops scheduling it with a field agent;
  - SMS confirmations and reminders at T−24 h and T−2 h;
  - the agent's check-in with GPS and time (the visit log), and the outcome;
  - limits and rate limits, and the exact address revealed once a visit is scheduled.
- It's done when a student books a visit on a phone, the agent checks in, and ops see the visit log.
- **ARCHITECTURE §11** allows at most 5 open visit requests per student. The visit log proves we introduced the student, which is the defence against leakage (PRODUCT_CONTEXT §6).
- **Rule 11.** The owner's phone and the exact address stay hidden until a visit is scheduled or a booking confirmed (CLAUDE.md rule 11, ADR 0026).
- **SMS.** Texts in India go through a DLT-registered template and a provider. The provider is a paid vendor, which the founders choose.

## Decision

1. **A `visits` module** with its own table and rules.
   - A visit is `requested`, then `scheduled`, then `completed` or `no_show`; it can be `cancelled` while open. The pure state machine is in `visits/domain/visits.py`.
   - Scheduling again changes the time or the agent.
   - The database checks the shape of each state: a booked visit has a time and an agent, a finished one has an outcome after a check-in, and the check-in's four fields come together.
   - A partial unique index allows one open visit per student and PG.
2. **The student asks** (`POST /v1/visits`), signed in by phone. Staff sessions can't.
   - They offer 1 to 3 times, each on the hour or half past, from 9 am to 7 pm in India, from three hours to two weeks ahead.
   - Only for a PG the public may see.
   - Five visits open at once at most (`VISIT_LIMIT_REACHED`). A student's requests take a lock in turn, so two at once can't both pass the limit.
   - One open visit per PG (`VISIT_EXISTS`), and 10 requests a day per person.
   - They see their own visits and cancel them (`/v1/visits`, `/v1/visits/{id}/cancel`); anyone else's is a 404.
3. **Ops book it** (`/v1/ops/visits…`): one of the offered times or another (from an hour ago to 30 days ahead), with an active field agent. Booking queues texts through the outbox:
   - the confirmation now;
   - reminders 24 hours and 2 hours before, as jobs due then.

   Each text is keyed by the visit, the template and the time, so it goes once per time. When its job runs, it checks the visit still stands as it did; a cancelled or rebooked visit's old texts don't go. Ops cancelling a booked visit texts the student.
4. **Texts** go through a `Texts` port: a DLT-ready template with blanks (`visits/texts.py`), sent by the worker.
   - `TEXT_SENDER=console` writes them to the log, with the phone masked, for local work.
   - `unavailable` sends nothing and logs that it didn't, until the founders choose a provider. Deployed environments refuse `console`.
5. **The agent checks in** (`/v1/field/visits/{id}/check-in`) from two hours before the visit. Their phone's position and its accuracy are recorded, with the server's time and the distance from the building's exact point. This is the visit log.
   - An outcome needs that check-in first (`CHECK_IN_REQUIRED`): interested, not interested, or the student didn't come (`no_show`).
   - Another agent's visit is a 404.
6. **The address once booked.** The visits module answers the catalog's `ContactAccess`: a student with a visit booked there (or one that happened) may see the owner's phone and the exact address.
   - Their visits page shows them through the existing, audited contact endpoint (ADR 0026).
   - Everything the module changes is in the audit log.
7. **Web.**
   - Students: `/pg/[slug]/visit` (three choices, nothing preselected, the API's reasons shown) and `/visits`.
   - Ops: `/ops/visits` with each visit's log.
   - Field agents: `/field/student-visits`, with check-in from the phone's GPS and the outcome.

## Consequences

- **Founders' decisions:**
  - the SMS provider. Until it's chosen, deployed texts are off and ops call students.
  - The visiting hours, notice and horizon (9 am to 7 pm, 3 hours, 2 weeks) are constants in `visits/domain/visits.py`, worth confirming.
- "Reserve now" after a visit (channel `on_spot`) is Phase 5's booking flow.
- A check-in far from the building is recorded rather than refused, as phones' fixes vary. Ops see the distance in the log.
