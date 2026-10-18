#!/usr/bin/env bash
# `make health`: check every local service and exit non-zero if any is down.
set -uo pipefail
cd "$(dirname "$0")/.."

api_port="${API_PORT:-8000}"
web_port="${WEB_PORT:-3000}"
compose=(docker compose -f infra/docker-compose.yml)
status=0
ok() { printf '  ok    %s\n' "$1"; }
down() {
  printf '  DOWN  %s\n' "$1"
  status=1
}

echo "Infrastructure (make infra-up):"
for service in postgres valkey s3 mailpit; do
  health="$("${compose[@]}" ps --format '{{.Health}}' "$service" 2>/dev/null || true)"
  if [[ "$health" == "healthy" ]]; then ok "$service"; else down "$service (${health:-not running})"; fi
done

# Creating the extensions inside a rolled-back transaction proves they are installed without
# changing the database (step 0.3's first migration creates them for real).
extensions=(postgis btree_gist pg_trgm citext)
sql="BEGIN;"
for extension in "${extensions[@]}"; do sql+=" CREATE EXTENSION IF NOT EXISTS $extension;"; done
sql+=" ROLLBACK;"
if "${compose[@]}" exec -T postgres psql -U platform -d platform -v ON_ERROR_STOP=1 -qc "$sql" >/dev/null 2>&1; then
  ok "postgres extensions: ${extensions[*]}"
else
  down "postgres extensions: ${extensions[*]}"
fi

echo "Apps (make dev):"
if curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:$api_port/healthz" 2>/dev/null; then
  ok "api     http://127.0.0.1:$api_port/docs"
else
  down "api     http://127.0.0.1:$api_port/healthz"
fi
heartbeat=apps/api/.run/worker.heartbeat
if [[ -n "$(find "$heartbeat" -mmin -1 2>/dev/null)" ]]; then
  ok "worker  heartbeat less than a minute old"
else
  down "worker  no heartbeat in the last minute ($heartbeat)"
fi
# The first request compiles the page, which takes a while on webpack.
if curl -fsS --max-time 120 -o /dev/null "http://127.0.0.1:$web_port/" 2>/dev/null; then
  ok "web     http://127.0.0.1:$web_port"
else
  down "web     http://127.0.0.1:$web_port"
fi

echo "Emails the app sends: http://127.0.0.1:${MAILPIT_UI_PORT:-8025}"
exit "$status"
