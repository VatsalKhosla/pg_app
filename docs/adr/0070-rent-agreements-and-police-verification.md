# ADR 0070: Rent agreements signed by both sides in the app, and the tenant's police verification

- Status: accepted. The agreement's text is a DRAFT until a lawyer has reviewed it.
- Date: 2026-11-15
- Build step: the founders' item 11 of 2026-11-12, "Rent agreement sign both side with police verification. this you should work properly on."

## Context

Once an owner confirms a booking, the student and the owner need a written agreement for the stay, and Delhi Police expect landlords to register their tenants. Today both happen on paper, if at all.

The founders chose the approach on 2026-11-12:
- **Signing:** both sides sign in the app, each confirming with a one-time code sent by email, with a record of who signed, when, from where, and the SHA-256 of the exact text they signed.
- **Text:** marked DRAFT until a lawyer reviews it. Nobody writes final legal text in the code (CLAUDE.md).
- **Police verification:** the student fills in the details the Delhi Police tenant-verification form asks for; the site turns them into a pre-filled summary; the owner submits it on the Delhi Police portal and uploads the acknowledgement; both see where it stands.
- **Never store Aadhaar numbers.** At most the last four digits.

The rest is set by the rules already in force: modules talk through services and outbox events (ARCHITECTURE §5); the exact address shows only once a booking is confirmed (rule 11); money is the booking's own, copied from its quote and never worked out again (rules 5 and 12); every route has a policy and an entry in the authorization matrix; personal data is collected to the minimum, KYC data encrypted, and kept no longer than needed (DPDP, ADR 0018).

## Decision

### 1. A module of its own, following bookings through the outbox

- The `agreements` module owns four tables: `rental_agreements`, `agreement_signatures`, `agreement_signing_codes` and `tenant_verifications` (migration `ea4c308884f8`).
- The booking module announces two events through the outbox, each once per booking: `booking.confirmed` and `booking.ended` (any final status). Bookings never call agreements; an import-linter contract enforces it.
- One idempotent handler serves both: it brings the agreement in step with the booking as it is now. The order the jobs run in, a retry, or a second run changes nothing.
- Every request does the same first. So the agreement shows as soon as the owner confirms, even before the job has run, and bookings confirmed before this module existed get theirs on first use.
- What the agreement states comes through other modules' services, never their tables: `BookingLookup` (new, in the booking module), the catalog's owner and PG (`invoice_party`, `bed_ref`), the student's name from identity, and the quote's itemised charges from pricing (`QuoteLookup.charges`, new).

### 2. The text

- **A versioned template.** Each version is a Markdown file in `agreements/data/templates/` (`draft-1` now), in the subset the web app renders. `CURRENT_VERSION` names the one in force, changed in the same review as a new file. A unit test pins each file's SHA-256, so a text someone may have signed can't be edited: a change is a new version.
- **A draft can't reach production.** Production refuses to start while the current version is a draft, as it does for the owner agreement and the privacy notice. The text itself says DRAFT on its third line, and the pages say so too.
- **Filled from the booking.** The parties (the owner's legal and business names, the student's name), the PG and its exact address, the bed, room and room type, the move-in, the stay and its end, the monthly rent, deposit, token, the amount due at move-in, and every mandatory charge as the quote showed it. Amounts are formatted, never computed. Anything a person typed (a name, an address) is made plain text, so it can't become a heading, bold or a link.
- **Current until somebody signs, fixed after.** Until the first signature, the text follows the facts and the template in force: a student who adds their name, or ops correcting an address, changes it. From the first signature it is fixed, so both sides sign the same words.
- **Nobody signs a text without the student's name.** The agreement names the student from their account. While the account has no name, the text says so and signing is refused (`409 AGREEMENT_NOT_READY`).

### 3. Signing

- **The code:**
  - six digits, kept as an HMAC under `SECRET_KEY` bound to its row;
  - lasts ten minutes; five wrong tries lock it; a new one at most every 30 seconds;
  - at most five an hour per person (Redis, refusing while Redis is down, as each costs an email);
  - signing attempts limited to 20 per person per 15 minutes.
- **Delivery** is by email to the account's address, through the module's own port (`SigningCodeSender.send(to, code)`) and the site's mailer (`app.core.mail.Mailer`, ADR 0068), straight away and never through the outbox (which would store the code). It goes the way sign-in codes do:
  - locally, the console mailer logs it and the API hands the code back to the page;
  - a test site without email shows it on screen, as it does sign-in codes;
  - anywhere else the mailer sends it, and without one asking answers 503.

  An account without an email address can't be sent one (`409 SIGNING_NEEDS_EMAIL`).
