#!/usr/bin/env bash
# `make lint-workflows`: check the GitHub Actions workflows for mistakes (actionlint, which also
# runs shellcheck on their scripts) and for security problems (zizmor). With GH_TOKEN set, as in
# CI, zizmor adds its online audits, such as checking that each pinned commit really belongs to
# its action's repository. The images come from the Makefile, pinned by digest.
set -euo pipefail
cd "$(dirname "$0")/.."

docker run --rm --volume "$PWD:/repo:ro" --workdir /repo \
  "${ACTIONLINT_IMAGE:?set by the Makefile}" -color=false

online=(--offline)
if [[ -n "${GH_TOKEN:-}" ]]; then
  online=()
fi
# --env GH_TOKEN passes the token through the environment, never on a command line.
docker run --rm --env GH_TOKEN --volume "$PWD:/repo:ro" --workdir /repo \
  "${ZIZMOR_IMAGE:?set by the Makefile}" "${online[@]}" --persona=pedantic .github/workflows
