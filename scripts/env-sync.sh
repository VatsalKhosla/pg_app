#!/usr/bin/env bash
# Keeps apps/api/.env (git-ignored) in step with apps/api/.env.example: creates it when missing
# (readable only by you) and appends any setting the example has and .env lacks, with the
# example's dummy value. Existing values are never changed or printed. Run by make setup and dev.
set -euo pipefail
cd "$(dirname "$0")/.."
example=apps/api/.env.example
env_file=apps/api/.env
if [[ ! -f "$env_file" ]]; then
  install -m 600 "$example" "$env_file"
  echo "Created $env_file (readable only by you) from .env.example"
  exit 0
fi
added=()
while IFS= read -r line; do
  [[ "$line" =~ ^([A-Z][A-Z0-9_]*)= ]] || continue
  key="${BASH_REMATCH[1]}"
  if ! grep -q "^${key}=" "$env_file"; then
    printf '%s\n' "$line" >>"$env_file"
    added+=("$key")
  fi
done <"$example"
if ((${#added[@]})); then
  echo "Added to $env_file from .env.example: ${added[*]}"
fi
