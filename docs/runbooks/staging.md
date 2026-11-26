# Staging

Staging is a test copy of the site that follows `main`: every push that passes every check is deployed to it within about 15 minutes. It runs on free plans for now, which the founders chose on 2026-10-31 (ADR 0047). Until launch it is what the main domain shows, under a banner saying it's a test copy. Before launch it moves to the planned Vercel and AWS (ARCHITECTURE §3), and to `staging.` addresses of its own.

- **Web:** https://fixyourstay.in. Render's own address, https://fys-staging-web.onrender.com, still opens the pages, but sign-in works only at the domain, because the cookies are the domain's.
- **API:** served by the web app at the same address, under `/v1/...` (ADR 0055). Its own address is https://fys-staging-api.onrender.com, with its interactive docs at `/docs`.

Everything runs in the US East (Ohio) region, where the Neon project is, so the API sits beside its database and storage.

| Part | Where | Free plan limits that matter |
|---|---|---|
| Web app | Render, free web service `fys-staging-web` | Sleeps after 15 idle minutes. The first visit after that waits about a minute, and a little longer if the API is asleep too. |
| API, worker and migrations, in one container | Render, free web service `fys-staging-api` | Sleeps the same way, and jobs wait while it sleeps. Render's free plan has no background workers. Each start brings the database up to date, loads the geo data and delists any fictional sample still listed (ADR 0073), which adds a few seconds to waking. |
| Cache (rate limits, short-lived data) | Render, free Key Value `fys-staging-cache` | Kept in memory only, so it starts empty after a restart. That's fine for a cache. |
| Database (Postgres with PostGIS) | Neon, free plan, project `fixyourstay-staging` | 0.5 GB. It pauses when idle and wakes in about a second. |
| Photos | Neon's object storage on the same project: buckets `pg-platform-private` (uploads) and `pg-platform-media` (public photos) | 5 GB. It's addressed by path. Its CORS rule still names the old `staging.` address. Uploads (students' dispute photos, and staff's) need it changed to `https://fixyourstay.in`, in Neon's console. |
| Images | GitHub's container registry: `pg_app-api` and `pg_app-web` | Free for a public repository. |

The services are described in `render.yaml`; the deploy is the **Deploy staging** job in `.github/workflows/ci.yml`.


**When the API is asleep:** the host answers the web app's own requests to a sleeping API with a `429` challenge and doesn't wake it, so the site shows no data. `components/system/api-waker.tsx` handles this on the test site only: it asks the API to wake from the visitor's browser, says so, and reloads the page when the API answers, usually after two or three minutes (2 min 42 s when measured).

## Payments

The test site takes payments through Razorpay's test mode (since 2026-11-06): **Pay** opens Razorpay's own checkout, and no real money moves. Production refuses test keys. Setting it up, or changing its keys:

1. In Razorpay's dashboard, switch to **Test Mode**. Under **Account & Settings**, then **API Keys**, generate a test key. Its id starts with `rzp_test_`.
2. Under **Account & Settings**, then **Webhooks**, add a webhook:
   - **URL:** `https://fys-staging-api.onrender.com/v1/webhooks/razorpay`
   - **Secret:** a long random one of your own, not the key's secret.
   - **Alert email:** yours. Razorpay turns a webhook off after 24 hours of failures, and says so there.
   - **Active events:** `payment.authorized`, `payment.captured`, `payment.failed`, `order.paid`, `refund.created`, `refund.processed`, `refund.failed`, `refund.speed_changed`, and, for owners' invoices, `payment_link.paid`, `payment_link.expired` and `payment_link.cancelled`, and, for tokens blocked by mandate, `token.confirmed`, `token.rejected`, `token.cancelled` and `token.paused`.

   If it asks for a code in test mode, Razorpay's docs give `754081`.
3. On `fys-staging-api` in Render, open **Environment** and add `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET`. Never paste them in a chat.
4. `PAYMENT_GATEWAY` is `razorpay` in `render.yaml`. Set it to `fake` to go back to the site's own test bank (ADR 0056), which needs no keys.

Razorpay's test card is `4100 2800 0000 1007`, with CVV `123` and expiry `12/26` (as Razorpay's onboarding gives them), and its test UPI id is `test@razorpay`.

