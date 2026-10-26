#!/usr/bin/env bash
# `make api-breaking BASE=<git ref>`: fail if the API's schema (packages/api-client/openapi.json)
# has breaking changes since BASE: removed endpoints or fields, new required inputs, narrowed
# types and the like (oasdiff, OASDIFF_IMAGE set by the Makefile). Additive changes pass.
# OASDIFF_FORMAT=githubactions annotates the pull request instead of printing text. Changes that
# were meant, and reviewed as safe, are listed in docs/api-contract-exceptions.md, and only those
# are ignored.
set -euo pipefail
cd "$(dirname "$0")/.."

base="${1:?usage: $0 <git ref>}"
schema=packages/api-client/openapi.json

if ! git cat-file -e "$base:$schema" 2>/dev/null; then
  echo "api-breaking: $base has no $schema; nothing to compare against."
  exit 0
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git show "$base:$schema" >"$work/base.json"
cp "$schema" "$work/head.json"
cp docs/api-contract-exceptions.md "$work/exceptions.md"

docker run --rm --volume "$work:/specs:ro" "${OASDIFF_IMAGE:?set by the Makefile}" \
  breaking /specs/base.json /specs/head.json \
  --fail-on ERR --err-ignore /specs/exceptions.md --format "${OASDIFF_FORMAT:-text}"
echo "api-breaking: no breaking changes since $base."
