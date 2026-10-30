# Staging

Staging is a test copy of the site that follows `main`: every push that passes every check is deployed to it within about 15 minutes. It runs on free plans for now, which the founders chose on 2026-10-31 (ADR 0047). Before launch it moves to the planned Vercel and AWS (ARCHITECTURE §3).

- **Web:** https://staging.fixyourstay.in
- **API:** https://api.staging.fixyourstay.in (its interactive docs are at `/docs`)

Everything runs in the US East (Ohio) region, where the Neon project is, so the API sits beside its database and storage.

| Part | Where | Free plan limits that matter |
|---|---|---|
| Web app | Render, free web service `fys-staging-web` | Sleeps after 15 idle minutes. The first visit after that waits about a minute. |
| API, worker and migrations, in one container | Render, free web service `fys-staging-api` | Sleeps the same way, and jobs wait while it sleeps. Render's free plan has no background workers. |
| Cache (rate limits, short-lived data) | Render, free Key Value `fys-staging-cache` | Kept in memory only, so it starts empty after a restart. That's fine for a cache. |
| Database (Postgres with PostGIS) | Neon, free plan, project `fixyourstay-staging` | 0.5 GB. It pauses when idle and wakes in about a second. |
| Photos | Neon's object storage on the same project: buckets `pg-platform-private` (uploads) and `pg-platform-media` (public photos) | 5 GB. It's addressed by path, and uploads are allowed only from the staging site (CORS). |
| Images | GitHub's container registry: `pg_app-api` and `pg_app-web` | Free for a public repository. |

The services are described in `render.yaml`; the deploy is the **Deploy staging** job in `.github/workflows/ci.yml`.

## What staging can't do yet

- **Phone sign-in** answers "unavailable", because there is no SMS provider yet (a paid vendor the founders choose). Students can browse but can't sign in.
- **Staff sign-in** needs a Google OAuth client for staging (see [Later](#later)).
- **Listings:** it starts with none (see [Later](#later)).
- **Map:** it uses OpenStreetMap's tiles, which their policy allows for a site this lightly used. The live site needs a map provider the founders choose.
- **Search engines** are kept out: `robots.txt` disallows everything on staging.

## One-time setup (founders)

Keep every password, key and connection string to yourselves. Paste them only where these steps say, and never into a chat, an issue or a commit.

### 1. Neon (the database and the photos)

1. The project `fixyourstay-staging` exists, in AWS US East (Ohio). Open **Connect** and turn **Connection pooling** off. Copy the connection string (it starts with `postgresql://`) and keep it for step 3. Paste it exactly as Neon shows it: the API turns it into what it needs.
2. The two buckets exist, and the uploads bucket accepts the staging site's uploads. In Neon's console, open the project's object storage, choose the `pg-platform-media` bucket, and set its access to **public read**. Visitors' browsers load the photos from it.
3. The storage keys pasted into a chat on 2026-10-31 count as exposed. **Regenerate them** in the console, and keep the new access key ID and secret for step 3. Do the same for the AI Gateway token, which staging doesn't use.

### 2. GitHub (after the first green push with this file)

The **Deploy staging** job publishes two images. Make both public, so Render can pull them without a password:

1. Open the repository's main page. Under **Packages** on the right, open `pg_app-api`.
2. Go to **Package settings**. Under **Danger Zone**, choose **Change visibility**, then **Public**, and confirm.
3. Do the same for `pg_app-web`.

### 3. Render (the web app, the API and the cache)

1. Sign up at [render.com](https://render.com) with GitHub, on the free Hobby workspace.
2. Choose **New**, then **Blueprint**, and connect the `pg_app` repository. Render reads `render.yaml` and lists `fys-staging-web`, `fys-staging-api`, `fys-staging-cache` and the `fys-staging-shared` group.
3. Render asks for three values. Then choose **Apply**; the first deploy takes a few minutes.
   - `DATABASE_URL`: Neon's connection string from step 1.
   - `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY`: the regenerated storage keys.
4. Open each service's **Settings**, find **Deploy Hook**, and copy its URL. Treat these URLs like passwords.

### 4. GitHub again (the deploy hooks)

In the repository, go to **Settings**, then **Secrets and variables**, then **Actions**, then **New repository secret**. Add:

- `RENDER_DEPLOY_HOOK_API`: the deploy hook of `fys-staging-api`;
- `RENDER_DEPLOY_HOOK_WEB`: the deploy hook of `fys-staging-web`.

From then on, every green push to `main` deploys.

### 5. GoDaddy (the addresses)

1. In Render, open `fys-staging-web`, then **Settings**, then **Custom Domains**. It lists `staging.fixyourstay.in` and the target to point it at, which ends in `onrender.com`.
2. In GoDaddy, go to **My Products**, then **fixyourstay.in**, then **DNS**, then **Add New Record**. Add a **CNAME** with name `staging` and that target as its value.
3. Do the same for `fys-staging-api`: a **CNAME** named `api.staging` with its target.
4. Back in Render, choose **Verify** on each domain. Render issues the HTTPS certificates itself, which can take up to an hour after the records are added.

## Day to day

- **Is it up?** `https://api.staging.fixyourstay.in/readyz` says whether the API reaches the database and the cache. A first visit may take a minute while the services wake.
- **A deploy:** the **Deploy staging** job in the CI run of that commit says what it deployed. Render's **Events** tab shows each deploy and why one failed.
- **Logs:** each service's **Logs** tab in Render. The API's log has the worker's lines too.
- **A broken deploy:** in Render, open the service's **Events** tab and roll back to the previous deploy. Then fix `main`, and the next green push deploys again.
- **The database:** Neon's console has a SQL editor. Change data only through the app, as everywhere else.

## Later

- **Listings:** staging starts empty. Two ways to fill it, both the founders' call:
  - the six fictional sample PGs, clearly labelled, which today refuse to run anywhere deployed;
  - real listings added through the ops console, once staff can sign in.
- **Staff sign-in:**
  1. Create a Google OAuth client in a Google Cloud project, with the redirect URI `https://api.staging.fixyourstay.in/v1/auth/staff/google/callback`.
  2. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `STAFF_GOOGLE_EMAILS` on `fys-staging-api`.
  3. Make the founders staff with `python -m app.manage staff add`, run with staging's settings ([staff access](staff-access.md)).
- **The move:** the planned Vercel and AWS staging replaces this one (BUILD_PLAN 8.5). Its images and deploy job stay much the same.
