# ADR 0024: Field verification: a visit booked by ops, reported from the building, before a PG goes live

- Status: accepted
- Date: 2026-10-26
- Build step: 2.5 (field verification workflow)

## Context

The product's promise is verified listings: a field agent visits every building, checks its safety and takes the photos (PRODUCT_CONTEXT §1). The reasons are real:
- a PG building in Satya Niketan collapsed in September 2026;
- the MCD surveyed 1,252 PG buildings afterwards;
- Noida's housing societies often ban PGs.

PRODUCT_CONTEXT §7 asks for physical verification before publishing, a safety checklist, and "never list a flagged building". BUILD_PLAN 2.5 asks for:
- a mobile checklist;
- the agent's GPS position and the time, captured with it;
- a result that sets `verification_status`;
- no publishing while `verified_only` is the default.

## Decision

1. **A visit is the unit of verification** (`verification_visits`, which replaces ARCHITECTURE §6's `verification_reports`). Ops book one for one field agent at a time, and it holds the agent's report once submitted. A property has at most one booked visit (a partial unique index).
2. **The property's verification status follows the visits.**
   - Booking a visit makes an unverified, failed or suspended property `scheduled`.
   - Cancelling puts back the status it had before.
   - A passed report makes it `verified`, and a failed one `rejected`.
   - Ops can suspend a verified property's verification (a complaint, an authorities' notice).
   - A failed or suspended property that is live is paused at once, with an audit entry naming the reason.
   - The API says what each listing allows now (`canBookVisit`, `canSuspend`), as it does with `nextStatuses`, so the web app keeps no copy of these rules.
3. **The report:**
   - **The checklist** covers:
     - the building's age, its condition and any cracks;
     - its exits, fire extinguishers, CCTV and a warden at night;
     - safety features for women;
     - the licence number shown on site, and the housing society's permission;
     - any notice from the authorities.
   - **Every question must be answered.** Yes-or-no questions start unanswered.
   - **Position and time:** the agent's position comes from their phone, with its accuracy. The time comes from the server's clock. The distance from the building's pin is kept with the report, and the agent may make their position the pin; a moved pin gets a new public point.
   - **Photos:** at least one, as evidence. They use a new private media purpose, `verification_photo`: metadata stripped like every photo, shown only through signed links (ADR 0022).
4. **Only two rules decide a report**, both from the founders' documents:
   - a building with a sealing, demolition or unsafe-building notice from the authorities can't pass ("never list a flagged building");
   - a failed visit must say why.

   Every other answer, cracks or missing extinguishers for instance, is evidence for the agent's judgement. Making more of them decisive is a business rule, and therefore the founders' call.
5. **Publishing** needs a passed verification while the `verified_only` flag is on, which is the default (seeded by a data migration). A failed or suspended verification blocks publishing even with the flag off.
6. **Who does what:**
   - Ops and admins book, cancel and read every visit, and suspend verifications.
   - A field agent sees only the visits booked for them and reports only on those. Anyone else's visit answers 404.
   - The authorization matrix covers all 8 routes.
7. **The web app:**
   - The ops listing page gains a Verification section: the status, booking with an agent and a time (the browser's own time zone, sent with its offset), cancelling, suspending, and every visit with its report.
   - Field agents get `/field/visits` and the visit's page: the address, directions and the owner's number, then the report form while the visit is theirs and booked.
   - The CSP's `img-src` takes the private storage's origin, for the signed photo links.
8. **Local development without an authenticator app:** `make dev-staff` and `make staff-code` make and sign in a staff member with no app. Both refuse when deployed.

## Consequences

- A PG can't go live without a field agent's visit, which is the product's promise. Field agents and their phones are needed before launch.
- **Re-verification** (a verified property visited again, on a schedule or after a complaint) isn't built. A suspended property gets a new visit; a verified one can't be booked again yet.
- **Founders' decisions:**
  - whether more checklist answers should fail a visit on their own, such as structural cracks or no fire extinguishers;
  - how often verified PGs are visited again.
- **Search** (step 3.x) shows only verified PGs while `verified_only` is on.
