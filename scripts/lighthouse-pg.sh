#!/usr/bin/env bash
# `make lighthouse-pg`: Lighthouse's mobile audit of a fictional sample PG's page, which must score
# at least 85 in every category (BUILD_PLAN 3.4); `make lighthouse-search` audits search's list
# (LIGHTHOUSE_PATH, LIGHTHOUSE_REPORT). The pages need the API, so this starts the browser tests'
# API (scripts/e2e-api.sh: a database and buckets of its own), adds the sample PGs to it
# (python -m app.manage catalog samples), and points the production build's server at it.
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/e2e-env.sh
source scripts/e2e-env.sh

api_port="${E2E_API_PORT:-8100}"
log="$(mktemp -t lighthouse-api.XXXXXX)"
# A process group of its own, so stopping it stops the API and its worker too.
E2E_API_LOG="$log" setsid scripts/e2e-api.sh >/dev/null 2>&1 &
api=$!
trap 'kill -TERM -- "-$api" 2>/dev/null || true; rm -f "$log"' EXIT

for _ in $(seq 180); do
  curl --fail --silent "http://127.0.0.1:$api_port/healthz" >/dev/null && break
  sleep 1
done
curl --fail --silent "http://127.0.0.1:$api_port/healthz" >/dev/null || {
  echo "lighthouse-pg: the API didn't start; its log: $log" >&2
  exit 1
}
scripts/e2e-manage.sh catalog samples

API_URL="http://127.0.0.1:$api_port" \
  LIGHTHOUSE_PATH="${LIGHTHOUSE_PATH:-/pg/fictional-sample-pg-aster-kamla-nagar}" \
  LIGHTHOUSE_MIN_SCORE=0.85 \
  LIGHTHOUSE_REPORT="${LIGHTHOUSE_REPORT:-pg}" \
  pnpm --filter @pg-platform/web run lighthouse
