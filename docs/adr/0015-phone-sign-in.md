# ADR 0015: Phone sign-in with one-time codes

- Status: accepted
- Date: 2026-10-19
- Build step: 1.2 (phone OTP login)

## Context

Students, parents and owners sign in with their phone number. They get a six-digit code by SMS, and a correct code starts a session (ADR 0014). ARCHITECTURE §12 fixes the outline:
- HMAC-stored codes;
- a five-minute expiry, five attempts and a 30-second resend cooldown;
- five sends per phone per hour, plus per-IP limits;
- Cloudflare Turnstile before sending;
- E.164 phone numbers;
- an `OtpSender` port with a console adapter.

The codes are cheap to attack, since there are only a million of them, and each one costs an SMS to send. The SMS provider isn't chosen yet. It must be registered on DLT (India's SMS sender registry) and it is a paid vendor, so the choice is the founders'. This ADR records the details.

## Decision

1. **Codes** (`identity/domain/otp.py`, `identity/service/otp.py`):
   - Six digits from `secrets.randbelow`. A code lives 5 minutes, and asking again replaces it.
   - The `otp_challenges` row never stores the code. It stores an HMAC-SHA-256 of the challenge's public id and the code, keyed with `SECRET_KEY` (purpose `otp`).
   - A copy of the database alone can't confirm a guess. Because the challenge id is part of the input, the same code on two challenges hashes differently.
   - A slow unkeyed hash wouldn't help, because a million candidates take seconds to try. The key does the protecting.
   - Codes are compared in constant time.
2. **Challenges.** A code request answers `202` with:
   - the challenge's public id;
   - its expiry;
   - `resendAfter`, when a new code may be asked for, so the form can show an honest countdown.

   Verify takes the challenge id and the code:
   - It locks the challenge row (`FOR UPDATE`), so parallel guesses wait in line. Nobody gets more than five tries, and a right code works once.
   - A wrong code answers `400 OTP_INVALID` with the attempts left, and the attempt is committed. After five wrong codes the challenge is locked: the sixth try answers `OTP_LOCKED` whatever it says.
   - A used challenge, a replaced one and one that doesn't exist all answer `OTP_INVALID`, like a wrong code, so nothing leaks about other people's challenges. An expired challenge answers `OTP_EXPIRED`. None of these count as an attempt.
   - The states (open, used, locked, expired) are pure rules, tested without a database.
3. **Abuse controls, in the order a request meets them:**
   1. **Per-IP limits:** 60 code requests an hour and 120 checks per 15 minutes. They are generous on purpose: campus Wi-Fi and mobile carriers put many students behind one address. They stop floods, not people.
   2. **Turnstile**, before any code is sent (item 6).
   3. **A 30-second cooldown per phone** (`429 OTP_RESEND_TOO_SOON` with `Retry-After`). It is worked out from the challenges themselves, under a per-phone advisory lock (`pg_advisory_xact_lock`), so two simultaneous requests can't both send.
   4. **Five codes per phone per hour** (`429 RATE_LIMITED`), counted in Redis under a keyed pseudonym of the number. It refuses while Redis is down (503), because each code costs an SMS.
   5. **Five wrong tries lock a code.**

   Metrics count codes sent and checks by outcome (`identity.otp.sent`, `identity.otp.checks`). They are what the alerts on spikes and provider failures in ARCHITECTURE §17 and §19 will watch.
4. **Accounts.**
   - **Indian mobiles only:** `+91` and ten digits starting 6–9. Spaces, dashes, brackets and the prefixes `+91`, `91`, `0` and `0091` are accepted, and numbers are stored in E.164 form. Anything else is a `422` field error (`phone_invalid`) that doesn't echo the number back. SMS sent through DLT reaches only Indian numbers, and landlines can't receive SMS.
   - **No account enumeration:** the code request answers the same whether or not the number has an account, and never looks one up. The account is created at the first correct code (`INSERT … ON CONFLICT DO NOTHING`, safe under concurrency), so asking for codes creates nothing. Only someone who proved they hold the phone learns `newUser`.
   - **Suspension:** a suspended account answers `403 ACCOUNT_SUSPENDED` after a correct code.
   - **No staff roles:** a phone sign-in never carries staff roles, whatever the account holds; user sessions drop them on every request. Staff sign in through step 1.3, so a SIM swap can't open the back office.
   - **The session:** a correct code starts a user session and sets the session and CSRF cookies. Any earlier session in the same browser ends (ADR 0014).
5. **Sending codes.**
   - Codes are sent straight away, once the challenge is committed, and no locks are held while sending. They don't go through the outbox like other notifications (ARCHITECTURE §14), because an outbox job would keep the plain code in its payload, and the person is waiting for it.
   - If a send fails, the challenge is deleted and the request answers `503`. Deleting it lets the person retry at once, without the cooldown. The failed send still counts toward the hourly limit.
   - `OTP_SENDER` picks the `OtpSender` adapter:
     - `console` logs the code (warning level, phone masked). It is for local development and tests; deployed environments refuse it at startup.
     - `unavailable` turns phone sign-in off (`503`) while the rest of the API works. Deployed environments run it until the founders choose the SMS provider, whose adapter then joins the list.
6. **Turnstile** (`app/core/human_check.py`):
   - **The check:** the API posts the token, the client's IP address and an idempotency key to Cloudflare's siteverify endpoint.
   - **Retries:** network trouble, 5xx answers, malformed answers and Cloudflare's `internal-error` are retried up to three times with the same key. If Cloudflare stays unreachable, the request is refused (`503`), not let through.
   - **Form and site:** a token counts only for the form and site it was solved on, as Cloudflare advises.
     - The sign-in widget's action must be `otp_request`, and the API schema says so.
     - The hostname must be one of the web app's, taken from `CORS_ALLOWED_ORIGINS`, which is now required when deployed.
     - Cloudflare's test keys report neither field and flag their answers (`result_with_testing_key`), so those answers skip both checks. Real secrets refuse test tokens, so only a test secret ever gets such an answer.
   - **Bad input:** an empty token or one over 2,048 characters fails without asking Cloudflare.
   - **Our own mistakes:** a refused secret key is logged as an error and answers `503`, because it's our misconfiguration, not the visitor's fault.
   - **Configuration:** without `TURNSTILE_SECRET_KEY`, every check passes (local development and tests). Deployed environments require the key, and production refuses Cloudflare's test secrets. Staging may use the always-pass test secret for smoke tests.
   - **Connections:** Turnstile has its own `httpx.AsyncClient` (connect 3 s, read 10 s). Each provider gets its own client, so a slow one can't hold up the others. httpx is now a runtime dependency.
7. **Retention.** A daily job at 03:45 India time deletes challenges after 7 days, with their phone numbers, IP addresses and user agents. That is long enough to investigate abuse, and DPDP says to keep data no longer than needed.

## Consequences

- **Locally,** phone sign-in works end to end, with the code written to the API's log.
- **Deployed,** phone sign-in answers `503` until two things happen. The founders choose a DLT-registered SMS provider and its adapter is built. And someone creates a Turnstile widget for the web app's hostnames, with `otp_request` as the sign-in form's action.
- **One code per solve:** each Turnstile solve allows one code, so asking for another code means solving the widget again.
- **Constants, not tables:** the attempt limit, the cooldown and the per-phone and per-IP limits are constants in code, not database policy. They are security controls, not business rules, and ARCHITECTURE §22 keeps only business policy in tables.
- **A spent code:** a correct code is used up in the same transaction that finds or creates the account, and the session starts in the next one. If starting the session fails, the code is gone and the person asks for a new one.
