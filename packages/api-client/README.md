# @pg-platform/api-client

The typed client the web app uses to call the API, generated from the API's OpenAPI schema.

- `openapi.json` is the API's schema, exported without starting the API (`python -m app.openapi`).
- `src/generated/schema.ts` is generated from it by openapi-typescript.
- `src/index.ts` exports `createApiClient` (openapi-fetch) and the schema types (`paths`, `Schemas`).

Both generated files come from `make gen-client`. **Never edit them by hand**: change the API and
regenerate. `make check-client`, part of `make check`, fails when they are out of date with the API.

The web app doesn't use this package directly: `apps/web/src/lib/api` adds timeouts, cookie and
request-id forwarding and typed errors (ADR 0012).
