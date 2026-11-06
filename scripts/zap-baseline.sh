#!/usr/bin/env bash
# `make zap-baseline url=…`: OWASP ZAP's baseline scan of a deployed site (step 8.1, ADR 0065). It
# spiders the site for a minute and reports what its passive rules see in the responses: headers,
# cookies, leaks. It sends no attacks, so it's safe against the test site.
#
# Fails on any finding, except those .zap/rules.tsv accepts with a reason. The HTML and JSON
# reports land in test-results/zap/. ZAP_DOCKER_ARGS adds arguments to `docker run` (for example
# --add-host where a network's DNS needs help).
set -euo pipefail

url="${1:?usage: $0 <url>}"
out="$(pwd)/test-results/zap"
rm -rf "$out"
mkdir -p "$out"
cp .zap/rules.tsv "$out/rules.tsv"
# ZAP runs as its own user in the container, and writes its reports here.
chmod a+rwx "$out"

# shellcheck disable=SC2086 # ZAP_DOCKER_ARGS is meant to split into arguments
docker run --rm ${ZAP_DOCKER_ARGS:-} \
  --volume "$out:/zap/wrk:rw" \
  "${ZAP_IMAGE:?set by the Makefile}" \
  zap-baseline.py -t "$url" -c rules.tsv -m 1 -r baseline.html -J baseline.json
