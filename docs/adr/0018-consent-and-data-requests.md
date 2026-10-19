# ADR 0018: Consent, data requests and the retention schedule (DPDP)

- Status: accepted
- Date: 2026-10-19
- Build step: 1.5 (consent and data requests)

## Context

The DPDP Act 2023 and its Rules apply in full from 13 May 2027 (PRODUCT_CONTEXT). For this build, that means:
- consent that is specific and freely given, against a privacy notice, with records the platform can produce;
- a way for people to get a summary of their data, and to ask for its erasure;
- personal data kept no longer than needed.

ARCHITECTURE §12 places versioned consent in the identity module, and data requests and retention in a compliance module. Three things here are not for engineering to decide:
- the notice's text, which is legal text;
- what an erasure must keep, since invoices, payments and disputes carry legal retention duties;
- retention periods for data that doesn't exist yet.

This ADR records what was built, and where it stops for the founders.

## Decision

1. **Consent per purpose, per notice version** (the `consents` table in the identity module).
   - **Purposes:** `account` (required: running the account and the service) and `marketing` (optional). Nothing is ever assumed or pre-ticked (CLAUDE.md rule 7): a purpose counts only when the request names it.
   - **Records:** every grant is a row with its purpose, notice version and time. Withdrawing sets `withdrawn_at`, so the history (the proof the Act asks for) survives, with one active consent per purpose and version.
   - **The notice:** `PRIVACY_NOTICE_VERSION` names the version of the notice the web app shows; the text is the web app's (step 3.8, marked DRAFT for a lawyer). `GET /v1/privacy-notice` gives the version and which purposes are required. Production refuses a version starting `draft`, so a reviewed notice is a launch gate.
2. **No account without consent.**
   - **The first sign-in:** an account is created only with consent to the current notice that includes `account`. Without it, `POST /v1/auth/otp/verify` answers `400 CONSENT_REQUIRED` and changes nothing: the challenge stays open, so the same code works again once consent is given.
   - **No account enumeration:** that answer comes only after the code has proved right, so it tells nobody without the phone whether an account exists.
   - **Old notices:** consent naming another notice version answers `409 PRIVACY_NOTICE_CHANGED`.
   - **Returning people** sign in without being asked again.
3. **When the notice changes,** `/v1/me` sets `consentRequired` until the person agrees to the new version (`POST /v1/me/consents`). Optional purposes are given the same way and withdrawn with `DELETE /v1/me/consents/{purpose}`. The account's own purpose can't be withdrawn while the account exists (`409 CONSENT_NEEDED_FOR_ACCOUNT`); that takes a deletion request.
4. **Data requests** (the new `compliance` module): `POST /v1/me/data-requests` with `export` or `deletion`, and the list at `GET /v1/me/data-requests`.
   - **One open at a time:** each person has at most one open request of each kind (a partial unique index). Asking again answers the open one, so retries are harmless.
   - **An export** is put together by an outbox job (`compliance.build_export`):
     - **Contents:** one part from every module that holds personal data. `app/jobs.py` lists the parts: identity (the account, roles, consents, sessions, recent sign-in codes, sign-in methods) and compliance (the person's requests). Secrets stay out: no session tokens, code hashes or authenticator salts.
     - **Storage:** the JSON file is kept in `data_exports` (small, so in PostgreSQL rather than object storage).
     - **Download:** the file comes from `GET /v1/me/data-requests/{id}/file` for 7 days. It is for the person who asked only: anyone else, staff included, gets `404`. The response is never cached (`Cache-Control: no-store`).
   - **A deletion** goes to the ops queue (`GET /v1/ops/data-requests`, for ops and admins in a staff session). Staff resolve it with `POST /v1/ops/data-requests/{id}/resolve`, which records `completed` or `rejected` with a note the person sees. Resolving is audited. Exports and resolved requests answer `409 INVALID_TRANSITION`, a code now in core for every state machine.
   - **Nothing is erased automatically yet.** What a completed deletion must erase, and what it must keep, is the founders' decision with legal advice. Until then, staff resolve requests by hand (docs/runbooks/data-requests.md). Before launch there are no real people to erase.
5. **The retention schedule** is one daily job (`compliance.retention`, 03:30 India time) running rules that each module contributes. `app/jobs.py` lists them, so the schedule reads in one place:
   - sessions, 30 days after they end or expire;
   - sign-in codes, after 7 days;
   - export files, 7 days after they're ready.

   Each run records how much each rule removed in the audit log (`retention.ran`). It replaces the two separate cleanup jobs from steps 1.1 and 1.2.

## Consequences

- **The web app** (step 1.6) shows the notice and the purposes at sign-up, unticked, and sends the chosen consent with the code. It handles `CONSENT_REQUIRED` by showing the notice and resending the same code, and it asks again when `consentRequired` is set.
- **A module that starts keeping personal data** adds its export part and its retention rule to `app/jobs.py`, in the same change.
- **For the founders:**
  - the privacy notice's text and its first reviewed version;
  - the list of purposes;
  - what a deletion erases and what is kept, and for how long;
  - how long consent records, data requests and the audit log are kept.

  Until these are decided, those records are kept.
- **Operator-made staff** (ADR 0016) have no consent records, so `consentRequired` is set until they agree in the web app.
