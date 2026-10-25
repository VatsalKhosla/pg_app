# Staff access

Who can use the staff tools, and how to change that. Staff sign in with Google or, until the company has a Google Workspace, with a phone code followed by a code from an authenticator app (ADR 0016). Nobody becomes staff by signing in: an operator makes them staff with the commands below.

Run the commands where the API's settings are: `make manage args="…"` locally, or `python -m app.manage …` inside the deployed API's environment (a one-off task from Phase 8 on). They change that environment's database directly and write every change to the audit log. Phone numbers are Indian mobile numbers, written any usual way.

## Give someone staff access

1. Make them staff, with every role they need (`field_agent`, `ops`, `admin`). The phone number must be their own, because the fallback sign-in starts with a code sent to it.

   ```sh
   make manage args="staff add +91XXXXXXXXXX --role ops --email name@company.in --name 'Their name'"
   ```

2. **For Google sign-in:** `--email` must be their Google account's address, and that account must be allowed: its Workspace domain in `STAFF_GOOGLE_DOMAINS`, or the exact address in `STAFF_GOOGLE_EMAILS`. Their first Google sign-in links the account.
3. **For the fallback:** set up their authenticator app with them in the room.

   ```sh
   make manage args="staff enrol-authenticator +91XXXXXXXXXX"
   ```

   They add the setup key it prints to an authenticator app (Google Authenticator, Microsoft Authenticator, 1Password or similar), then type the code the app shows. Never send the key or the link by chat, email or any website, including QR-code sites: anyone with the key can make codes.

They then sign in on the web app's staff sign-in page (step 1.6). A staff session ends 12 hours after sign-in.

What each role opens:
- `ops` and `admin`: the ops console at `/ops`, where listings are built and published (ADR 0023).
- `field_agent`: the staff home for now; verification screens come later.

## Take access away

- **All of it:** `make manage args="staff remove +91XXXXXXXXXX"`. Their staff sessions stop working at their next request, and their authenticator app is removed.
- **One role:** add `--role admin` (or another role) to the same command.
- **Leaving the company:** also remove them from the Workspace, or their address from `STAFF_GOOGLE_EMAILS`.
- **Lost or replaced phone:** `staff remove-authenticator`, then enrol their new app.
- **Replaced Google account:** a new Google account with the same address is refused, on purpose, because addresses can change hands. If the person really did replace their account, run `staff remove-google`; their next Google sign-in then links the new one.

## See who has access

- `make manage args="staff list"` prints each staff member's roles and how they sign in.
- An admin in a staff session can call `GET /v1/admin/staff`.
- The `audit_logs` table holds every change and sign-in: actions `staff.roles_granted`, `staff.roles_removed`, `staff.authenticator_enrolled`, `staff.authenticator_removed`, `staff.google_linked`, `staff.google_unlinked` and `staff.sign_in`.

## Set up Google sign-in (once per environment)

1. In a Google Cloud project owned by the company, create an OAuth client of type **Web application**.
2. Add one authorized redirect URI, exactly `API_URL` followed by `/v1/auth/staff/google/callback`. For example, `https://api.<domain>/v1/auth/staff/google/callback`; locally, `http://localhost:8000/v1/auth/staff/google/callback`.
3. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in the environment's secret store, never in code. Also set `STAFF_GOOGLE_DOMAINS` (the Workspace domain) or `STAFF_GOOGLE_EMAILS` (single addresses). `SITE_URL` and `API_URL` must be the environment's own https addresses.
4. In the Workspace admin console, enforce 2-step verification for everyone. The API can't see whether it is on.
5. Check it: a staff member with an allowed account signs in; an account outside the allowlist is sent back with `STAFF_ACCOUNT_NOT_ALLOWED`.

Once everyone signs in with Google, remove the authenticator apps (`staff remove-authenticator`) to retire the fallback.

## When a sign-in fails

The web app's staff sign-in page shows the error code it was sent back with.

| Code | Meaning | What to do |
|---|---|---|
| `STAFF_ACCOUNT_NOT_ALLOWED` | The Google account isn't allowed; or the account isn't staff, is suspended, or has no confirmed authenticator app; or the address belongs to a different Google account than the one linked | The API logs `staff sign-in refused` with the reason. Check `staff list` and the allowlist; for a replaced Google account, see above |
| `STAFF_SIGN_IN_EXPIRED` | The Google sign-in took over 10 minutes, was finished in another tab or browser, or reused a code | Start again |
| `STAFF_SIGN_IN_CANCELLED` | The person cancelled at Google | Nothing |
| `SERVICE_UNAVAILABLE` | Google sign-in isn't set up here, Google can't be reached, or Google refused our OAuth client | Look for `Google refused the code` or `Google ID token refused` in the logs; check the client id, the secret and the redirect URI |
| `TOTP_INVALID` | A wrong or already-used authenticator code | Wait for the next code. If it keeps failing, check the phone's clock is set automatically |
| `RATE_LIMITED` | More than five authenticator codes tried within 15 minutes | Wait, then try again |

Rotating `SECRET_KEY` invalidates every authenticator app; enrol them all again afterwards.
