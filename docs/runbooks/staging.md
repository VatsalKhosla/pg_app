# Staging

Staging is a test copy of the site that follows `main`: every push that passes every check is deployed to it within about 15 minutes. It runs on free plans for now, which the founders chose on 2026-10-31 (ADR 0047). Until launch it is what the main domain shows, under a banner saying it's a test copy. Before launch it moves to the planned Vercel and AWS (ARCHITECTURE §3), and to `staging.` addresses of its own.

- **Web:** https://fixyourstay.in. Render's own address, https://fys-staging-web.onrender.com, still opens the pages, but sign-in works only at the domain, because the cookies are the domain's.
- **API:** served by the web app at the same address, under `/v1/...` (ADR 0055). Its own address is https://fys-staging-api.onrender.com, with its interactive docs at `/docs`.

Everything runs in the US East (Ohio) region, where the Neon project is, so the API sits beside its database and storage.

| Part | Where | Free plan limits that matter |
|---|---|---|
| Web app | Render, free web service `fys-staging-web` | Sleeps after 15 idle minutes. The first visit after that waits about a minute, and a little longer if the API is asleep too. |
| API, worker and migrations, in one container | Render, free web service `fys-staging-api` | Sleeps the same way, and jobs wait while it sleeps. Render's free plan has no background workers. Each start brings the database up to date, loads the geo data and checks the samples are there, which adds a few seconds to waking. |
| Cache (rate limits, short-lived data) | Render, free Key Value `fys-staging-cache` | Kept in memory only, so it starts empty after a restart. That's fine for a cache. |
| Database (Postgres with PostGIS) | Neon, free plan, project `fixyourstay-staging` | 0.5 GB. It pauses when idle and wakes in about a second. |
| Photos | Neon's object storage on the same project: buckets `pg-platform-private` (uploads) and `pg-platform-media` (public photos) | 5 GB. It's addressed by path. Its CORS rule still names the old `staging.` address. Uploads (students' dispute photos, and staff's) need it changed to `https://fixyourstay.in`, in Neon's console. |
| Images | GitHub's container registry: `pg_app-api` and `pg_app-web` | Free for a public repository. |

The services are described in `render.yaml`; the deploy is the **Deploy staging** job in `.github/workflows/ci.yml`.

## What staging can't do yet

- **Texts:** there's no SMS provider yet (a paid vendor the founders choose). Sign-in codes show on the sign-in page instead (`OTP_SENDER=screen`, ADR 0055), and visit and booking texts aren't sent.
  - Anyone can sign in with any number here, so never put real people's details on this site. Staff roles never come with a phone sign-in, and production refuses this setting.
- **Staff sign-in** needs a Google OAuth client for staging (see [Later](#later)).
- **Real listings:** staging shows the six fictional sample PGs, added on its first start. A banner on every page says they're samples (see [Later](#later)).
- **Map:** it uses OpenStreetMap's tiles, which their policy allows for a site this lightly used. The live site needs a map provider the founders choose.
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

- **Real listings** come through the ops console, once staff can sign in. To stop adding the samples, set `SEED_SAMPLES` to `false` on `fys-staging-api`; the ones already there stay until they're unpublished in the ops console.
- **Staff sign-in:**
  1. Create a Google OAuth client in a Google Cloud project, with the redirect URI `https://fixyourstay.in/v1/auth/staff/google/callback` (the site's address, as it serves the API).
  2. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `STAFF_GOOGLE_EMAILS` on `fys-staging-api`.
  3. Make the founders staff with `python -m app.manage staff add`, run with staging's settings ([staff access](staff-access.md)).
- **The move:** the planned Vercel and AWS staging replaces this one (BUILD_PLAN 8.5). Its images and deploy job stay much the same.
