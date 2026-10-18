#!/usr/bin/env bash
# `make dev`: run the API (reloads on code changes), the worker (restarts on code changes) and the
# web app together, with labelled output. Ctrl-C stops all three; the infrastructure keeps running
# (`make infra-down` stops it). Override the ports with API_PORT (8000) and WEB_PORT (3000).
set -euo pipefail
cd "$(dirname "$0")/.."

api_port="${API_PORT:-8000}"
web_port="${WEB_PORT:-3000}"

# Next.js 16's native compiler, which Turbopack needs, requires glibc 2.29 or newer. On older Linux
# (RHEL or Rocky Linux 8) the web app runs on webpack with WebAssembly bindings instead.
# Force a choice with NEXT_BUNDLER=webpack or NEXT_BUNDLER=turbopack.
web_bundler_flag=""
case "${NEXT_BUNDLER:-auto}" in
  webpack) web_bundler_flag="--webpack" ;;
  turbopack) ;;
  auto)
    glibc="$(getconf GNU_LIBC_VERSION 2>/dev/null | awk '{print $2}' || true)"
    if [[ -n "$glibc" && "$(printf '%s\n' "$glibc" 2.29 | sort -V | head -n 1)" != "2.29" ]]; then
      web_bundler_flag="--webpack"
      echo "dev: glibc $glibc is older than 2.29, so the web app runs on webpack instead of Turbopack."
    fi
    ;;
  *)
    echo "dev: NEXT_BUNDLER must be auto, webpack or turbopack" >&2
    exit 2
    ;;
esac

api="uv run --directory apps/api --locked uvicorn app.main:create_app --factory --reload --reload-dir src --host 127.0.0.1 --port $api_port"
worker="uv run --directory apps/api --locked watchfiles --filter python 'python -m app.worker --heartbeat-file .run/worker.heartbeat' src"
web="pnpm --filter @pg-platform/web exec next dev --hostname 127.0.0.1 --port $web_port $web_bundler_flag"

exec pnpm exec concurrently \
  --names api,worker,web \
  --prefix-colors blue,magenta,green \
  --kill-others-on-fail \
  "$api" "$worker" "$web"
