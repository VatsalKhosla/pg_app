#!/usr/bin/env bash
# The API for the browser tests, started by apps/web/playwright.config.ts (`make e2e`).
#
# It runs against the local infrastructure (started here if it isn't up) but never touches
# development data: its own database (platform_e2e, migrated here) and its own Valkey database (1).
# Every setting that matters is set below, so a developer's apps/api/.env can't change the tests.
# Sign-in codes go to the log as JSON (the console sender); the tests read them from E2E_API_LOG.
set -euo pipefail
cd "$(dirname "$0")/.."

api_port="${E2E_API_PORT:-8100}"
web_port="${E2E_PORT:-3100}"
log="${E2E_API_LOG:-$PWD/apps/web/.e2e-api.log}"
database=platform_e2e
compose=(docker compose --file infra/docker-compose.yml)

"${compose[@]}" up --detach --build --wait postgres valkey >&2
if ! "${compose[@]}" exec -T postgres psql --username=platform --dbname=platform --tuples-only \
  --command="SELECT 1 FROM pg_database WHERE datname = '$database'" | grep -q 1; then
  "${compose[@]}" exec -T postgres createdb --username=platform "$database"
fi

export APP_ENV=local
export LOG_LEVEL=INFO
export LOG_FORMAT=json
export DATABASE_URL="postgresql+asyncpg://platform:platform@127.0.0.1:${POSTGRES_PORT:-5432}/$database"
export REDIS_URL="redis://:platform@127.0.0.1:${VALKEY_PORT:-6379}/1"
export SECRET_KEY="e2e-only-secret-key-0123456789abcdef"
export SITE_URL="http://127.0.0.1:$web_port"
export API_URL="http://127.0.0.1:$api_port"
export CORS_ALLOWED_ORIGINS="$SITE_URL"
export SESSION_COOKIE_DOMAIN=
export OTP_SENDER=console
export TURNSTILE_SECRET_KEY=
export GOOGLE_CLIENT_ID=
export GOOGLE_CLIENT_SECRET=
export STAFF_GOOGLE_DOMAINS=
export STAFF_GOOGLE_EMAILS=
export PRIVACY_NOTICE_VERSION=draft-1
export SENTRY_DSN=
export OTEL_EXPORTER_OTLP_ENDPOINT=

uv run --directory apps/api --locked alembic upgrade head >&2
mkdir -p "$(dirname "$log")"
exec uv run --directory apps/api --locked uvicorn app.main:create_app --factory \
  --host 127.0.0.1 --port "$api_port" --no-access-log >"$log" 2>&1
