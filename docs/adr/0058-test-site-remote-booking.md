# ADR 0058: A test site can open booking without a visit, through an audited flag command

- Status: accepted
- Date: 2026-11-05
- Build step: none (staging; extends ADR 0047)

## Context

- **Season one is visit-first.** `remote_booking_enabled` is off by default, so a bed is reserved only from a visit an agent has checked in to (ADR 0053).
- **The test site can't reach a booking that way.** It has no staff sign-in or field agents yet, so the booking and payment pages built in Phases 5 and 6 can't be tried on it.
- **Nothing could change a flag** except direct access to the database, which the founders have asked to keep away from.

## Decision

1. **`python -m app.manage flags set NAME VALUE` sets a feature flag.** It checks the value against the flag's declared type, and writes an audit entry. Setting a flag to the value it has already changes nothing and adds no entry.
2. **`TEST_SITE_REMOTE_BOOKING` sets the flag as the test site starts,** in `all_in_one`, which only the free-plan staging host runs. The free plan restarts often, which is why an unchanged value adds no audit entry.
3. **A quote says whether a visit is needed** (`reserveWithoutVisit`), so the PG's page offers **Reserve this bed** from the flag as it is now, rather than from a value cached with the page. Someone not signed in signs in first, and comes back to the PG.
4. **Season one's rule is unchanged.** The flag's default stays off, and production doesn't use `all_in_one` or this variable.

## Consequences

- People can reserve a bed and pay at the test bank on the test site. Every PG there is a fictional sample, and no money moves.
- It's only for the test copy. A real launch keeps the visit-first rule until the founders decide otherwise.
