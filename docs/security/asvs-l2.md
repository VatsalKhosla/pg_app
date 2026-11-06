# OWASP ASVS 5.0 level 2 checklist

Step 8.1. Assessed on 2026-11-06 against the code at `068c2e2`. Level 2 is the 253 requirements marked L1 or L2 in [ASVS 5.0.0](https://github.com/OWASP/ASVS/tree/v5.0.0/5.0) (CC BY-SA 4.0). Requirements are named by ID and summed up in our own words; the standard has the exact text. The [threat model](threat-model.md) explains the reasoning behind the controls cited here.

Each requirement gets one of four statuses:
- **Met**, with the evidence beside it.
- **Partial**: what's missing is said.
- **Open**: not met yet; listed with the fix under [Gaps](#gaps).
- **N/A**: the feature isn't in this product, with the reason.

Recount and re-tick this file whenever a change touches what it cites.

**Summary:** 160 Met, 20 Partial, 4 Open, 69 N/A. The open items and partial ones needing work are the [Gaps](#gaps) at the end.

## What ASVS asks to have written down

### Limits (2.1.3, 6.1.1, 15.1.3)
Per person (or per phone number):
- 1 active hold at a time, and 10 holds an hour.
- 10 visit requests a day.
- 5 sign-in codes an hour per number, with 30 seconds between codes and 5 tries per code.

Per address (these fail closed when Redis is down):
- 60 code requests an hour.
- 120 code checks per 15 minutes.
- 60 staff sign-ins an hour.
- 60 authenticator checks per 15 minutes.
- 1,200 map-pin requests per 10 minutes, a generous limit because the map asks again on every pan.

For everyone:
- Request bodies are capped (413).
- A page of results holds at most 50.
- The map answers at most 2,000 pins.
- Refunds above ₹5,000 need a second person.

The heavy work is the search and map queries, which are precomputed price summaries plus caching; image processing and PDF rendering, which run only in the worker; and the price calendars, which are cached.

### Cryptography in use (11.1.1, 11.1.2)

| What | Algorithm | Key | Where |
|---|---|---|---|
| Session tokens | 256-bit random value, stored as SHA-256 | none | `identity/service/sessions.py` |
| CSRF tokens | HMAC-SHA256 over a nonce and a hash of the session | `SECRET_KEY` | `core/csrf.py` |
| Sign-in codes | 6 random digits, stored as HMAC-SHA256 bound to their challenge | `SECRET_KEY` | `identity/service/otp.py` |
| Phone lookups and other pseudonyms | HMAC-SHA256 with a purpose string | `SECRET_KEY` | `core/hashing.py` |
| Staff authenticators | TOTP (RFC 6238, HMAC-SHA1 for authenticator apps), secret derived from `SECRET_KEY` and a per-person salt | `SECRET_KEY` | `identity/domain/totp.py` |
| Razorpay checkout and webhooks | HMAC-SHA256 | the key secret, the webhook secret | `payments/adapters/razorpay.py` |
| Google sign-in | Google's ID token, RS256, keys from Google's JWKS | Google's | `identity/adapters/google_oidc.py` |
| Transport | TLS 1.2 and 1.3, certificates from the hosts | the hosts' | Render, Neon |

Rotation:
- **Gateway, OAuth and storage keys** are replaced at the provider and in the host's settings; nothing else depends on them.
- **`SECRET_KEY`** signs out everyone and invalidates sign-in codes in flight. It also invalidates staff authenticators, which need enrolling again. Version it before rotating it in production (gap 6).

### Data and its protection (14.1.1, 14.1.2)
- **Secret**: tokens, codes, keys, authenticator secrets. Never logged; stored hashed or derived, or only in the host's secret settings.
- **Personal**: phone numbers, names, email addresses, visit details, IP addresses on audit and consent records, and owners' documents.
  - Phone numbers are masked in logs to their last 4 digits.
  - Personal data is shown only to its owner and to staff who need it; an owner's phone and exact address are hidden until a visit is booked or a booking confirmed.
  - It's exported and erased on request (DPDP).
  - Documents live in a private bucket behind 5-minute links.
- **Money records**: payments, refunds, postings and invoices. Kept and never changed: the ledger and invoices are append-only, guarded by triggers.
- **Public**: listings, prices, display points and policies.

### Logging (16.1.1)
- **What's logged:** one structured JSON line per request (request id, route, status, duration, user id), plus job results, security events (refused sign-ins, failed checks, rate limits) and unhandled errors with their tracebacks.
- **Where:** everything goes to standard output, which the host keeps: Render now, CloudWatch in production. Sentry gets errors once its DSN is set.
- **What's never logged:** tokens, codes, secrets, full webhook payloads or unmasked phone numbers.
- **Separately:** staff, owner and money actions also go to the append-only `audit_logs` table.

### Fixing vulnerable dependencies (15.1.1)
pip-audit, pnpm audit and Trivy run on every push and every week. Each finding is fixed, or written up as a reviewed exception with its reason, within:
- 7 days for critical;
- 30 days for high;
- 90 days for anything else.

Updates wait 7 days after release.

## V1 Encoding and sanitization

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 1.1.1 | Decode input once, to a canonical form | Met | The frameworks (Starlette, Pydantic, Next.js) decode once; nothing decodes again. |
| 1.1.2 | Encode output at the last step | Met | React escapes text at render; JSON is serialised by Pydantic. |
| 1.2.1 | Context-aware output encoding | Met | React and JSON. No HTML is built by hand. |
| 1.2.2 | Encode untrusted data in URLs; only safe schemes | Met | URLs are built with `URLSearchParams` or the typed client; links are to our own routes, and photos come from our storage. |
| 1.2.3 | Encode JavaScript and JSON content | Met | JSON-LD escapes `<` as `<` (`lib/seo/json-ld.ts`). |
| 1.2.4 | Parameterised database queries | Met | SQLAlchemy 2 queries with bound parameters; no SQL is built from input. |
| 1.2.5 | No OS command injection | Met | The only subprocesses are fixed commands (`all_in_one.py`, the manage commands), with no shell. |
| 1.2.6, 1.2.7, 1.2.8 | LDAP, XPath, LaTeX | N/A | None used. |
| 1.2.9 | Escape regex metacharacters | Met | No regular expression is built from input; text search uses PostgreSQL with bound parameters. |
| 1.3.1 | Sanitise HTML from editors | N/A | Nobody submits HTML; owners' text is shown as text. |
| 1.3.2 | No eval | Met | None in the API or the web app; the CSP refuses `unsafe-eval`. |
| 1.3.3 | Sanitise data bound for dangerous contexts | Met | Pydantic patterns and lengths on every field; owners' text is never interpreted. |
| 1.3.4 | User-supplied SVG | Met | SVG uploads are refused (type allowlist, magic bytes). |
| 1.3.5 | User-supplied Markdown, CSS and templates | Met | None accepted. The legal pages' Markdown is our own, from the repository. |
| 1.3.6 | SSRF | Met | The API calls only addresses from its settings (Razorpay, Google, Turnstile, storage, the web app). No URL comes from a request. |
| 1.3.7 | Template injection | Met | Text templates and the invoice PDF use fixed layouts filled with values. |
| 1.3.8 | JNDI | N/A | Not Java. |
| 1.3.9 | Memcache injection | N/A | No memcache. Redis keys are built from validated values. |
| 1.3.10 | Format strings | Met | No input is used as a format string. |
| 1.3.11 | SMTP and IMAP injection | N/A | No email is sent yet. Check this when an email sender is added. |
| 1.4.1, 1.4.3 | Memory safety | N/A | Python and TypeScript are memory-safe. |
| 1.4.2 | Integer overflow | Met | Money is integer paise in `bigint` columns, and Pydantic bounds every number. Fuzzing found a year-0 month crashing search, now refused (377e062). |
| 1.5.1 | XML external entities | N/A | No XML is parsed; Razorpay's reports are JSON. |
| 1.5.2 | Safe deserialisation | Met | JSON only, into Pydantic models with `extra="forbid"`; no pickle. |

## V2 Validation and business logic

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 2.1.1 | Document input validation rules | Met | The request models (Pydantic, generated into the OpenAPI schema) are the rules: types, patterns, ranges. |
| 2.1.2 | Document combined-data rules | Met | ARCHITECTURE §7 and §8 (booking dates, quotes, search filters); `SEARCH_INVALID` for combinations that make no sense. |
| 2.1.3 | Document business limits | Met | [Limits](#limits-213-611-1513) above. |
| 2.2.1 | Validate against business expectations | Met | Allowlisted enums, patterns and ranges; quotes and prices only from the server. |
| 2.2.2 | Validate at a trusted layer | Met | The API validates everything; Zod in the browser is only for convenience. |
| 2.2.3 | Check combinations | Met | Moving in is checked against the quote, the hold and the beds; the search filters are checked together. |
| 2.3.1 | Steps in order | Met | Booking changes go only through the state machine, compare-and-set. |
| 2.3.2 | Enforce business limits | Met | One hold, rate limits, the price lock and the refund approval threshold. |
| 2.3.3 | Transactions | Met | Each service owns its transaction; changes and their ledger postings commit together. |
| 2.3.4 | Locking for limited resources | Met | The exclusion constraint on `inventory_allocations`, proven by the 50-concurrent-holds test. |
| 2.4.1 | Anti-automation | Partial | Rate limits and Turnstile, but no WAF yet (gap 3). |

## V3 Web frontend security

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 3.2.1 | Stop responses rendering in the wrong context | Met | JSON with `nosniff`; uploads served from storage with their own type, on another host. |
| 3.2.2 | Safe text rendering | Met | React text nodes; nothing is set as HTML. |
| 3.3.1 | Secure cookies with a prefix | Met | `__Secure-session`, `__Secure-csrf`, `__Host-staff-login` (`core/cookies.py`). |
| 3.3.2 | SameSite by purpose | Met | Lax on all of them. |
| 3.3.3 | `__Host-` unless shared on purpose | Met | Session and CSRF cookies are shared with the API's sibling host on purpose (`__Secure-`); the staff login cookie is `__Host-`. |
| 3.3.4 | HttpOnly for session tokens | Met | Session and staff login cookies are HttpOnly. The CSRF cookie is readable, as the pattern needs. |
| 3.4.1 | HSTS for a year, including subdomains | Met | On both the API and the web app (`core/security.py`, `next.config.ts`). |
| 3.4.2 | CORS allowlist | Met | Exact origins from `CORS_ALLOWED_ORIGINS`. |
| 3.4.3 | Content-Security-Policy | Met | A per-request nonce with `strict-dynamic` and no `unsafe-inline` scripts (`lib/security/csp.ts`); browser tests check it. |
| 3.4.4 | `nosniff` everywhere | Met | On both. |
| 3.4.5 | Referrer policy | Met | `no-referrer` on the API, `strict-origin-when-cross-origin` on the web app. |
| 3.4.6 | `frame-ancestors` | Met | `'none'` on every page. |
| 3.5.1 | Check that cross-origin requests come from us | Met | The CSRF token on every unsafe method. |
| 3.5.2 | No way around the preflight | Met | The CSRF header forces a preflight, and the token is checked whatever the CORS outcome. |
| 3.5.3 | Unsafe methods for sensitive actions | Met | Every change is POST, PUT, PATCH or DELETE; GETs change nothing. |
| 3.5.4 | Separate applications on separate hosts | Met | Web, API and media on separate hosts in production; the test site serves the API through the web host (ADR 0055). |
| 3.5.5 | Check postMessage origins | N/A | We don't listen for messages; Razorpay's checkout handles its own. |
| 3.7.1 | Only supported client technology | Met | No plugins. |
| 3.7.2 | Redirects to other hosts only from an allowlist | Met | Sign-in's return path must be one of ours (`safeNext`); Google's sign-in URL is fixed. |

## V4 API and web service

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 4.1.1 | Content-Type with charset | Met | JSON (UTF-8 by definition) and problem+json from the API; HTML with `charset=utf-8` from Next.js. |
| 4.1.2 | Only user-facing endpoints redirect to HTTPS | Partial | The hosts redirect every endpoint, the API's included. HSTS and https-only clients keep it from mattering. |
| 4.1.3 | Intermediary headers can't be overridden | Partial | The test site trusts every forwarding proxy (`FORWARDED_ALLOW_IPS="*"`), so whether a client can set its own `X-Forwarded-For` depends on Render (gap 7). |
| 4.2.1 | Request smuggling | Met | One proxy (the host's) in front of uvicorn's HTTP/1.1 parser; nothing in between rewrites messages. |
| 4.3.1, 4.3.2 | GraphQL | N/A | No GraphQL. |
| 4.4.1, 4.4.2, 4.4.3, 4.4.4 | WebSockets | N/A | No WebSockets. |

## V5 File handling

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 5.1.1 | Document file types and sizes | Met | ARCHITECTURE §13: images and PDFs, their sizes, private and public buckets. |
| 5.2.1 | Size limits | Met | Presigned uploads carry a size range, and the worker checks again. |
| 5.2.2 | Extension and content checks | Met | Type allowlist and magic bytes; images are re-encoded. |
| 5.2.3 | Archive bombs | N/A | Archives aren't accepted. |
| 5.3.1 | Uploads never run | Met | They live in object storage, never on an app server. |
| 5.3.2 | Paths from trusted data | Met | Object keys are generated by the server. |
| 5.4.1 | Ignore user filenames; set Content-Disposition | Met | Names are ours; downloads (invoice PDFs, exports) set their own. |
| 5.4.2 | Encode served filenames | Met | Filenames are generated (`invoice-FY2026-27-000001.pdf`), so nothing needs escaping. |
| 5.4.3 | Antivirus | Open | Images are re-encoded, which strips anything hidden in them, but owners' PDFs aren't scanned (gap 4). |

## V6 Authentication

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 6.1.1 | Document anti-automation for sign-in | Met | [Limits](#limits-213-611-1513) above, and the [threat model](threat-model.md#sign-in-and-sessions). |
| 6.1.2 | Context-specific password words | N/A | No passwords. |
| 6.1.3 | Document every sign-in route | Met | SMS code for everyone; Google, or SMS code and authenticator, for staff (ADR 0016, `docs/runbooks/staff-access.md`). |
| 6.2.1 to 6.2.12 | Passwords | N/A | No passwords anywhere. |
| 6.3.1 | Defend against stuffing and brute force | Met | Codes expire in 5 minutes and allow 5 tries; per-number and per-address limits; Turnstile. |
| 6.3.2 | No default accounts | Met | Every account starts from a sign-in or an operator's `staff add`. |
| 6.3.3 | Multiple factors | Partial | Staff need Google (whose 2-Step Verification the founders should enforce in the Workspace admin console, gap 5) or an SMS code plus an authenticator. Students and owners sign in with an SMS code alone, a product decision. |
| 6.3.4 | No undocumented sign-in routes | Met | The local-only shortcuts (`--without-app`, console codes) are refused outside local development. |
| 6.4.1 | Generated codes are random and expire | Met | `secrets.randbelow`, 5 minutes, once. |
| 6.4.2 | No secret questions | Met | None. |
| 6.4.3 | Password reset keeps MFA | N/A | No passwords. |
| 6.4.4 | Proof of identity when a factor is lost | Met | A new authenticator is set up in person (staff access runbook). |
| 6.5.1 | Codes and TOTP work once | Met | A used code is consumed, and a TOTP step is refused if it isn't newer than the last used one. |
| 6.5.2 | Hash low-entropy lookup secrets | N/A | No lookup secrets (recovery codes). |
| 6.5.3 | CSPRNG for codes and seeds | Met | `secrets` throughout. |
| 6.5.4 | At least 20 bits in codes | Met | 6 random digits. |
| 6.5.5 | Codes have a lifetime of 10 minutes at most | Met | 5 minutes for SMS codes, 30-second steps for TOTP. |
| 6.6.1 | SMS codes only for checked numbers, with the risk explained | Partial | The SMS code is the product's sign-in and checks the number at the same time; staff powers never come from it alone. |
| 6.6.2 | Codes bound to their own request | Met | Hashed together with their challenge's id. |
| 6.6.3 | Rate limits on codes | Met | 5 tries per code, 120 checks per 15 minutes per address. |
| 6.8.1 | No spoofing across identity providers | Met | One provider (Google). The Google account links by `sub`, and a different account with the same address is refused. |
| 6.8.2 | Validate assertion signatures | Met | The ID token's signature against Google's keys (`google_oidc.py`). |
| 6.8.3 | SAML replay | N/A | No SAML. |
| 6.8.4 | Strength or recentness from the IdP | N/A | We don't ask Google for a particular strength; 2-Step Verification is enforced in Workspace (gap 5). |

## V7 Session management

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 7.1.1 | Document timeouts, with reasons | Met | Users: 30 idle days, and 90 days from sign-in at most. Staff: 12 hours, idle or not (`identity/domain/sessions.py`, ADR 0014). |
| 7.1.2 | Document concurrent sessions | Met | Any number per account. People see them and can end them (`GET /v1/me/sessions`), or end them all. |
| 7.1.3 | Document federated sessions | Met | A staff session doesn't depend on the Google session; it ends after 12 hours. |
| 7.2.1 | Verify sessions in the backend | Met | Every request looks the session up by its hash. |
| 7.2.2 | Dynamic tokens | Met | A new random token per sign-in. |
| 7.2.3 | CSPRNG, at least 128 bits | Met | 256 bits. |
| 7.2.4 | New token at sign-in, old one ended | Met | Signing in issues a new session; moving up to a staff session issues another. |
| 7.3.1 | Inactivity timeout | Met | As 7.1.1. |
| 7.3.2 | Absolute lifetime | Met | 90 days from sign-in for users, however active; 12 hours for staff. |
| 7.4.1 | Ended means unusable | Met | Sign-out and expiry end the session server-side. |
| 7.4.2 | Disabling an account ends its sessions | Met | Suspended accounts' sessions are refused; removing staff roles stops staff sessions. |
| 7.4.3 | Offer to end other sessions after a factor changes | Met | No factor can be changed by the person; "Sign out on every device" is always there. |
| 7.4.4 | Visible sign-out | Met | In the account menu on every signed-in page. |
| 7.4.5 | Admins can end sessions | Partial | Removing staff roles or suspending an account ends a person's sessions, but there's no button to end one person's or everyone's. |
| 7.5.1 | Sign in again before changing sign-in details | N/A | The phone number is the account and can't be changed; staff details change only from the command line. |
| 7.5.2 | People see and end their sessions | Partial | They can, without signing in again first. |
| 7.6.1 | RP and IdP session lifetimes as documented | Met | As 7.1.3. |
| 7.6.2 | Sessions only by explicit action | Met | Sign-in needs the person to act; Google always asks. |

## V8 Authorization

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 8.1.1 | Document function and data access rules | Met | ARCHITECTURE §12 and `tests/authorization.py`, the authorization matrix. |
| 8.1.2 | Document field-level rules | Met | Rule 11 (an owner's contact and exact address), and the public schemas' allowlists (backend rules). |
| 8.2.1 | Function-level checks | Met | A policy on every route, and the matrix test calls every route as every caller in CI. |
| 8.2.2 | Data-level checks (IDOR) | Met | Records load through their owner; anyone else gets 404. |
| 8.2.3 | Field-level checks | Met | Separate response models per audience; requests forbid extra fields. |
| 8.3.1 | Enforce at a trusted layer | Met | All in the API. |
| 8.4.1 | Tenant isolation | Met | Owners reach only their own PGs (ADR 0063), checked route by route by the matrix. |

## V9 Self-contained tokens

We don't issue self-contained tokens. This chapter applies to Google's ID token, which we check, and to our CSRF token, which is a MAC.

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 9.1.1 | Check the signature or MAC first | Met | The ID token's signature; the CSRF token's HMAC. |
| 9.1.2 | Allowlisted algorithms | Met | RS256 only for the ID token. |
| 9.1.3 | Keys from trusted sources | Met | Google's published keys, at a fixed address. |
| 9.2.1 | Check validity times | Met | `exp` is checked. |
| 9.2.2 | Check the token's type and purpose | Met | Only the ID token from our own code exchange. |
| 9.2.3 | Check the audience | Met | `aud` and `azp` must be our client id. |
| 9.2.4 | Audience restriction when one key serves several | N/A | We issue no tokens. |

## V10 OAuth and OIDC

We're an OIDC client of Google, and nothing more.

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 10.1.1 | Tokens only where needed | Met | The API exchanges the code; no Google token reaches the browser. |
| 10.1.2 | Only values from flows we started | Met | State, nonce and PKCE verifier come from our own `__Host-` cookie. |
| 10.2.1 | CSRF on the code flow | Met | State and PKCE. |
| 10.2.2 | Mix-up with several authorization servers | N/A | One: Google. |
| 10.3.1 to 10.3.4 | Resource server | N/A | We accept no access tokens. |
| 10.4.1 to 10.4.11 | Authorization server | N/A | Google is the authorization server. Our client is confidential, with a registered redirect URI. |
| 10.5.1 | ID token replay | Met | The nonce must match. |
| 10.5.2 | Identify by `sub` | Met | Linked by `sub`. |
| 10.5.3 | Reject a server impersonating another | Met | The issuer must be Google's. |
| 10.5.4 | ID token audience | Met | `aud` must be our client id. |
| 10.5.5 | Back-channel logout | N/A | Not used. |
| 10.6.1, 10.6.2 | OpenID provider | N/A | We're not one. |
| 10.7.1, 10.7.2, 10.7.3 | Consent at the authorization server | N/A | Google's. The client is Internal, for the company's Workspace only. |

## V11 Cryptography

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 11.1.1 | A key management policy | Partial | [Cryptography in use](#cryptography-in-use-1111-1112) covers rotation; `SECRET_KEY` has no versions yet (gap 6). |
| 11.1.2 | A cryptographic inventory | Met | [Cryptography in use](#cryptography-in-use-1111-1112). |
| 11.2.1 | Industry-validated implementations | Met | Python's `hashlib`, `hmac` and `secrets`; Google's keys through a maintained JOSE library; TLS from the hosts. |
| 11.2.2 | Crypto agility | Partial | Algorithms are named in one place each, but everything derived from `SECRET_KEY` changes together (gap 6). |
| 11.2.3 | At least 128-bit security | Met | HMAC-SHA256 with a key of at least 32 characters; 256-bit tokens. |
| 11.3.1, 11.3.2 | Block modes and ciphers | Open | We don't encrypt anything ourselves yet; documents should get envelope encryption with AES-GCM (gap 1). |
| 11.3.3 | Authenticated encryption | Open | As above. |
| 11.4.1 | Approved hash functions | Met | SHA-256. HMAC-SHA1 only inside TOTP (RFC 6238), as authenticator apps expect, where SHA-1's weakness doesn't apply. |
| 11.4.2 | Password hashing | N/A | No passwords. |
| 11.4.3 | Collision-resistant hashes for integrity | Met | SHA-256 (invoice PDFs and agreement documents are fingerprinted with it). |
| 11.4.4 | KDFs from passwords | N/A | No passwords. |
| 11.5.1 | CSPRNG for unguessable values | Met | `secrets` for tokens, codes, nonces and salts. |
| 11.6.1 | Approved algorithms for keys and signatures | Met | We generate no key pairs; signatures are checked with RS256. |

## V12 Secure communication

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 12.1.1 | TLS 1.2 or later | Met | The hosts (Render, Neon) end TLS 1.2 and 1.3. |
| 12.1.2 | Strong cipher suites | Met | The hosts' modern defaults. |
| 12.1.3 | mTLS | N/A | Not used. |
| 12.2.1 | TLS for every external connection | Met | HTTPS only, with HSTS. |
| 12.2.2 | Publicly trusted certificates | Met | Issued by the hosts. |
| 12.3.1 | Encrypt every connection | Partial | The database and outbound calls use TLS; Redis on the test site runs inside Render's private network without TLS. |
| 12.3.2 | TLS clients check certificates | Partial | httpx checks them. The database connection uses `ssl=require`, which encrypts but doesn't verify (gap 2). |
| 12.3.3 | TLS between internal services | Met | The web server reaches the API over HTTPS. |
| 12.3.4 | Trusted certificates internally | Met | Public certificates everywhere. |

## V13 Configuration

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 13.1.1 | Document what the app talks to | Met | ARCHITECTURE §3 and §9; `render.yaml`. |
| 13.2.1 | Backend connections authenticated | Met | The database, Redis and storage each need credentials. |
| 13.2.2 | Least privilege between components | Partial | The app's database role also runs migrations; separate roles come with production (8.5). |
| 13.2.3 | No default credentials | Met | Generated on every deployed host; `platform:platform` exists only in local Docker. |
| 13.2.4, 13.2.5 | An allowlist of outbound destinations | Partial | Fixed in settings, but nothing at the network level enforces it yet (8.5). |
| 13.3.1 | A secrets manager | Partial | The host's encrypted settings and GitHub secrets; AWS Secrets Manager in production (8.5). |
| 13.3.2 | Least privilege for secrets | Partial | As 13.3.1. |
| 13.4.1 | No source control metadata deployed | Met | Images copy only named paths. |
| 13.4.2 | No debug modes in production | Met | FastAPI's debug is off and Next.js runs a production build; the settings refuse local-only options. |
| 13.4.3 | No directory listings | Met | Nothing serves directories. |
| 13.4.4 | No TRACE | Met | Starlette answers 405. |
| 13.4.5 | No stray docs or monitoring endpoints | Met | Interactive docs only where enabled; the health checks are meant to be public and say nothing sensitive. |

## V14 Data protection

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 14.1.1 | Classify sensitive data | Met | [Data and its protection](#data-and-its-protection-1411-1412). |
| 14.1.2 | Protection rules per class | Met | As above. |
| 14.2.1 | No sensitive data in URLs | Met | Phone numbers and codes travel in bodies; booking codes in URLs aren't secrets. |
| 14.2.2 | No caching in servers | Met | The API defaults to `Cache-Control: no-store`; only public listings and search are cached. |
| 14.2.3 | Nothing sensitive to trackers | Met | Analytics events carry no unmasked personal data (ADR 0035). |
| 14.2.4 | Controls documented per class | Met | As 14.1.1, with the DPDP export and erasure (`compliance` module). |
| 14.3.1 | Clear the browser's data at sign-out | Met | The session ends server-side and its cookies are cleared. The page then reloads from scratch, which drops everything held in memory. Browser storage holds nothing personal (14.3.3). |
| 14.3.2 | Anti-caching headers | Met | `no-store` on the API; signed-in pages are dynamic and uncached. |
| 14.3.3 | Nothing sensitive in browser storage | Met | Only `sessionStorage`, for an anonymous analytics id and a view counter. |

## V15 Secure coding and architecture

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 15.1.1 | Remediation times documented | Met | [Fixing vulnerable dependencies](#fixing-vulnerable-dependencies-1511) above. |
| 15.1.2 | An SBOM | Partial | `uv.lock` and `pnpm-lock.yaml` list everything, pinned; no SBOM file is published with each build yet. |
| 15.1.3 | Document heavy functions | Met | [Limits](#limits-213-611-1513) above. |
| 15.2.1 | Components within remediation times | Met | Audits are clean in CI. |
| 15.2.2 | Defend heavy functions | Met | Rate limits, caching, precomputed summaries, page caps, and heavy work in the worker. |
| 15.2.3 | Nothing extra in production | Met | The test bank and the local helpers answer 404 or are refused outside tests and the test site. |
| 15.3.1 | Return only what's needed | Met | Response models per audience; public responses leave out internal ids, coordinates and contacts. |
| 15.3.2 | Don't follow redirects | Met | httpx doesn't by default, and we don't turn it on. |
| 15.3.3 | Mass assignment | Met | `extra="forbid"` request models with named fields. |
| 15.3.4 | The client's address from trusted fields | Partial | See 4.1.3 (gap 7). |
| 15.3.5 | Strict types | Met | mypy strict and Pydantic; TypeScript strict. |
| 15.3.6 | Prototype pollution | Met | No deep merges of untrusted JSON in the web app. |
| 15.3.7 | Parameter pollution | Met | Each parameter is declared once with a type; repeats can't change its meaning. |

## V16 Security logging and error handling

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 16.1.1 | A logging inventory | Met | [Logging](#logging-1611) above. |
| 16.2.1 | When, where, who, what | Met | Timestamp, request id, route, user id and event in every structured line. |
| 16.2.2 | Synchronised time, in UTC | Met | ISO UTC timestamps from the hosts' clocks. |
| 16.2.3 | Logs only where documented | Met | Standard output, plus Sentry once set. |
| 16.2.4 | A common format | Met | JSON lines. |
| 16.2.5 | Log sensitive data by its class | Met | Phones masked; no tokens, codes or secrets. |
| 16.3.1 | Log sign-ins, successful and failed | Met | Sign-ins, refusals and their reasons; staff sign-ins in the audit log too. |
| 16.3.2 | Log failed authorization | Met | Every request line carries its status, so 403 and 404 answers are there. |
| 16.3.3 | Log security events and bypass attempts | Met | Validation, CSRF and rate-limit refusals; forged webhooks. |
| 16.3.4 | Log unexpected errors | Met | Unhandled errors with tracebacks. |
| 16.4.1 | Encode against log injection | Met | Structured JSON escapes every value. |
| 16.4.2 | Protect logs | Partial | Kept by the host, where only the founders' accounts reach them; append-only storage comes with production (8.3). |
| 16.4.3 | Send logs to a separate system | Partial | The host's log store; alerting and a separate store come in 8.3. |
| 16.5.1 | Generic error messages | Met | problem+json with a stable code and no internals. |
| 16.5.2 | Keep running securely when a dependency fails | Met | Payments wait and reconciliation catches up; the map still answers without Redis; sign-in limits fail closed. |
| 16.5.3 | Fail securely | Met | Transactions roll back whole; webhooks are verified first; nothing fails open. |

## V17 WebRTC

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| 17.1.1, 17.2.1, 17.2.2, 17.2.3, 17.2.4, 17.3.1, 17.3.2 | TURN, media and signalling servers | N/A | No WebRTC. |

## Gaps
1. **Encrypt owners' documents** with envelope encryption, AES-GCM per object under a key held by the host's key service (11.3.x; ARCHITECTURE §17). They're in a private bucket today, encrypted only by the storage provider.
2. **Verify the database's certificate**: `ssl=verify-full` with the system's CA bundle, tried on staging first (12.3.2).
3. **WAF and bot protection**: Cloudflare in step 8.5 (2.4.1).
4. **Scan owners' PDFs** for malware before ops open them, or turn them into images (5.4.3).
5. **Enforce 2-Step Verification** for every account in the Workspace admin console. This is for the founders, and free (6.3.3).
6. **Version `SECRET_KEY`** so it can be rotated without signing everyone out or re-enrolling every authenticator (11.1.1, 11.2.2).
7. **Trust only the load balancer's addresses for `X-Forwarded-For`** in production (8.5), and confirm how Render treats a client's own header (4.1.3, 15.3.4).
