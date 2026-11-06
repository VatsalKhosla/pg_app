# ADR 0065: The launch security review: a STRIDE threat model, ASVS 5.0 level 2, ZAP's baseline on the test site and Schemathesis on a private copy of the API

- Status: accepted
- Date: 2026-11-06
- Build step: 8.1 (security review)

## Context

- **BUILD_PLAN 8.1** asks for:
  - a STRIDE threat model for sign-in, booking and payments;
  - the ASVS level 2 checklist;
  - ZAP's baseline and Schemathesis "on staging";
  - a complete authorization matrix;
  - clean dependency and image scans;
  - rotated secrets.
- **ARCHITECTURE §17** targets ASVS level 2 for sign-in, booking, payments and personal data, and asks for the threat model again in every phase that touches sign-in or money.
- **ASVS 5.0.0** (May 2025) reorganised the standard: 253 requirements at levels 1 and 2, in 17 chapters.
- **The test site** is the only deployed copy. It runs on free plans, its data is fictional, and the founders use it every day. Its per-address limits (60 an hour for sign-in) protect it from floods, including our own.

## Decision

1. **The threat model and the checklist live in `docs/security/`**: `threat-model.md` and `asvs-l2.md`.
   - Both cite the code and tests behind each claim, and are revised in the same change as the code they describe.
   - The checklist accounts for every one of the 253 requirements, in our own words with their IDs; the standard has the exact text.
   - It also holds what ASVS asks to have written down: limits, the cryptography in use, data classes, a logging inventory and remediation times.
2. **ZAP's baseline runs against the test site**: `make zap-baseline`. It's passive: it spiders for a minute and reads the responses, sending no attacks.
   - It fails on any finding that `.zap/rules.tsv` doesn't accept with a reason.
   - The image is pinned by digest like the other scanners. It's an on-demand scanner rather than part of what's shipped, so it takes ZAP's current stable build instead of waiting the usual 7 days.
3. **Schemathesis runs against a private copy of the API, not the test site.** That copy has its own database and cache index on a developer's machine or a CI runner.
   - Fuzzing the test site would fill the founders' copy with junk accounts and visits, and trip its per-address limits for everyone behind the same address.
   - It's the same code and schema, so it finds the same faults.
   - For this review it ran twice: once signed out, and once signed in, with a session and its CSRF token. That copy had a fresh database, the API on its own port and the console sign-in codes.
   - The signed-in pass found nothing; the signed-out pass found the year-0 month.
   - A `make fuzz-api` that repeats both passes is still to come.
4. **What the review fixed:**
   - a move-in month in year 0, which crashed search and the map (found by Schemathesis);
   - user sessions with no end while in use, which now end 90 days after sign-in (ASVS 7.3.2);
   - `staff add`, which now writes an audit entry only when something changes.
5. **What stays open**, listed as gaps in the checklist with their fixes:
   - envelope encryption of owners' documents;
   - verifying the database's certificate;
   - a WAF;
   - scanning owners' PDFs;
   - Workspace 2-Step Verification (the founders');
   - versioning `SECRET_KEY`;
   - trusting only the load balancer for `X-Forwarded-For`.

## Consequences

- The open gaps keep 8.1 from being ticked until they're done or the founders accept them, in step 8.5 for those that come with production.
- Secrets pasted into chat (the Neon storage keys and an AI Gateway token) must be rotated by the founders; the plan's "secrets rotated" waits on that.
- A new route or feature updates the authorization matrix (enforced by its own test), and the checklist and threat model where they cite it.
- An external penetration test is still due before growing past the first micro-market (ARCHITECTURE §17).
