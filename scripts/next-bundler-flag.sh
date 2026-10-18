#!/usr/bin/env bash
# Print the flag that picks Next.js's bundler on this machine: nothing for Turbopack (the default),
# or --webpack where Turbopack can't run. Next.js 16's native compiler, which Turbopack needs,
# requires glibc 2.29 or newer; on older Linux (RHEL or Rocky Linux 8) webpack with WebAssembly
# bindings works instead. Force a choice with NEXT_BUNDLER=webpack or NEXT_BUNDLER=turbopack.
#
# Used by `make dev`, `make web-build`, `make e2e` and `make lighthouse`.
set -euo pipefail

case "${NEXT_BUNDLER:-auto}" in
  webpack) echo "--webpack" ;;
  turbopack) ;;
  auto)
    glibc="$(getconf GNU_LIBC_VERSION 2>/dev/null | awk '{print $2}' || true)"
    if [[ -n "$glibc" && "$(printf '%s\n' "$glibc" 2.29 | sort -V | head -n 1)" != "2.29" ]]; then
      echo "next: glibc $glibc is older than 2.29, so Next.js uses webpack instead of Turbopack." >&2
      echo "--webpack"
    fi
    ;;
  *)
    echo "next: NEXT_BUNDLER must be auto, webpack or turbopack" >&2
    exit 2
    ;;
esac
