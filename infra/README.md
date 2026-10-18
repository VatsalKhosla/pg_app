# Infrastructure

## Local (`docker-compose.yml`)

`make infra-up` starts these and waits until every health check passes; `make dev` does the same and then runs the apps. Ports are bound to `127.0.0.1` only, and every image is pinned by tag and digest. Decisions: `docs/adr/0008-local-infrastructure.md`.

| Service | What | Address | Dev credentials |
|---|---|---|---|
| `postgres` | PostgreSQL 18 + PostGIS 3.6 (built from `postgres/Dockerfile`); btree_gist, pg_trgm and citext included | `127.0.0.1:5432`, database `platform` | `platform` / `platform` |
| `valkey` | Valkey 8.1, the Redis-compatible cache and rate-limit store; nothing is persisted | `127.0.0.1:6379` | password `platform` |
| `s3` | SeaweedFS 4.48, S3-compatible object storage; requests must be signed | `http://127.0.0.1:8333` | `seaweedfs/s3.json` |
| `mailpit` | Catches every email the app sends | SMTP `127.0.0.1:1025`, inbox `http://127.0.0.1:8025` | none |

- `make health` checks every service (and the apps, when `make dev` is running).
- `make infra-down` stops the containers and keeps the data; `make infra-reset` also deletes the local data volumes.
- Ports can be moved with `POSTGRES_PORT`, `VALKEY_PORT`, `S3_PORT`, `MAILPIT_SMTP_PORT` and `MAILPIT_UI_PORT` (update `apps/api/.env` to match).

## Cloud (`terraform/`, Phase 8)

Staging and production on AWS Mumbai, plus Vercel and Cloudflare settings. Until then, manual setup is documented in `docs/runbooks/`.