- **Signing** takes the code, the signer's full name as typed, and the SHA-256 of the text they read. If the text has changed since, it's refused (`409 AGREEMENT_TEXT_CHANGED`) and the code stays usable.
- **The evidence.** Each signature is a row with:
  - the side and the account;
  - the typed name;
  - the time from the injectable clock;
  - the request's IP address and user agent;
  - the text's SHA-256 and the template version.
- **The database keeps the record honest:**
  - an agreement's `text_sha256` must be the SHA-256 of its `text` (a check);
  - a signature refers to the agreement *and* its hash through one foreign key, so a text somebody has signed can never change;
  - each side signs once (a unique constraint);
  - signatures can't be updated, deleted or truncated (a trigger, as on the audit log).
- **The audit log** records each agreement made, signed and voided.

### 4. States

A pure state machine in `agreements/domain/agreements.py`, unit-tested over every pair and with Hypothesis over any order of events:

- `awaiting_signatures` → `signed_by_student` or `signed_by_owner` → `signed`.
- `void` when the booking ends early (cancelled, rejected, a no-show, or refunded) before both have signed. Signatures already made stay on the record.
- A signed agreement stays signed if the booking ends later. What that means for the tenancy is for the agreement's own terms (the lawyer's section 7).

### 5. Police verification

- **Its states:** `not_started` → `details_submitted` → `submitted_to_police` → `verified`.
  - The student gives their details and may correct them until the owner has submitted them.
  - The owner marks them submitted with the portal's acknowledgement, then verified.
  - Nothing moves once the booking has ended.
- **The details:**
  - full name;
  - father's, mother's or guardian's name;
  - date of birth and gender;
  - mobile number;
  - permanent address (with district, state, PIN code, and the police station if known);
  - student, working or other, with the college or workplace;
  - an identity document's type and **the last four characters of its number only**;
  - up to two people who know them.

  The list follows what tenant-verification forms commonly ask. It needs checking against the current Delhi Police form (below).
