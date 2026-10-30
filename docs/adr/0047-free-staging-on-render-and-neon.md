# ADR 0047: Staging on free plans for now, deployed from GitHub: Render runs the web app, the API with its worker, and a cache; Neon holds the database and the photos

- Status: accepted
- Date: 2026-10-31
- Build step: alongside 5.3 (the founders asked for a staging site that follows the build)

## Context

- **The founders' choice.** They asked for the site to be deployed from GitHub as it's built. The planned hosting is Vercel for the web and AWS Mumbai for the rest (ARCHITECTURE §3, BUILD_PLAN 8.5), and both are paid. On 2026-10-31 the founders chose **free hosts for now**, moving to the planned stack before launch.
- **GitHub alone can't host the site.** GitHub Pages serves static files only. The site needs its API, PostgreSQL with PostGIS, a cache and a worker.
- **The free options, as of October 2026, from the providers' pages:**
  - **Vercel's Hobby plan** is for non-commercial personal use only, so it's out even for a business's staging.
  - **Render's free web services** sleep after 15 idle minutes and take about a minute to wake. They have 512 MB and share 750 hours a month per workspace. Render has no free background workers, and its free Postgres expires after 30 days. Its free Key Value is in memory only.
  - **Neon's free plan** includes Postgres with PostGIS (0.5 GB per project) and S3-compatible object storage (5 GB). It scales to zero when idle and has no region in Mumbai.
  - **Koyeb** has one free service, and only in Frankfurt or Washington.
  - **Oracle's free VMs** were reportedly cut in mid-2026 and are reclaimed when idle.
  - **Netlify's free plan** allows commercial use, but its Next.js 16 adapter isn't stable yet.
- **A deployed environment is held to production's rules** (`app/config.py`): HTTPS everywhere, a Turnstile secret, no console sign-in codes or texts, and a revalidation secret. Cloudflare publishes Turnstile test keys that always pass, and the API allows them on staging only.

## Decision

1. **Render runs the services, as `render.yaml` describes them.** They run in Ohio, beside the founders' Neon project (AWS us-east-2), so the API sits next to its database and storage. Users in India wait a little longer for each page than they would from Singapore, which a staging site can bear.
   - **The web app** is Next.js's standalone server in a new image (`apps/web/Dockerfile`).
   - **The API** is the existing image. On staging it runs `python -m app.all_in_one`, because the free plan has no workers:
     - migrations first;
     - then the geo data, which a load changes only where it differs;
     - then, with `SEED_SAMPLES=true`, the six fictional sample PGs, which a second run leaves alone;
     - then the worker and the API side by side.

     When either process stops, so does the other, and Render restarts the container.
   - **The cache** is Render's Key Value, which only the private network reaches.

   Production keeps the API and the worker apart.
2. **Neon holds the database and the photos, on its free plan.**
   - **The database:** Postgres with PostGIS. The API takes the connection string as Neon shows it. Any `postgresql://` URL is used with asyncpg, `sslmode` becomes asyncpg's `ssl`, and `channel_binding`, which asyncpg doesn't take, is dropped.
   - **The photos:** Neon's S3-compatible object storage on the same project, with 5 GB. It's addressed by path, as SeaweedFS is locally, so the S3 adapter needs no change. It takes browser uploads by presigned POST, has public-read buckets and CORS rules, and answers PutBucketPolicy with 501.
   - **The buckets:** on 2026-10-31, with the founders' keys, Claude Code created `pg-platform-private` and `pg-platform-media`, and allowed uploads to the private one from the staging site only. A test upload and a signed download worked. Making the media bucket public is a setting in Neon's console.
3. **GitHub Actions deploys.** A **Deploy staging** job joins CI and runs only for a push to `main` that passed every other check:
   - it builds both images with the same make targets a developer uses (`make api-image`, `make web-image`);
   - it publishes them to GitHub's container registry, by commit and as `staging`;
   - it calls each Render service's deploy hook with the image's digest, the API first.

   With no hooks configured, it publishes and skips the deploy. Images are built on GitHub, so Render's build minutes go unused, and every push is built from the same commit CI tested.
4. **The fictional sample PGs go on staging**, at the founders' request (2026-10-31). `catalog samples` now refuses only production, and the web app shows a banner on every page of staging: a test copy whose PGs are fictional samples, where nothing booked is real. They need storage for their photos, which Neon now provides.
5. **What staging inlines:**
   - **the addresses:** at first `staging.fixyourstay.in` and `api.staging.fixyourstay.in`. On 2026-10-31 the founders asked for the main domain to show the site, so until launch staging is `fixyourstay.in` (with `www.` redirecting) and `api.fixyourstay.in`, and the session cookie covers the domain. At launch, production takes these and staging moves back to `staging.` addresses;
   - **Turnstile:** Cloudflare's test keys;
   - **the map:** OpenStreetMap's tiles, since a site this lightly used is within their tile policy. The live site still waits for a map provider the founders choose.

   Search engines are kept out, as `robots.txt` already does on staging.
6. **What waits for a founder's choice:**
   - **SMS:** phone sign-in stays off, because the provider is a paid vendor.
   - **Real listings:** they come through the ops console once staff can sign in.
   - **Staff sign-in:** it needs a Google OAuth client for staging.

## Consequences

- **The founders' steps** are in `docs/runbooks/staging.md`, about 15 minutes once:
  - make the media bucket public-read (the images come out public, as the repository is);
  - regenerate the storage keys, which were pasted into a chat;
  - apply the blueprint with Neon's connection string and the storage keys;
  - save the two deploy hooks as GitHub secrets;
  - point the domain at Render in GoDaddy: an A record for the main domain, CNAMEs for `www` and `api`, and GoDaddy's forwarding and parked page removed.
- **A first visit after a quiet spell waits about a minute** while the web app wakes, and the API may add another. Jobs run only while the API is awake.
- **Each green push to `main` takes about five minutes longer**, for building and publishing the images.
- **The move to Vercel and AWS** (8.5) replaces the hosts and keeps the images, the deploy job and the settings.
