#!/usr/bin/env bash
# Checks the developer toolchain. `make setup` runs it first; `make doctor` runs it on its own.
# Node.js is not checked: pnpm downloads the pinned version (package.json devEngines.runtime),
# so a different system Node.js on PATH doesn't matter.
set -euo pipefail

failed=0
ok() { printf '  ok       %s\n' "$1"; }
missing() {
  printf '  MISSING  %s\n           install: %s\n' "$1" "$2"
  failed=1
}

echo "Checking the toolchain:"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  ok "git $(git --version | awk '{print $3}')"
else
  missing "git (run this from inside a clone of the repository)" "https://git-scm.com/downloads"
fi

if command -v uv >/dev/null 2>&1; then
  ok "uv $(uv --version | awk '{print $2}') (installs Python 3.14 for apps/api)"
else
  missing "uv" "https://docs.astral.sh/uv/getting-started/installation/"
fi

if command -v pnpm >/dev/null 2>&1; then
  ok "pnpm $(pnpm --version) (package.json pins the exact pnpm and Node.js versions)"
else
  missing "pnpm" "https://pnpm.io/installation (the standalone version needs no Node.js)"
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  ok "docker $(docker --version | awk '{print $3}' | tr -d ,) with compose $(docker compose version --short)"
else
  missing "docker with compose v2 (runs the local infrastructure for make dev)" "https://docs.docker.com/get-docker/"
fi

exit "$failed"
