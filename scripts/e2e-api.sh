#!/usr/bin/env bash
# The API for the browser tests, started by apps/web/playwright.config.ts (`make e2e`), with the
# worker that prepares uploaded photos beside it.
#
# It runs against the local infrastructure (started here if it isn't up) but never touches
# development data: its settings (scripts/e2e-env.sh) name a database, a Valkey database and
# buckets of its own, migrated, loaded and made here. Sign-in codes go to the log as JSON (the
# console sender); the tests read them from E2E_API_LOG.
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/e2e-env.sh
source scripts/e2e-env.sh

log="${E2E_API_LOG:-$PWD/apps/web/.e2e-api.log}"
worker_log="${E2E_WORKER_LOG:-$(dirname "$log")/.e2e-worker.log}"
compose=(docker compose --file infra/docker-compose.yml)

"${compose[@]}" up --detach --build --wait postgres valkey s3 >&2
if ! "${compose[@]}" exec -T postgres psql --username=platform --dbname=platform --tuples-only \
  --command="SELECT 1 FROM pg_database WHERE datname = '$database'" | grep -q 1; then
  "${compose[@]}" exec -T postgres createdb --username=platform "$database"
fi

api=(uv run --directory apps/api --locked)
"${api[@]}" alembic upgrade head >&2
"${api[@]}" python -m app.manage geo load >&2
"${api[@]}" python -m app.manage media buckets >&2

mkdir -p "$(dirname "$log")"
"${api[@]}" python -m app.worker >"$worker_log" 2>&1 &
worker=$!
# The worker stops with the API, however the API stops.
trap 'kill "$worker" 2>/dev/null || true' EXIT
"${api[@]}" uvicorn app.main:create_app --factory \
  --host 127.0.0.1 --port "$api_port" --no-access-log >"$log" 2>&1
