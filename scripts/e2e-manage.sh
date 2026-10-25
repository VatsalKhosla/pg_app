#!/usr/bin/env bash
# Operator commands (python -m app.manage) against the browser tests' API: for tests that need
# what only an operator can do, such as making a staff account. Same settings as
# scripts/e2e-api.sh, so the commands reach the tests' database.
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/e2e-env.sh
source scripts/e2e-env.sh
exec uv run --directory apps/api --locked python -m app.manage "$@"
