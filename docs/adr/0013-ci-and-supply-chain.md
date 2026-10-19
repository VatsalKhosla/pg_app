# ADR 0013: CI and supply-chain security

- Status: accepted
- Date: 2026-10-19
- Build step: 0.7 (CI and security scanning)

## Context

Every change must pass the same checks a developer runs, on a clean machine, before it reaches `main`. The repository is public and will handle money and personal data, so the build itself is an attack surface: third-party actions, scanner downloads, dependency updates and the API's container image. ARCHITECTURE §17 asks for SHA-pinned actions, least-privilege tokens, pip-audit, pnpm audit, CodeQL, gitleaks and Trivy.

## Decision

1. **CI calls `make`.** Each job runs make targets (`lint-api`, `test-web`, `check-client`, `api-breaking`…), so a developer reproduces any check exactly. Lint and typecheck targets are split per app for parallel jobs. Job names are short and stable, because branch protection requires them by name (docs/ci.md).
2. **Workflows are locked down:**
   - Actions are pinned by commit SHA, at releases at least 7 days old.
   - The default token is `contents: read`, and only CodeQL gets `security-events: write`.
   - Checkouts use `persist-credentials: false`, and untrusted values reach scripts through `env`, never through inline expressions.
   - actionlint and zizmor check every workflow. In CI, zizmor also confirms each pinned SHA belongs to its action's repository.
3. **Scanners run as containers pinned by digest** (Trivy, oasdiff, gitleaks, actionlint, zizmor), invoked by the Makefile. That means no third-party scanner actions and no `curl | sh`. Trivy reads the image from a `docker save` tarball, so it never gets the Docker socket.
4. **The checks.** CI covers:
   - lint, types and tests for both apps, with integration tests on real PostGIS and Valkey containers and 10,000 cases per property test;
   - the web build, and Playwright on that build;
   - client staleness, and breaking API changes (oasdiff). The base is the target branch for pull requests, or the previous commit for pushes, so `main` is guarded too.

   Security covers:
   - CodeQL for Python, TypeScript and the workflows themselves;
   - gitleaks over the full history;
   - pip-audit and pnpm audit over every locked dependency, development tools included;
   - Trivy on the API image.

   Security also runs weekly, so new advisories surface without a code change.
5. **Audit exceptions are explicit.** An advisory with no fix that our code can't reach is listed with its reason and date (`auditConfig.ignoreGhsas` in pnpm-workspace.yaml), and anything new fails. The first entry is braces ≤ 3.0.3 (GHSA-vfj7-8cjw-p6xm), reachable only through ESLint's own globbing.
6. **The API image** (`apps/api/Dockerfile`) is multi-stage:
   - uv installs the locked dependencies and the app, not editable, into `/opt/venv`, from Python 3.14.8-slim, pinned by digest.
   - The runtime stage runs as an unprivileged user, and its code is owned by root.
   - The base image's pip is removed: it is never used at run time, and its vendored urllib3 and msgpack were Trivy's only findings.
   - `.dockerignore` is an allowlist, so no `.env` or test file can enter the image.
   - One image runs the API, the worker and migrations.
7. **Renovate, not Dependabot.**
   - Dependabot supports pnpm only up to v10 and uv only at v0.11, while this repository uses pnpm 12 and uv 0.13.
   - Renovate supports both, honours the repository's 7-day cooldown (`minimumReleaseAge`), keeps actions and images pinned to digests (including the scanner images in the Makefile, through a custom manager), and groups minor and patch updates weekly.
   - Security fixes skip the cooldown.
   - It needs the free Renovate GitHub App, which only the founders can install.

## Consequences

- A pull request is mergeable only when 13 checks pass, once the founders turn on the ruleset in docs/ci.md. Until then, the checks run on every push but block nothing.
- The weekly scan can turn `main` red without a code change. That is intended: someone reviews the new advisory, then upgrades or records an exception.
- Breaking API changes need deprecation first (expand, then contract), as migrations do.
- Until the Renovate app is installed, pinned versions only change by hand.
