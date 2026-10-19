#!/usr/bin/env bash
# `make audit`: check every locked dependency, development tools included, against the public
# vulnerability databases. Python goes through pip-audit (PyPI and OSV advisories), JavaScript
# through pnpm audit (GitHub advisories).
#
# A finding fails the audit until someone reviews it: upgrade, or, when no fix exists and the code
# can't reach the flaw, list it with the reason in pnpm-workspace.yaml (auditConfig).
set -euo pipefail
cd "$(dirname "$0")/.."

requirements="$(mktemp)"
trap 'rm -f "$requirements"' EXIT

uv export --directory apps/api --locked --all-groups --no-emit-project --quiet \
  --format requirements-txt --output-file "$requirements"
uv run --directory apps/api --locked pip-audit --strict --require-hashes --disable-pip \
  --requirement "$requirements"

pnpm audit --audit-level moderate
