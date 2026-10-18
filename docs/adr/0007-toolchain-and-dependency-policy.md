# ADR 0007: Toolchain pins and dependency supply-chain policy

- Status: accepted
- Date: 2026-10-18
- Build step: 0.1 (monorepo scaffold)

## Context

CLAUDE.md asks for current stable versions pinned in lockfiles, and ARCHITECTURE §17 asks for a defended supply chain. Developer machines differ: the founders use Macs, the first Linux machine already has another Node.js version on its PATH for unrelated work, and CI and Vercel run their own images. Recent npm and PyPI compromises spread through freshly published versions and hijacked maintainer accounts, and were usually caught within days.

## Decision

1. **The repository pins its runtimes, not the machine.**
   - Python 3.14 (`apps/api/.python-version`), installed by uv. uv itself must be at least 0.13.1 (`[tool.uv] required-version`).
   - Node.js 24.22.0 LTS through pnpm's `devEngines.runtime` in the root `package.json`. pnpm downloads it, records its checksum in `pnpm-lock.yaml` and runs every script and `pnpm exec` with it, whatever `node` is on the PATH. `engines.node` says `24.x` for Vercel.
   - pnpm 12.12.0 through `packageManager`. The standalone pnpm build needs no Node.js.
2. **Exact versions** for direct dependencies (`savePrefix: ""` in `pnpm-workspace.yaml`, `==` pins in `apps/api/pyproject.toml`). Lockfiles pin everything else, and `make setup` installs with `--locked` / `--frozen-lockfile`.
3. **A seven-day cooldown** on new releases: pnpm `minimumReleaseAge: 10080` and uv `exclude-newer = "1 week"` (stored in `uv.lock` as a span, so the lock doesn't go stale). Renovate (step 0.7) must use the same minimum age. An urgent security fix may bypass it for one package (`minimumReleaseAgeExclude`, `exclude-newer-package`) after review.
4. **pnpm trust and build gates.** `trustPolicy: no-downgrade` refuses a version published with weaker provenance than earlier ones. `strictDepBuilds` refuses dependency install scripts that haven't been reviewed in `allowBuilds`. Every exception names one exact package or version and the reason, in `pnpm-workspace.yaml`.
5. **Held-back majors.** Revisit when the blockers move; Renovate will propose the upgrades.
   - TypeScript 6.0, not 7.0: typescript-eslint 8 supports TypeScript below 6.1 only.
   - ESLint 9.39, not 10: eslint-plugin-react, eslint-plugin-import and eslint-plugin-jsx-a11y, all used by eslint-config-next, declare ESLint 9 at most, and Next.js 16.4's own template installs ESLint 9. npm marks ESLint 9 as deprecated; we accept that for a development-only tool until the plugins move.
6. **Git hooks run through pre-commit.** Linters are local hooks that run from the lockfiles, so hook versions never drift from `make lint`. Third-party hook repositories are pinned to commit SHAs.

## Consequences

- Any machine with uv, pnpm and git gets identical Python, Node.js and tool versions from `make setup`.
- Upgrades are deliberate: new releases wait a week, and held-back majors wait for their plugin ecosystems.
- Known gap: Next.js 16.4's native compiler needs glibc 2.29 or newer. On older Linux (RHEL or Rocky Linux 8) Turbopack is unavailable and Next.js falls back to WebAssembly bindings, so builds there use `--webpack`: it works, but slower. CI, Vercel and macOS are unaffected.
