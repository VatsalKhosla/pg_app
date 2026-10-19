#!/usr/bin/env bash
# `make gen-client`: export the API's OpenAPI schema (without starting the API) and regenerate the
# typed client in packages/api-client from it.
# `make check-client` (--check): generate into a temporary directory instead and fail if the
# committed files differ, so a changed API can't ship with a stale client.
set -euo pipefail
cd "$(dirname "$0")/.."

client="$PWD/packages/api-client"
case "${1:-}" in
  "") out="$client" ;;
  --check)
    out="$(mktemp -d)"
    trap 'rm -rf "$out"' EXIT
    ;;
  *)
    echo "usage: $0 [--check]" >&2
    exit 2
    ;;
esac
mkdir -p "$out/src/generated"

uv run --directory apps/api --locked python -m app.openapi "$out/openapi.json"
# --immutable: responses come back as readonly types.
pnpm --filter @pg-platform/api-client exec openapi-typescript "$out/openapi.json" \
  --immutable --output "$out/src/generated/schema.ts"

if [[ "$out" != "$client" ]]; then
  stale=0
  for file in openapi.json src/generated/schema.ts; do
    if ! diff -u "$client/$file" "$out/$file"; then
      stale=1
    fi
  done
  if ((stale)); then
    echo "check-client: the API client is out of date with the API; run 'make gen-client'." >&2
    exit 1
  fi
  echo "check-client: the API client matches the API."
fi
