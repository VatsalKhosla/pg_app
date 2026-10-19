# ADR 0012: Typed API client

- Status: accepted
- Date: 2026-10-19
- Build step: 0.6 (typed API client pipeline)

## Context

The web app calls the API only through a typed client generated from the API's OpenAPI schema (ARCHITECTURE §16), so a change on one side that breaks the other fails a check instead of reaching a student. The client must also carry the API's RFC 9457 errors, forward the visitor's API cookies from server components, and fail CI when it is out of date.

## Decision

1. **openapi-typescript generates types; openapi-fetch makes the calls.** There are no generated functions. The schema's paths type each call's parameters, body and responses, and the runtime is about 6 KB. Responses are readonly (`--immutable`).
2. **The schema is exported, not fetched.**
   - `python -m app.openapi` builds the app with placeholder settings that ignore the environment, so every machine and CI write identical bytes. It needs no running API, database or Redis.
   - `packages/api-client/openapi.json` is committed, so a pull request shows the contract change, and `oasdiff` (step 0.7) compares it against main.
3. **The schema describes the errors the API really sends.**
   - Every operation declares `4XX` and `5XX` as `application/problem+json` with `ProblemDetail`. FastAPI then adds none of its own `HTTPValidationError` 422s, a shape the API never sends.
   - Documented non-problem bodies keep their own schema, such as `/readyz`'s 503 `Readiness`.
   - Operation ids are tag plus function name in camelCase (`systemHealthz`), not `healthz_healthz_get`.
4. **Stale clients fail the build.** `make check-client` regenerates into a temporary directory and diffs against the committed files. It is part of `make check`, which CI runs.
5. **`apps/web/src/lib/api` wraps the client:**
   - **No caching, and every request has a timeout.** The timeout signal goes in fetch's `init`, not on a copied Request: undici links a copy's signal only weakly. Caller and timeout signals are combined by hand, because `AbortSignal.any` needs Safari 17.4.
   - **`unwrap()` returns the data or throws a typed `ApiError`.** The error carries status, the API's code, the problem details, the request id and field errors. Failures the API never reported get client codes: `API_UNREACHABLE`, `API_TIMEOUT` and `UNEXPECTED_RESPONSE`. A caller's own cancellation passes through unchanged.
   - **`getServerApi()` is for server components and actions:**
     - It reaches the API at `API_URL`, read at start-up (an internal address in production), or else the public URL.
     - It forwards only the cookies named in `API_COOKIES` (deny by default; step 1.1 adds the session and CSRF cookies).
     - It forwards the page's request id, which `src/proxy.ts` makes for every request and never takes from the browser. The API's log lines then match the page.
     - It waits at most 3 s.
   - **`browserApi` is for client components.** It sends credentials, which the API's CORS allows for this site's origin.
6. **The home page shows the API's liveness through the client.** It streams in behind `Suspense`, so a slow or absent API never holds up the page. With the API down it reads "Unavailable".
7. **TypeScript 6 is allowed for openapi-typescript,** although it declares `^5`. It only uses the compiler API to print the generated file, and `make check-client` would show any difference.

## Consequences

- A pull request that changes the API must include `make gen-client`'s output, or CI fails.
- Callers branch on `ApiError.code`, the stable codes in ARCHITECTURE §15, and forms read `fieldErrors`.
- Server rendering that calls the API depends on its latency. The 3 s budget bounds the damage, and API-dependent parts of a page should stream behind `Suspense`.
- The package exports TypeScript source: Next.js transpiles it (`transpilePackages`), and Vitest reads it directly.
