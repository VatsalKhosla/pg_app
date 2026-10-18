# ADR 0008: Local infrastructure

- Status: accepted
- Date: 2026-10-18
- Build step: 0.2 (local infrastructure)

## Context

Step 0.2 asks for PostgreSQL with PostGIS, Redis, MinIO and Mailpit in Docker Compose. Since the plan was written:

- MinIO stopped publishing community images; `minio/minio` no longer exists on Docker Hub.
- The `postgis/postgis` image is still built for amd64 only, while the founders' Macs are likely Apple Silicon (arm64).
- Production targets Amazon RDS for PostgreSQL 18 with PostGIS 3.6.3, and AWS ElastiCache's lowest-priced engine is Valkey, the BSD-licensed fork of Redis.

## Decision

1. **PostgreSQL 18 with PostGIS 3.6**, built from `infra/postgres/Dockerfile`: the official multi-arch `postgres:18.6-trixie` image plus the PostgreSQL project's own `postgresql-18-postgis-3` packages. It runs natively on amd64 and arm64, uses glibc collations (`en_US.utf8`) like RDS and the same PostGIS minor version as RDS. btree_gist, pg_trgm and citext ship with PostgreSQL.
2. **Valkey 8.1 for Redis.** It speaks the Redis protocol, so code and docs keep saying "Redis"; ElastiCache for Valkey is the expected production engine, confirmed with the Phase 8 infrastructure. A password is required, as in production, and nothing is persisted (nothing durable lives in Redis).
3. **SeaweedFS 4.48 (`weed mini`) for S3**, replacing MinIO. It is Apache-2.0 licensed and mature, and supports presigned URLs, multipart uploads and bucket CORS. Requests must be signed with the development identity in `infra/seaweedfs/s3.json`, as on AWS. The alternatives were RustFS (1.0 in September 2026, releasing every few days) and Garage (needs a cluster-layout step before first use).
4. **Mailpit 1.31** catches every email the app sends.
5. **Safe defaults**: every port is bound to `127.0.0.1`, every image is pinned by tag and digest, and every service has a health check, so `docker compose up --wait` returns only when everything is usable.
6. **`make dev`** runs the API (uvicorn with reload), the worker (restarted by watchfiles) and the web app (`next dev`) together under `concurrently`. The web app switches to `--webpack` automatically where glibc is older than 2.29 (ADR 0007).
7. **No database init scripts.** Extensions and roles are created by migrations (step 0.3 onwards), so local, CI and RDS databases are built the same way. `make health` only proves the extensions can be created, inside a rolled-back transaction.

## Consequences

- The first `make dev` builds the PostgreSQL image (about a minute) and pulls three more images.
- Testcontainers (step 0.3 onwards) and CI (step 0.7) need the same PostgreSQL image: build it from `infra/postgres/Dockerfile` there too, or publish it to a registry in step 0.7.
- Binding to `127.0.0.1` keeps the services off the network, but other users of a shared machine can still reach loopback ports, so local data must stay fictional (CLAUDE.md already requires this).
- Revisit SeaweedFS if the media pipeline (step 2.3) needs an S3 feature it lacks.
