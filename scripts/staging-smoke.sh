#!/usr/bin/env bash
# `make staging-smoke`: does staging answer as a visitor would? The API is ready (it reaches the
# database and the cache), and the home page, search and a PG's page render. Free instances sleep
# when idle, so each page gets three tries of two minutes to wake them (ADR 0047). SITE_URL and
# API_URL default to staging's own.
set -euo pipefail

site="${SITE_URL:-https://fixyourstay.in}"
api="${API_URL:-https://api.fixyourstay.in}"
failed=0
answer=""
# Hosts that never answered: their other pages aren't asked for, so a site that's down fails in
# minutes rather than waiting out every page.
declare -A down=()

# Asks for a page as a visitor's browser would, its body to $2: sets $answer to the HTTP status,
# or "no answer".
fetch() {
  local url="$1" body="$2" host attempt
  host="${url#*://}"
  host="${host%%/*}"
  answer="no answer"
  if [[ -n "${down[$host]:-}" ]]; then
    return
  fi
  for attempt in 1 2 3; do
    # curl says 000 when nothing answered at all.
    answer=$(curl --silent --show-error --location --max-time 120 \
      --output "$body" --write-out '%{http_code}' "$url") || true
    answer="${answer:-000}"
    if [[ "$answer" != 000 && "$answer" != 5* ]]; then
      return
    fi
    if ((attempt < 3)); then
      sleep 10
    fi
  done
  if [[ "$answer" == 000 ]]; then
    answer="no answer"
    down[$host]=1
  fi
}

check() {
  fetch "$1" /dev/null
  if [[ "$answer" == 200 ]]; then
    echo "ok    $1"
  else
    echo "FAIL  $1: $answer"
    failed=1
  fi
}

check "$api/readyz"
check "$site/"
check "$site/search"

found="$(mktemp)"
trap 'rm -f "$found"' EXIT
fetch "$api/v1/search/properties?limit=1" "$found"
if [[ "$answer" == 200 ]]; then
  slug=$(python3 -c 'import json, sys; items = json.load(sys.stdin)["items"]; print(items[0]["slug"] if items else "")' <"$found")
  if [[ -n "$slug" ]]; then
    check "$site/pg/$slug"
  else
    echo "FAIL  $api/v1/search/properties: no live PG to open"
    failed=1
  fi
else
  echo "FAIL  $api/v1/search/properties: $answer"
  failed=1
fi

exit "$failed"
