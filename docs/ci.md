# CI, security scanning and branch protection

Two GitHub Actions workflows guard `main`. Every job runs `make` targets, so anything CI checks can be run locally first. Decisions and reasons are in ADR 0013.

## What runs

**CI** (`.github/workflows/ci.yml`) runs on every pull request and every push to `main`.

| Check | What it does | Locally |
|---|---|---|
| API | ruff, import-linter, mypy, then all API tests. Integration tests run on PostGIS and Valkey containers, and property tests run 10,000 cases each. | `make lint-api typecheck-api test-api` |
| Web | eslint, prettier, tsc, Vitest, then a production build | `make lint-web typecheck-web test-web web-build` |
| Browser tests | Playwright on a production build and the real API (on its own database, from `scripts/e2e-api.sh`), on phone and desktop. Any console error or CSP violation fails a test. | `make e2e` (needs Docker) |
| API client | The committed `packages/api-client` matches the API | `make check-client` |
| API contract | No breaking schema change since the target branch, or since the previous commit on `main` (oasdiff) | `make api-breaking BASE=origin/main` |
| Workflows | actionlint, and zizmor's security audits of the workflows | `make lint-workflows` |
| Pre-commit hooks | Whitespace, line endings, YAML/TOML, merge markers, large files | `pre-commit run --all-files` |
| Deploy staging | Pushes to `main` only, once every check above passes: builds the API and web images, publishes them to GitHub's container registry, and deploys them to Render (ADR 0047, [the staging runbook](runbooks/staging.md)) | `make api-image web-image` |

**Security** (`.github/workflows/security.yml`) runs on every pull request, every push to `main`, and every Monday at 08:47 IST.

| Check | What it does | Locally |
|---|---|---|
| CodeQL (actions, javascript-typescript, python) | Static analysis with the security-extended queries. Results appear under Security → Code scanning. | n/a |
| Secrets | The whole git history, scanned with gitleaks | `make secrets-scan` |
| Dependencies | Every locked dependency checked with pip-audit and pnpm audit | `make audit` |
| API image | Builds the API image and scans it with Trivy. Fixable HIGH and CRITICAL vulnerabilities, and any baked-in secret, fail the check. | `make scan-api-image` |

Actions are pinned by commit SHA, with the tag in a comment. Scanner images are pinned by digest in the `Makefile`. The workflow token is read-only, and only CodeQL may write security events.

## Branch protection (founders: set this up once)

In GitHub, go to **Settings → Rules → Rulesets → New branch ruleset** and create a ruleset for the default branch (`main`):

1. **Enforcement:** Active.
2. **Restrict deletions** and **Block force pushes**.
3. **Require a pull request before merging:**
   - Require at least one approval. With two founders, each reviews the other's (and Claude Code's) changes.
   - Dismiss stale approvals when new commits are pushed.
   - Require conversation resolution.
4. **Require status checks to pass** and **Require branches to be up to date before merging.** The required checks, by name, are:
   - From CI: `API`, `Web`, `Browser tests`, `API client`, `API contract`, `Workflows`, `Pre-commit hooks`.
   - From Security: `CodeQL (actions)`, `CodeQL (javascript-typescript)`, `CodeQL (python)`, `Secrets`, `Dependencies`, `API image`.
5. **Require linear history:** squash or rebase merges only.
6. **Require code scanning results:** CodeQL, with security alerts at High or higher blocking.

Also, under **Settings → Code security**, turn on:
- secret scanning and push protection (free for public repositories);
- Dependabot alerts. They feed Renovate's security pull requests, but Renovate, not Dependabot, makes the update pull requests.

Once the ruleset is active, changes reach `main` only through pull requests.

## Dependency updates (Renovate)

Renovate's configuration is `.github/renovate.json5`. It does nothing until a founder installs the free [Renovate GitHub App](https://github.com/apps/renovate) on this repository and merges its onboarding pull request. After that:
- **Schedule:** Monday mornings (IST). Minor and patch updates are grouped per ecosystem, and majors arrive alone.
- **Cooldown:** a release must be 7 days old, the repository's own cooldown (ADR 0007). Security fixes skip both the schedule and the cooldown.
- **What it pins:** GitHub Actions and container images stay pinned to digests, including the scanner images in the `Makefile`, through the annotated lines.

## When a check fails

- **API client:** run `make gen-client` and commit the result with the API change.
- **API contract:** the schema has a breaking change, such as a removed endpoint or field, or a new required input. Keep changes additive. To retire something, mark it deprecated (`deprecated=True` on the route or field), ship that, and remove it in a later release. This is the same expand-then-contract rule as migrations.
  - A change that is meant and safe for our only client, such as a rename with the same shape or an enum value the web app is regenerated for, goes in `docs/api-contract-exceptions.md` in the same commit, with the date and why. The check ignores exactly the changes listed there.
- **Dependencies:** an advisory affects a locked package.
  - Upgrade it if a fix exists.
  - If no fix exists and our code can't reach the flaw, record the advisory with the reason and date: `auditConfig.ignoreGhsas` in `pnpm-workspace.yaml` for JavaScript, an `--ignore-vuln` flag in `scripts/audit.sh` for Python. Review it again when a fix ships.
- **API image:** usually a base-image fix; update the pinned digest in `apps/api/Dockerfile` (Renovate does this weekly).
- **Secrets:** treat the secret as leaked. Rotate it first, then remove it from history with the founders.
- **Browser tests:** the run keeps its Playwright report, traces and the test API's log (`.e2e-api.log`) as a `playwright-report` artifact for 14 days.
