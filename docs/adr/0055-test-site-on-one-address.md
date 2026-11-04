# ADR 0055: The test site serves the API at its own address, waits for a sleeping API, and shows sign-in codes on screen

- Status: accepted
- Date: 2026-11-04
- Build step: none (staging; extends ADR 0047)

## Context

- **Search broke on staging** (reported by the founders on 2026-10-31 and 2026-11-04).
  - Render still ran the first Blueprint's settings: the old `staging.` custom domains, and an API that only accepted `https://staging.fixyourstay.in`.
  - The web server fetches from its `API_URL`. That was almost certainly `api.staging.fixyourstay.in`, whose DNS had been removed, so every page needing the API answered 500.
  - The switch to `fixyourstay.in` in `render.yaml` (ADR 0047) never took effect. The likely reason: it asked for more custom domains than the free workspace's two, so the sync failed as a whole, with the settings in it. Only Render's dashboard could confirm this.
- **Two `onrender.com` addresses can't share cookies.** `onrender.com` is a public suffix, so browsers treat each service as its own site. Sign-in can't work there while the browser calls the API directly.
- **A sibling `api.` domain may cost money.** Render's free plan includes two custom domains, then charges $0.25 a month each. It adds `www` by itself, and its docs don't say whether that counts. The founders ask before any paid choice.
- **The free plan sleeps.** Both services sleep after 15 idle minutes and take about a minute to wake. Server rendering waited 3 seconds for the API, so the first visit to a sleeping site was an error page.
- **There's no SMS provider yet.** With `OTP_SENDER=unavailable`, nobody could sign in on the deployed site. The founders asked on 2026-11-04 for the code to show on the sign-in page.

## Decision

1. **The test site serves the API itself.** A build with `API_PROXY_TARGET` rewrites `/v1/...` to that address, and `NEXT_PUBLIC_API_SAME_ORIGIN=true` keeps the browser's calls on the site.
   - Whatever address the site is on, the browser sees one site: cookies are first-party, and CORS has nothing to allow.
   - The server calls the API directly at `API_PROXY_TARGET`, which is built into the image, so a stale `API_URL` in Render can't break it.
   - The API's public address (`API_URL`, which Google's redirect URI starts with) is then the site's own.
   - Everything else stays as ADR 0002 and ARCHITECTURE §3 plan: with these two values empty, as in production, the browser calls the API directly.
2. **It waits for a sleeping API.** `NEXT_PUBLIC_API_WAIT_MS=90000` sets how long server rendering, the browser and the rewrite wait. Without it, the usual 3 and 10 seconds apply.
3. **`OTP_SENDER=screen` shows the code on the sign-in page.** Nothing is sent and nothing is logged; the API's answer carries the code, as local development's does.
   - **The risk, accepted for a test copy only:** whoever asks gets the code, so anyone can sign in with any number, including an owner's.
   - **What limits it:** staff roles never come with a phone sign-in (an existing test), so the ops console stays out of reach. Turnstile and every rate limit still apply. The site holds fictional PGs under a banner saying so.
   - **Production refuses it:** the API won't start with `OTP_SENDER=screen` when `APP_ENV=production` (tested).
4. **Custom domains leave `render.yaml`** and are added in Render's dashboard, so a domain the plan doesn't include can't fail a sync and hold back its settings. `fixyourstay.in` goes on the web service only; there's no `api.` domain to pay for.
5. **The smoke check** uses Render's own addresses, which work whatever the DNS says, and also asks for the API through the site.

## Consequences

- **Tested:** the whole browser suite passed in this mode on a local production build, sign-in included. CI's browser tests run the direct mode, and the smoke check covers the rewrite on the live site every three hours.
- **Browser calls on staging take one more hop.** That's fine for a test site, and production doesn't have it.
- **Attaching `fixyourstay.in`** takes the founders' steps in the staging runbook, then one commit here: the site's address and the cookie domain name the new address. `SESSION_COOKIE_DOMAIN` names the site's own host for now, because Render keeps a value a Blueprint stops listing.
- **Before anything real goes on this site,** whether real listings or real people's numbers, `OTP_SENDER=screen` has to go, along with the rest of what ADR 0047 calls a test copy. A real launch needs the SMS provider the founders choose, and production's settings already insist on that.
