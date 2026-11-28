# ADR 0074: Email through Gmail's API over HTTPS, where the host blocks SMTP

- Status: accepted
- Date: 2026-11-28
- Build step: the founders' request of 2026-11-27, sign-in codes by email rather than on screen

## Context

- **Email went through Gmail's SMTP server** (ADR 0068), from support@fixyourstay.in with a Workspace app password. ADR 0073 left the founders one step: setting that password on the host.
- **Render's free web services block SMTP's ports** (25, 465 and 587) since September 2025 ([Render's changelog](https://render.com/changelog/free-web-services-will-no-longer-allow-outbound-traffic-to-smtp-ports)). With the password set, every send timed out after the mailer's 20 seconds, and sign-in said "We couldn't send the code".
- **The founders chose to stay on the free plan** (2026-11-28) rather than pay for an instance that may use SMTP. They didn't want another email vendor either: Google Workspace is already theirs.

## Decision

1. **A fourth mail sender, `gmail_api`** (`app/core/gmail.py`), which sends over HTTPS (port 443) through Gmail's API:
   - A Google service account in the founders' Cloud project holds a key.
   - The Workspace's domain-wide delegation lets that service account act for the Workspace's users with one scope, `gmail.send`.
   - For each hour of sending, the mailer signs a token (RS256, with `cryptography`; no new dependency) saying it acts for `MAIL_FROM`, and trades it at Google's token endpoint for an access token.
   - It posts each message, built as the SMTP sender builds it, to Gmail's `users/me/messages/send`. Gmail sends it from support@fixyourstay.in's own mailbox, so it carries Google's own DKIM signature.
   - A token Gmail refuses is replaced once.
2. **The key is a secret on the host**, in `GMAIL_SERVICE_ACCOUNT`: the downloaded JSON file's text, flattened or as base64 if a field won't take line breaks. It never reaches a log or a repr.
3. **The same waiting rule as SMTP's** (ADR 0073). Outside production, a sender missing what it needs (no key, a text that isn't one, or no `MAIL_FROM`) sends nothing, and the site shows codes on screen as before. The API logs which settings it waits for, by name only. Production refuses to start that way.
4. **Google's refusals are explained in the log**, in Google's own words, with what they usually mean here:
   - `unauthorized_client`: the delegation isn't set up;
   - `SERVICE_DISABLED`: the Gmail API is off;
   - `invalid_grant`: the address or the key is wrong.
5. **SMTP stays** for any host that allows it. `render.yaml` sets `MAIL_SENDER=gmail_api` and drops the SMTP settings.

## The founders' steps (docs/runbooks/staging.md)

1. In Google Cloud, in the project that holds the site's Google sign-in, turn on the Gmail API.
2. Make a service account (no roles), copy its Unique ID, and download a JSON key.
   - New Workspace organizations forbid key downloads by default (the "Disable service account key creation" policy). An admin overrides it for this project.
3. In the Workspace admin console, open Domain-wide delegation. Allow that Unique ID the scope `https://www.googleapis.com/auth/gmail.send`.
4. On `fys-staging-api`, set `GMAIL_SERVICE_ACCOUNT` to the file's text, and save and deploy.

## Consequences

- **Sign-in codes and messages go by email** on the free plan, with no new vendor and no cost. Gmail's sending limits for a Workspace mailbox apply (about 2,000 messages a day), far above the site's needs.
- **The key is powerful.** Domain-wide delegation lets the key send as any user of the Workspace, though only send. The code acts only for `MAIL_FROM`.
  - The key lives only on the host.
  - If it may have leaked, delete it in the service account's Keys tab and remove the delegation, then make a new one.
  - A narrower alternative, one mailbox's own consent stored as a refresh token, is a later option if the Workspace grows.
- **SPF, DKIM and DMARC** in the domain's DNS still decide whether mail lands in the inbox (the runbook's DNS step).
