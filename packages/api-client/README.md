# @pg-platform/api-client

The typed client the web app uses to call the API.

- `src/generated/` is generated from the API's OpenAPI schema by `make gen-client`. **Never edit it by hand**; change the API and regenerate.
- CI fails when the generated client is out of date with the API (step 0.6).
