# ADR 0025: The owner agreement: versioned texts in the repository, click-wrap acceptance of the exact text, append-only evidence, accepted again for every new version

- Status: accepted
- Date: 2026-10-27
- Build step: 2.6 (owner records and agreements)

## Context

The owner agreement is the platform's main defence against leakage (PRODUCT_CONTEXT §6). The fee is due for any student we introduced who moves in within 90 days, however they pay, and the acceptance is recorded with the version, the time and the IP. If an owner disputes the fee, this record is the proof, so it has to show exactly which text the owner accepted, when and from where.

BUILD_PLAN 2.6 asks for:
- owner profiles: the business name and an optional GSTIN;
- a versioned agreement text with click-wrap acceptance, recording the version, the document's hash, the time, the IP and the user agent.

It's done when an acceptance is recorded and visible in ops, and a new agreement version asks owners to accept again.

The final agreement is legal text, which the founders write with a lawyer (CLAUDE.md). Only a draft marked DRAFT can be written now.

## Decision

1. **The texts are versioned files in the repository**, one Markdown file per version in `catalog/data/agreements/`. The brand name is filled in from `BRAND_NAME`.
   - `OWNER_AGREEMENT_VERSION` names the current version.
   - A version's file is never edited once an owner may have accepted it: a change is a new file and a new version.
   - The API refuses to start if the current version has no file.
   - Production refuses a version whose name starts with `draft`. A reviewed agreement is therefore a launch gate, as the privacy notice is (ADR 0018).
   - **Why files rather than a table:** a change is reviewed in a pull request with the code that depends on it, every environment has the same text, and no admin screen is needed yet.
2. **An acceptance names exactly what the owner was shown.**
   - The browser sends the version and the SHA-256 of the text it displayed.
   - Anything other than the current version and text is refused with `409 AGREEMENT_CHANGED`, and the page reloads with the new text.
3. **The evidence.**
   - Each acceptance is a row in `owner_agreements`: the owner, the version, the text's SHA-256, the time from the server's clock, and the request's IP and user agent.
   - The browser calls the API directly, so the IP and user agent are the owner's own, not the web server's.
   - The database refuses to update, delete or truncate these rows, using a trigger as the audit log does. The audit log records each acceptance as well.
   - Accepting a version that was already accepted returns the existing record, so a second tab or a repeated click adds nothing. The owner's row is locked while this is checked.
   - An owner's data export includes their business record and every acceptance (DPDP, ADR 0018).
4. **A new version asks every owner again.**
   - The owner record keeps the version accepted last, and the API's `agreementCurrent` says whether that is the current one.
   - The owner area sends an owner to the agreement until they accept the current version.
5. **Owner records.**
   - Ops change an owner's legal name, business name and GSTIN with `PATCH /v1/ops/owners/{id}`. Only the fields sent change, and the audit entry names the fields changed.
   - A GSTIN's last character must check the 14 before it, using GSTN's published scheme (Luhn's check in base 36). A single mistyped character is always caught.
6. **Consent at an owner's first sign-in.**
   - Ops make an owner's account before the owner has ever signed in, so it existed before its person agreed to the privacy notice.
   - ADR 0018 asked for consent only when a sign-in created the account, so these owners were never asked.
   - Now a sign-in asks for consent (`CONSENT_REQUIRED`) whenever the account's person has never agreed to its required purposes, whoever made it. Staff added by an operator are asked the same way.
7. **Who sees what.**
   - **Ops and admins** see every owner and every acceptance: `GET /v1/ops/owners/{id}`, and `GET /v1/ops/owners/{id}/agreements`, newest first.
   - **An owner, signed in by phone,** sees only their own record and the agreement:
     - `GET /v1/owner/profile`;
     - `GET /v1/owner/agreement`: the text, its hash, and whether and when they accepted it;
     - `POST /v1/owner/agreement/acceptances`.
   - Someone signed in who isn't an owner gets 403. An owner whose business ops haven't added yet gets 404.
   - The authorization matrix covers the 6 new routes. Its owner caller now has a business record.
8. **The web app.**
   - **`/owner`** (protected and noindex) shows the owner's business as we keep it.
   - **`/owner/agreement`** shows the text, a notice while it's a draft, and the click-wrap form. The form's box starts unticked.
     - The text is turned into React elements, never HTML, from a small subset of Markdown: headings, paragraphs, lists and bold.
     - A unit test checks that every version on file uses only that subset.
   - **The ops console gains Owners:**
     - a list, with search, showing whether each owner accepted the current agreement;
     - a form to add an owner;
     - each owner's page, with their details form and every acceptance;
     - a link to the owner's page from each listing.

## Consequences

- The text in the repository is `draft-1`, written from PRODUCT_CONTEXT's rules for discussion. Production can't run until the founders and a lawyer publish a reviewed version as a new file and set `OWNER_AGREEMENT_VERSION` to it.
- Any change to a published text needs a new version, and every owner must accept again. That is deliberate: the evidence names the exact text.
- **Retention:** an acceptance's IP address and user agent are personal data, kept as long as the agreement may need proving. The table refuses deletes, so a retention rule or an erasure that removes acceptances would need a reviewed migration first.
- **Not built yet:**
  - Owners can't change their own details; ops do it for them.
  - The owner dashboard is Phase 7.
- **Founders' decisions:**
  - the agreement's final text, and the company's registered name that the draft leaves as a placeholder;
  - how long acceptances are kept after an owner leaves the platform.
