#!/usr/bin/env bash
# `make load-test`: the planning load of ARCHITECTURE §18 against a local API (step 8.2, ADR 0066).
#
# - A database of its own (platform_load, dropped and made again) holding the geo data, the six
#   sample PGs (through the services, so quotes and holds work) and 3,000 fictional listings for
#   search and the map.
# - The API on LOAD_API_PORT (8300) with 4 workers, as a production container runs, trusting
#   forwarded addresses so that each simulated visitor comes from an address of its own.
# - k6 (K6_IMAGE) runs each scenario in load/: SCENARIOS, default "reads writes hold-race".
#
# Needs the local infrastructure (make infra-up). Results land in test-results/load/.
set -euo pipefail
cd "$(dirname "$0")/.."

port="${LOAD_API_PORT:-8300}"
database=platform_load
out="$(pwd)/test-results/load"
mkdir -p "$out"
compose=(docker compose -f infra/docker-compose.yml)
api=(uv run --directory apps/api --locked)

"${compose[@]}" exec -T postgres psql -q -U platform -d platform \
  -c "DROP DATABASE IF EXISTS $database WITH (FORCE)" -c "CREATE DATABASE $database"

export APP_ENV=local OTP_SENDER=console PAYMENT_GATEWAY=fake TEXT_SENDER=console
export DATABASE_URL="postgresql+asyncpg://platform:platform@127.0.0.1:5432/$database"
# A cache of its own, so nothing cached elsewhere answers for it, and nothing it caches lingers.
export REDIS_URL="redis://:platform@127.0.0.1:6379/9"
SECRET_KEY="$(head -c 48 /dev/urandom | base64 | tr -d '\n=+/')"
export SECRET_KEY
export SITE_URL=http://localhost:3000 API_URL="http://localhost:$port"
# The local object storage (SeaweedFS) and its dummy keys, as in the committed example: the samples'
# photos go there.
set -a
# shellcheck disable=SC1090 # the example file's storage lines, nothing else
source <(grep -E '^(S3_|MEDIA_)' apps/api/.env.example)
set +a

"${api[@]}" alembic upgrade head >/dev/null
"${api[@]}" python -m app.manage geo load >/dev/null
"${api[@]}" python -m app.manage catalog samples >/dev/null
"${api[@]}" python -m app.manage flags set remote_booking_enabled true >/dev/null
"${api[@]}" python -m tests.load.seed 3000
"${compose[@]}" exec -T valkey valkey-cli -a platform -n 9 FLUSHDB >/dev/null 2>&1 || true

log="$out/api.log"
# Process groups of their own, so stopping them stops every process. The job worker keeps search
# up to date (the samples reach it through their jobs) and does what the scenarios ask of it.
setsid "${api[@]}" uvicorn app.main:create_app --factory --workers 4 --host 127.0.0.1 \
  --port "$port" --proxy-headers --forwarded-allow-ips '*' --no-access-log >"$log" 2>&1 &
server=$!
setsid "${api[@]}" python -m app.worker >"$out/worker.log" 2>&1 &
worker=$!
trap 'kill -TERM -- "-$server" "-$worker" 2>/dev/null || true' EXIT
for _ in $(seq 120); do
  curl --fail --silent "http://127.0.0.1:$port/readyz" >/dev/null && break
  sleep 1
done
curl --fail --silent "http://127.0.0.1:$port/readyz" >/dev/null || {
  echo "load-test: the API didn't start; see $log" >&2
  exit 1
}

# The six samples in search, once the worker has run their jobs.
samples() {
  curl --silent "http://127.0.0.1:$port/v1/search/properties?q=fictional%20sample&limit=10" |
    grep -o '"slug"' | wc -l
}
for _ in $(seq 120); do
  [ "$(samples)" -ge 6 ] && break
  sleep 1
done
[ "$(samples)" -ge 6 ] || {
  echo "load-test: the samples never reached search; see $out/worker.log" >&2
  exit 1
}

failed=0
for scenario in ${SCENARIOS:-reads writes hold-race}; do
  echo "== $scenario"
  docker run --rm --network host --user "$(id -u):$(id -g)" \
    --volume "$(pwd)/load:/load:ro" --volume "$out:/out" \
    --env API="http://127.0.0.1:$port" --env DURATION="${DURATION:-2m}" \
    --env READS_PER_SECOND="${READS_PER_SECOND:-300}" --env WRITES_PER_SECOND="${WRITES_PER_SECOND:-20}" \
    --env STUDENTS="${STUDENTS:-50}" \
    "${K6_IMAGE:?set by the Makefile}" run --quiet \
    --summary-export "/out/$scenario.json" "/load/$scenario.js" || failed=1
done
exit "$failed"
