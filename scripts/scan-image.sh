#!/usr/bin/env bash
# `make scan-api-image`: scan a local image with Trivy (TRIVY_IMAGE, set by the Makefile). Fails on
# HIGH or CRITICAL vulnerabilities that have a fix, and on secrets baked into the image.
#
# The image goes in as a tar file, so the Trivy container never gets the Docker socket.
set -euo pipefail

image="${1:?usage: $0 <image>}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

docker save --output "$work/image.tar" "$image"
docker run --rm \
  --volume "$work:/scan:ro" \
  --volume pg-platform-trivy-cache:/root/.cache/trivy \
  "${TRIVY_IMAGE:?set by the Makefile}" image \
  --input /scan/image.tar \
  --scanners vuln,secret \
  --severity HIGH,CRITICAL \
  --ignore-unfixed \
  --exit-code 1 \
  --no-progress
