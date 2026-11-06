# Threat model: sign-in, booking and payments (STRIDE)

Step 8.1. Reviewed on 2026-11-06 against the code at `068c2e2`. ARCHITECTURE §17 asks for this model in every phase that touches sign-in or money, so update it in the same change as the code.

Each threat is marked:
- **Done**: the code handles it and a test proves it.
- **Accepted**: a risk knowingly left, with the reason.
- **Open**: still to do, listed under [Open items](#open-items).

## What's protected, and from whom

**Assets**
- Money: tokens, refunds, invoice balances, mandates and the gateway's settlements.
- The beds themselves: no bed is ever promised twice.
- Personal data: phone numbers, names, email addresses, owners' documents and visit details.
- Staff powers: publishing listings, refunds and their approval, reconciliation, feature flags.
- The integrity of the ledger, the invoices and the audit log.
- Secrets: `SECRET_KEY`, the gateway's keys and webhook secret, the OAuth client secret, storage keys.

**Actors**
- Visitors, who aren't signed in.
- Students, parents and owners, who sign in with a code by SMS.
- Staff: ops, admin and field agents, who sign in with Google from the company's Workspace, or with an SMS code plus an authenticator code.
- The worker, which runs jobs from the outbox.
- Razorpay, through its webhooks, and Google, through OIDC.

**Trust boundaries**
- The browser and the web server or API, over the internet.
- The web server and the API.
- The API and its database, cache and object storage.
- The API and Razorpay or Google: our calls out, and Razorpay's webhooks in.

## Sign-in and sessions

| | Threat | What stops it | Status |
|---|---|---|---|
| S | Signing in with someone else's phone | A 6-digit code that lives 5 minutes, allows 5 tries and is stored only as a keyed hash bound to its challenge, compared in constant time (`identity/service/otp.py`). A new code needs 30 seconds' wait; each number gets 5 codes an hour, and each address 60 code requests an hour and 120 checks per 15 minutes. These limits fail closed when Redis is down. Turnstile runs before any code is sent. | Done |
| S | SIM swap or intercepted SMS | Nothing in the app: an SMS code is how the product signs people in. Staff never get staff powers from it alone. | Accepted |
| S | The test site shows codes on screen (`OTP_SENDER=screen`), so anyone can sign in as any number | Production refuses that setting, and the test site holds only fictional data. | Accepted |
| S | A stolen session cookie | 256-bit random tokens, stored only as SHA-256. `__Secure-` cookies are HttpOnly and SameSite=Lax. A per-request CSP nonce keeps injected script out. User sessions end after 30 idle days and staff sessions after 12 hours whatever the activity; "Sign out on every device" ends them all. | Done |
| S | Impersonating staff | Google OIDC with state, nonce and PKCE kept in a `__Host-` cookie. Only allowed Workspace domains or addresses can sign in. The first sign-in links the Google account, and a different account with the same address is refused. Staff roles come only with a staff session. The fallback needs an SMS code and an authenticator code, set up in person. | Done |
| S | A suspended Workspace account keeps a staff session | Google refuses the next sign-in, but a session already open lasts up to 12 hours. | Open (1) |
| T | Cross-site request forgery | A signed double-submit token bound to the session, required for every POST, PUT, PATCH and DELETE by an app-wide dependency (`core/csrf.py`); only signature-checked webhooks are exempt. SameSite=Lax cookies; CORS allows exact origins only. | Done |
| R | Denying a staff action | The audit log records staff, owner and money actions with who did them. A database trigger refuses any UPDATE or DELETE on it. Staff sign-ins and role changes are audited; asking again for roles someone already has writes nothing. | Done |
| I | Finding out who has an account | A code request answers the same whether or not the number has an account. | Done |
| I | Personal data in logs | Phone numbers are masked to their last 4 digits. Where a phone must be looked up but not kept, it's an HMAC under the server's key. Webhook payloads are stored without the payer's details. | Done |
| D | Code flooding and SMS pumping | Turnstile, the resend wait, per-number and per-address limits. | Done |
| D | Floods beyond what the app's limits absorb | No WAF in front yet. | Open (3) |
| E | Raising your own role | Roles come only from the server's records. Every route checks its policy. The authorization matrix test calls every route as every kind of caller in CI, and a route missing from it fails CI. Anyone else's record answers 404. | Done |

## Booking and beds

| | Threat | What stops it | Status |
|---|---|---|---|
| S | Acting on someone else's booking | Each booking route loads the booking for the signed-in person and answers 404 to anyone else. Owners' routes resolve the PG from what they name and check it's theirs. | Done |
| T | Changing a price or an amount | The server computes every amount from stored quotes. A booking copies its quote's figures and is never re-priced. The rent is fixed for the stay. The refund a student confirms when cancelling must equal what the server computes now, or nothing changes (409 `REFUND_CHANGED`). | Done |
| T | Two people booking one bed | The exclusion constraint on `inventory_allocations` refuses overlapping allocations, proven by the 50-concurrent-holds test. Status changes go only through the state machine, compare-and-set on status and version. | Done |
| R | Disputes over what happened | Each change writes a `booking_events` row naming who made it; staff and money actions are also in the audit log. | Done |
| I | An owner's phone or exact address leaking early | Hidden until a visit is scheduled or the booking is confirmed (`hide_owner_contact`, rule 11). Public responses carry only the display point. | Done |
| D | Hoarding beds with holds | One active hold per person, holds expire, 10 holds an hour per person, 10 visit requests a day. | Done |
| E | A student acting as an owner or as ops | Role policies on every route, checked by the authorization matrix. | Done |

## Payments, refunds and the books

| | Threat | What stops it | Status |
|---|---|---|---|
| S | A browser claiming a payment it didn't make | The checkout callback's signature is checked, then the payment is fetched from Razorpay. Only captured money for the order's exact amount moves a booking. | Done |
| S | Forged or replayed webhooks | HMAC on the raw body with the webhook secret, before anything is parsed. Events over 48 hours old are refused. Each provider event id is stored once, so a repeat changes nothing. | Done |
| T | Paying less than what's owed | Orders are made server-side for exactly the token. An invoice is marked paid only by `payment_link.paid` for exactly its balance. A mandate's debit is the server's figure, made only after the notice. | Done |
| T | Changing the books or an invoice | Postings are written in the same transaction as the change they record. A deferred trigger refuses an unbalanced transaction, and posted rows can't be updated or deleted; mistakes are fixed by reversing entries. An issued invoice is fixed by a trigger, and invoice numbers come from a row locked to the end of the transaction, so none is skipped. | Done |
| R | A refund nobody answers for | A refund needs the ops role, a reason and an audit entry. Above ₹5,000 it needs a second person, and the database refuses an approval by whoever asked. | Done |
| I | Card or bank details | They never reach our servers. Razorpay's checkout runs in its own frame, and only the payment page's CSP allows it. | Done |
| D | The gateway down or silent | Checkouts wait. Every 15 minutes, reconciliation asks the gateway about anything that hasn't come back, and the daily settlement match raises an issue for anything that doesn't add up. | Done |
| E | Test money in production, or live keys on a test site | Settings refuse the fake gateway in production and refuse to mix test and live keys. | Done |
| T | A mandate blocking the wrong amount, or debited early | The mandate is for exactly the token. Only the gateway's word that it's confirmed secures a booking, whatever order its webhooks arrive in. The debit goes only after a 26-hour notice; the block is released when the booking ends first. Refused debits and mandates cancelled early become reconciliation issues. | Done |

## Files and personal data

| | Threat | What stops it | Status |
|---|---|---|---|
| T | Uploading a script or a disguised file | Presigned uploads with type and size allowlists, checked by magic bytes. No SVG. Images are re-encoded and EXIF and GPS stripped. | Done |
| I | Someone else's documents or invoices | Private buckets, links that expire after 5 minutes, and ownership checks before a link is made. | Done |
| D | Huge requests | Request bodies are capped and answer 413 (`core/security.py`). | Done |

## Infrastructure and secrets

| | Threat | What stops it | Status |
|---|---|---|---|
| I | Secrets in code or history | Secrets come only from the environment. gitleaks runs in pre-commit and scans the whole history in CI. Claude Code is denied reading `.env` files. | Done |
| I | Secrets pasted into chat | The Neon storage keys and an AI Gateway token were pasted once. | Open (2) |
| T | A dependency or image with a known flaw | pip-audit, pnpm audit, Trivy on the API image, CodeQL, actionlint and zizmor run in CI. Actions are pinned by SHA, and releases wait 7 days before use. | Done |
| D | Floods and scraping | Only the app's own limits and Turnstile for now. | Open (3) |

## Open items
1. **Staff sessions outlive a Workspace suspension by up to 12 hours.** Either end staff sessions at a shorter fixed limit, or check the Google account again during the session. Until then, an admin removes the person's staff roles at once (`staff remove`), and on the test site suspends their Workspace account.
2. **Rotate the secrets pasted in chat**: the Neon storage keys and the AI Gateway token. This is for the founders.
3. **WAF and bot protection**: Cloudflare in front of the site and API (step 8.5).
4. **An external penetration test** before growing past the first micro-market (ARCHITECTURE §17).