Test mode allows 30 payment links for the account, which owners' invoices use (ADR 0061).

To take tokens as UPI one-time mandates in test mode (ADR 0064), set `TEST_SITE_TOKEN_MODE` to `upi_mandate` on `fys-staging-api`; `payment` goes back to normal payments. The site sets the `token_mode` flag as it starts.

## Google Maps

Until Google's map is set up, every map uses OpenStreetMap's tiles. Once it is, every map is Google's, and the tiles are what it falls back to if Google refuses the key (ADR 0069). Google Maps Platform is a paid service with a monthly free allowance; setting up its billing is the founders' choice.

1. In [Google Cloud's console](https://console.cloud.google.com), create a project (for example `fixyourstay-maps`) and link a billing account to it. Under **Billing**, then **Budgets & alerts**, add a budget with an email alert.
2. Open **APIs & Services**, then **Library**, find **Maps JavaScript API** and choose **Enable**.
3. Open **APIs & Services**, then **Credentials**, then **Create credentials**, then **API key**. Edit the new key:
   - **Application restrictions:** **Websites**, with `https://fixyourstay.in/*` and `https://www.fixyourstay.in/*` (Render serves both).
   - **API restrictions:** **Restrict key**, with **Maps JavaScript API** only.
   - Save. The key shows in every visitor's browser by design; these restrictions are what keep others from using it.
4. Open **Google Maps Platform**, then **Map management**, then **Create map ID**:
   - **Name:** `fixyourstay-web`;
   - **Map type:** **JavaScript**, and **Vector**. Leave tilt and rotation unticked: the site sets them itself.
   - Save, and copy the map ID.
5. In the GitHub repository, open **Settings**, then **Secrets and variables**, then **Actions**, then the **Variables** tab, then **New repository variable**. Add `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`, the key.
   - The map ID is built in from `.github/workflows/ci.yml` (`4fdedc4df3f2d207acc8c8b8`, made on 2026-11-15); a variable `NEXT_PUBLIC_GOOGLE_MAPS_MAP_ID` replaces it. It isn't secret: every map request names it.
6. Rebuild. Both are built into the web image, so they take effect with the next deploy: a push to `main`, or, in the **Actions** tab, the latest **CI** run on `main`, then **Re-run all jobs**.
   - Setting them in Render's **Environment** for `fys-staging-web` does nothing: Render runs the image CI built.
7. Open https://fixyourstay.in/search. The map is Google's, with its logo in the corner. If it's still the OpenStreetMap map, Google refused the key: the browser console names the reason (`RefererNotAllowedMapError`, `ApiNotActivatedMapError`, `BillingNotEnabledMapError`).

To go back to OpenStreetMap's tiles, delete the key's variable and rebuild.

Set up on 2026-11-15: the key is restricted to the two addresses above and to the Maps JavaScript API.

## Booking without a visit

Season one is visit-first: a bed is reserved only from a visit an agent has checked in to. While the fictional samples were here, `TEST_SITE_REMOTE_BOOKING=true` let anyone reserve a bed and pay in test mode without one (ADR 0058). With the founders' real PGs here it's `false` (ADR 0073), so no real owner gets a booking nobody has paid for.

## What staging can't do yet

- **Texts:** there's no SMS provider yet (a paid vendor the founders choose). Sign-in codes show on the sign-in page instead (`OTP_SENDER=screen`, ADR 0055), and visit and booking texts aren't sent.
  - Phone sign-in is off here (`PHONE_SIGN_IN=false`), and staff roles never come with a phone sign-in; production refuses this setting.
- **Listings:** the founders' real PGs, imported as drafts and published by ops once verified (ADRs 0072, 0073). The six fictional sample PGs it showed until 2026-11-26 are delisted, and the banner that said so is gone.
- **Map:** it uses OpenStreetMap's tiles, which their policy allows for a site this lightly used, until Google's map is set up ([Google Maps](#google-maps)).
- **Search engines** are kept out: `robots.txt` disallows everything on staging.

## One-time setup (founders)

Keep every password, key and connection string to yourselves. Paste them only where these steps say, and never into a chat, an issue or a commit.

### 1. Neon (the database and the photos)

1. The project `fixyourstay-staging` exists, in AWS US East (Ohio). Open **Connect** and turn **Connection pooling** off. Copy the connection string (it starts with `postgresql://`) and keep it for step 3. Paste it exactly as Neon shows it: the API turns it into what it needs.
2. The two buckets exist, and the uploads bucket accepts the staging site's uploads. In Neon's console, open the project's object storage, choose the `pg-platform-media` bucket, and set its access to **public read**. Visitors' browsers load the photos from it.
3. The storage keys pasted into a chat on 2026-10-31 count as exposed. **Regenerate them** in the console, and keep the new access key ID and secret for step 3. Do the same for the AI Gateway token, which staging doesn't use.

### 2. Render (the web app, the API and the cache)

1. Sign up at [render.com](https://render.com) with GitHub, on the free Hobby workspace.
2. Choose **New**, then **Blueprint**, and connect the `pg_app` repository. Render reads `render.yaml` and lists `fys-staging-web`, `fys-staging-api`, `fys-staging-cache` and the `fys-staging-shared` group.
3. Render asks for three values. Then choose **Apply**; the first deploy takes a few minutes.
   - `DATABASE_URL`: Neon's connection string from step 1.
   - `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY`: the regenerated storage keys.
4. Open each service's **Settings**, find **Deploy Hook**, and copy its URL. Treat these URLs like passwords.

### 3. GitHub (the deploy hooks)

In the repository, go to **Settings**, then **Secrets and variables**, then **Actions**, then **New repository secret**. Add:

- `RENDER_DEPLOY_HOOK_API`: the deploy hook of `fys-staging-api`;
- `RENDER_DEPLOY_HOOK_WEB`: the deploy hook of `fys-staging-web`.

From then on, every green push to `main` deploys.

### 4. The domain

Done on 2026-11-05, and kept here in case it has to be done again. To show the site at `fixyourstay.in`:

GoDaddy's own forwarding and parked page must go, or they answer instead of Render.

1. In GoDaddy, open **My Products**, then **fixyourstay.in**. Under **Forwarding**, delete any forwarding of the domain.
2. Open **DNS**. Delete every `A` record for `@` (the parked page's, GitHub's `185.199.x.x`), every `AAAA` record, and the `CNAME` for `www`.
3. Add two records:

   | Type | Name | Value |
   |---|---|---|
   | A | `@` | `216.24.57.1` (Render's address for a main domain) |
   | CNAME | `www` | `fys-staging-web.onrender.com` |

   The value is a host name only: no `https://`. If Render's custom-domain page shows a different target, use that. An `api` record does no harm, but nothing uses it now.
4. In the GitHub repository, open **Settings**, then **Pages**, and turn GitHub Pages off: the site isn't served from there.
5. In Render, delete every custom domain on both services. Render refuses a domain that's still on another service, and `fys-staging-api` needs none. The free workspace includes two.
6. On `fys-staging-web`, open **Settings**, then **Custom Domains**, and add `fixyourstay.in`; Render adds `www` itself. Choose **Verify**. Render issues the HTTPS certificates itself, which can take up to an hour after the records are added. If it asks for a card, stop: that's a paid choice for the founders.
7. Then change the site's address in the repository (`NEXT_PUBLIC_SITE_URL` in the **Deploy staging** job; `SITE_URL`, `API_URL` and `SESSION_COOKIE_DOMAIN` in `render.yaml`), so sign-in's cookies and the site's links follow it.

`render.yaml` doesn't list custom domains: a sync asking for more than the plan includes fails whole, and takes its settings with it (ADR 0055).

## Day to day

- **Is it up?** `https://fys-staging-api.onrender.com/readyz` says whether the API reaches the database and the cache. A first visit may take a minute while the services wake.
  - The **Staging smoke** workflow checks every three hours that the API, the home page, search, a PG's page and the API through the site all answer, and emails you when they don't. Run it from the Actions tab, or `make staging-smoke` here.
  - **Settings not taking effect?** Open the Blueprint in Render. Its last sync says whether it failed and why. **Manual Sync** tries again.
- **A deploy:** the **Deploy staging** job in the CI run of that commit says what it deployed. Render's **Events** tab shows each deploy and why one failed.
- **Logs:** each service's **Logs** tab in Render. The API's log has the worker's lines too.
- **A broken deploy:** in Render, open the service's **Events** tab and roll back to the previous deploy. Then fix `main`, and the next green push deploys again.
- **The database:** Neon's console has a SQL editor. Change data only through the app, as everywhere else.

## Later

- **Real listings** come through the ops console: Import for the founders' survey files (ADR 0072), or New listing. `SEED_SAMPLES=false` in `render.yaml` keeps the fictional samples off and delists any still listed as the site starts (ADR 0073).
- **Staff sign-in** (set up 2026-11-06). Staff sign in with Google from the company's Workspace (`STAFF_GOOGLE_DOMAINS=fixyourstay.in`), through an Internal OAuth client whose redirect URI is `https://fixyourstay.in/v1/auth/staff/google/callback`. Its id and secret are set on `fys-staging-api`.
  - **Who's staff:** `TEST_SITE_STAFF` on `fys-staging-api`, set in Render's dashboard because it's personal. It lists each person's phone and Workspace address, address last, people separated by commas, for example `+91XXXXXXXXXX name@fixyourstay.in`. The site makes them staff (ops and admin) as it starts, so saving it is enough; asking again changes nothing and writes no audit entry ([staff access](staff-access.md)).
    The phone only identifies the account. Anyone who signs in here with that number sees the account's name and address, but never its staff tools, which need the Google sign-in.
  - **Taking access away:** deleting someone from `TEST_SITE_STAFF` leaves their roles, and Render's free plan has no shell for `staff remove`. Suspend their Workspace account instead: Google then refuses their sign-in, and a staff session ends within 12 hours.
- **Email and Google sign-in for everyone** (ADR 0068). Until steps 1 and 2 are done, the site shows each email code on screen, so anyone can sign in with any address; until step 4 it offers no Google button to people (staff keep theirs).
  1. **Gmail's app password.** Sign in to Google as support@fixyourstay.in, turn on 2-Step Verification, then make an app password named "Fix Your Stay site" (Google Account, Security, App passwords). If Google offers none, the Workspace admin console has turned app passwords off: turn them back on for that account (Security, Less secure apps and app passwords).
  2. **Render.** On `fys-staging-api`, open Environment and set `SMTP_PASSWORD` to the app password, then save. That's all: `render.yaml` already sets `MAIL_SENDER=smtp` and the address (ADR 0073). Codes and messages then go by email, from Fix Your Stay at support@fixyourstay.in. Check it by signing in with your own address: the code arrives by email and the page no longer shows it.
  3. **Keep the mail out of spam (GoDaddy DNS).** The domain needs:
     - SPF: a TXT record on `@`, `v=spf1 include:_spf.google.com ~all` (Workspace setup may have added it);
     - DKIM: Google Admin console, Apps, Google Workspace, Gmail, Authenticate email. Generate a key, add the TXT record it shows (`google._domainkey`), then press Start authentication;
     - DMARC: a TXT record on `_dmarc`, `v=DMARC1; p=none; rua=mailto:support@fixyourstay.in`.
  4. **Google sign-in for everyone.** In Google Cloud's console, on the staff sign-in's OAuth client project, open Google Auth Platform, Audience. Change the user type from Internal to External, then publish the app. In Branding, fill in the app's name (Fix Your Stay), its support address, the home page `https://fixyourstay.in` and the privacy policy `https://fixyourstay.in/privacy`. The scopes stay `openid` and `email`, which need no review by Google, and the redirect URI stays as it is. Staff tools still take only fixyourstay.in accounts. Then, on `fys-staging-api`, set `GOOGLE_SIGN_IN_FOR_EVERYONE` to `true`: the sign-in page offers Google from then on (until then it doesn't, since Google would turn away everyone outside the Workspace).
  5. **Phone sign-in comes back** once the SMS sender's DLT registration is done and an SMS provider is chosen: set `PHONE_SIGN_IN` to `true`.
- **The move:** the planned Vercel and AWS staging replaces this one (BUILD_PLAN 8.5). Its images and deploy job stay much the same.