- **No Aadhaar numbers, ever.** Identity documents are a type and a last four. Any text holding twelve digits (spaced or not, in any script's digits) is refused, whichever field it was typed into, by the API and by the browser's form. The owner copies the full number from the original document onto the portal.
- **Sealed at rest.** Nothing in the code encrypted KYC fields before this. `app/core/sealing.py` now seals values with AES-256-GCM:
  - each value is bound to its row, so it opens nowhere else;
  - keys come from `FIELD_ENCRYPTION_KEYS` (`id:key` pairs; the first seals, all open), so they can be rotated;
  - outside production a key is derived from `SECRET_KEY`; production refuses to start without keys of its own.

  The details are sealed as one JSON value. Only the student, the PG's owner and ops ever see them opened. Every look by the owner or ops is audited.
- **The acknowledgement** is the owner's own upload through the private-document flow (media purpose `document`: presigned, type and size allowlists, private bucket, links signed for five minutes). It is refused if it isn't theirs, isn't a document, or was rejected (`422 ACKNOWLEDGEMENT_INVALID`).
- **Retention** (in the daily schedule):
  - signing codes, with the IP address and user agent that asked, go after 7 days, as sign-in codes do;
  - the details are erased 30 days after the police verified the tenant or the booking ended. The record that it happened, the dates and the acknowledgement stay.
- **The data export** holds the student's agreements, the signatures they made on either side, and their verification details, opened for them.

### 6. Routes

Each route is in the authorization matrix. Another person's booking, and a booking never confirmed, answer 404.

| Who | Routes |
|---|---|
| The student who booked | `GET /v1/bookings/{code}/agreement`, `POST …/agreement/signing-codes`, `POST …/agreement/signatures`, `GET` and `PUT /v1/bookings/{code}/police-verification` |
| The PG's owner | `GET /v1/owner/bookings/{code}/agreement`, `POST …/agreement/signing-codes`, `POST …/agreement/signatures`, `GET /v1/owner/bookings/{code}/police-verification`, `POST …/police-verification/mark-submitted`, `POST …/police-verification/mark-verified` |
| Ops and admins, read-only | `GET /v1/ops/bookings/{code}/agreement` (with every signature's evidence), `GET /v1/ops/bookings/{code}/police-verification` |

New error codes: `AGREEMENT_TEXT_CHANGED`, `AGREEMENT_NOT_READY` and `SIGNING_NEEDS_EMAIL` (409); `SIGNING_CODE_INVALID`, `SIGNING_CODE_EXPIRED` and `SIGNING_CODE_LOCKED` (400); `SIGNING_CODE_TOO_SOON` (429, with `Retry-After`); `POLICE_DETAILS_INVALID` and `ACKNOWLEDGEMENT_INVALID` (422).

### 7. The web app

- The student's and the owner's booking pages gain two cards, drawn like the story pages' feature cards (`rounded-[1.75rem]`, an icon, the status):
  - **The agreement:** its status, who signed and when, the full text with the DRAFT notice, and the signing flow: ask for a code, then the code and the full name.
  - **Police verification:** the student's form (React Hook Form and Zod, with the API's errors shown by their fields); for the owner, the details, the acknowledgement upload and the "verified" button.
- Print pages show the document alone (a print stylesheet hides the rest):
  - `/bookings/[code]/agreement` and `/owner/bookings/[code]/agreement`;
  - the owner's pre-filled police summary at `/owner/bookings/[code]/police-verification`.
- The ops booking page shows both, read-only, with each signature's evidence.

## Legal caveats and questions for the founders and a lawyer

Nothing below is settled. Each item needs checking before real tenants sign.

1. **The text is a DRAFT.** It was written from the founders' rules and the booking's facts for discussion, and it isn't legal advice. The open questions are in square brackets in the text. A reviewed version becomes a new template file and the current version, and production can't run until then.
2. **The form of the agreement.** Is a leave and licence the right form for a bed in a PG in Delhi NCR? Does any rent-control or tenancy law apply? Should the platform stay outside the agreement, as the draft says?
3. **Electronic signature.** Is a signature made in the app enough for this agreement under the Information Technology Act, 2000? It is a one-time code to the signer's email, their typed name, the server's time, the IP address and device, and the text's hash. Or does it need Aadhaar-based e-Sign through a licensed e-Sign service provider? **e-Sign is a possible later upgrade:** another signing method behind the same signature record. It would need a paid vendor, which is the founders' choice.
4. **Stamp duty and registration.** We don't know yet, and the founders and a lawyer must decide:
   - whether this agreement attracts stamp duty in Delhi, and in Haryana and Uttar Pradesh for Gurugram and Noida;
   - how much, and who pays it;
   - whether e-stamping is needed, and how an e-stamp attaches to an agreement signed in the app;
   - whether it must be registered, and whether the length of the stay changes that. It is often said that terms longer than 11 months need registration: check that, and what it means for stays booked for 11 months or more.

   Until this is settled the draft says it isn't a stamped or registered agreement.
5. **Police verification.**
   - Confirm what Delhi Police require of PG owners and their residents now.
   - Check the field list against the current form on the Delhi Police portal.
   - Gurugram (Haryana Police) and Noida (Uttar Pradesh Police) have their own processes. The flow names Delhi Police and needs adapting before PGs outside Delhi use it.
6. **Identity documents.** The list on offer: Aadhaar (last four digits only), passport, voter ID, driving licence and PAN.
   - Which should we accept?
   - Should we keep even the last four characters?
   - Should a photo of the document ever be collected? It isn't now, by choice.
7. **Retention.** The founders confirm the 30 days for verification details and the 7 days for signing codes. Signatures and agreements are kept as evidence, with no deletion yet. How long after a stay ends to keep them is their decision, with the lawyer, as for owner agreements (ADR 0025).
8. **Who signs for an owner's business.** Today the owner's account signs, and the typed name records who. Should a company's signatory show their authority?

## Consequences

- **Production gates:** a reviewed rent agreement template and `FIELD_ENCRYPTION_KEYS`.
- **Signing needs email.** Production sends codes once `MAIL_SENDER=smtp` is set up (ADR 0068's steps). Accounts without an email address, such as phone accounts from before ADR 0068, can't sign until one is added: ops can add an owner's, but students can't add one themselves yet.
- **Keys:** rotating `FIELD_ENCRYPTION_KEYS` means listing the new key first and keeping the old one until every value has been sealed again (a re-sealing job isn't built yet). Losing a key loses what it sealed.
- **Not built yet:**
  - telling either side by email or text that an agreement is ready or signed;
  - a PDF made by the server (people print or save one from the browser);
  - Aadhaar e-Sign and e-stamping;
  - the PG's house rules written into the agreement (it refers to the listing);
  - re-sealing after a key rotation.
