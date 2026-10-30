# PG booking platform

An online platform for booking verified PG (paying guest) beds in Delhi NCR. Students find PGs on a map, book a visit, reserve a bed with a small refundable token and move in; owners pay a one-time placement fee. The brand lives in `apps/web/src/config/brand.ts` and the API's `BRAND_NAME` only.

| Path | What it holds |
|---|---|
| `apps/api` | FastAPI API and background worker (Python 3.14, uv) |
| `apps/web` | Next.js web app: public site, owner dashboard and ops console |
| `packages/api-client` | Typed API client, generated from the API's OpenAPI schema |
| `infra/` | Local infrastructure (Docker Compose), and Terraform later |
| `docs/` | Product context, architecture, build plan and decision records (ADRs) |

## Getting started

You need [uv](https://docs.astral.sh/uv/getting-started/installation/), [pnpm](https://pnpm.io/installation) (the standalone version needs no Node.js) and git; Docker from build step 0.2. You don't install Python or Node.js yourself: uv provides Python 3.14 and pnpm provides Node.js 24, the versions pinned in the repository.

```sh
make setup    # check the tools, install dependencies, Playwright's Chromium and the git hooks
make dev      # run the infrastructure, API, worker and web app (http://localhost:3000)
make check    # lint, typecheck and test everything
make e2e      # browser tests against a production build of the web app
make          # list every command
```

## How the work is organised

| File | Purpose |
|---|---|
| `CLAUDE.md` | Loaded by Claude Code every session: the product in brief, the business rules the code enforces, the stack, commands and how to work |
| `docs/PRODUCT_CONTEXT.md` | The business behind the code: fees, dynamic pricing, trust design, leakage, regulation, open decisions. Read it before touching anything about money |
| `docs/ARCHITECTURE.md` | System design, data model, booking state machine, pricing engine, payments and ledger, map, security, scaling, testing |
| `docs/BUILD_PLAN.md` | Phases 0–9 with numbered steps and "done when" checks, plus the founders' own tasks |
| `docs/adr/` | Decision records |
| `docs/ci.md` | What CI and the security scans check, branch protection, and what to do when a check fails |
| `.claude/` | Claude Code settings, the rules that load for matching files, and the `/next-step` and `/phase-review` commands |

Claude Code builds one step at a time with `/next-step` and reviews a finished phase with `/phase-review <n>`. The founders' tasks Claude Code can't do (company, SMS DLT registration, Razorpay KYC, lawyer, CA) are at the top of `docs/BUILD_PLAN.md`; start the slow ones first.
