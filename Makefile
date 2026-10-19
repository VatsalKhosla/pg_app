# One entry point for every developer command (CLAUDE.md). Run `make` to list them.
#
# Python tools run from apps/api's uv lockfile and JavaScript tools from pnpm-lock.yaml, so every
# machine and CI use exactly the same versions. Commands are added by the build step that needs them.

SHELL := bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help
.DELETE_ON_ERROR:
MAKEFLAGS += --warn-undefined-variables --no-builtin-rules --no-print-directory

API_DIR := apps/api
API := uv run --directory $(API_DIR) --locked
WEB := pnpm --filter @pg-platform/web
COMPOSE := docker compose -f infra/docker-compose.yml
API_IMAGE ?= pg-platform/api:local
# Git ref that `make api-breaking` compares the API schema against.
BASE ?= origin/main
# Message for `make migration m="..."`.
m ?=

# Scanner images, pinned by tag and digest; Renovate updates the annotated lines.
# renovate: datasource=docker depName=aquasec/trivy
TRIVY_IMAGE := aquasec/trivy:0.75.0@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa
# renovate: datasource=docker depName=tufin/oasdiff
OASDIFF_IMAGE := tufin/oasdiff:v1.33.0@sha256:6263a96dd2ef0726c54e21fea9b8e1607eac4841add0079324b424c1f52b819c
# renovate: datasource=docker depName=ghcr.io/gitleaks/gitleaks
GITLEAKS_IMAGE := ghcr.io/gitleaks/gitleaks:v8.30.1@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f
# renovate: datasource=docker depName=rhysd/actionlint
ACTIONLINT_IMAGE := rhysd/actionlint:1.7.12@sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667
# renovate: datasource=docker depName=ghcr.io/zizmorcore/zizmor
ZIZMOR_IMAGE := ghcr.io/zizmorcore/zizmor:1.30.1@sha256:a2eb396d886c053073405c7a980f2139ba2248ec172243cfa3841e57196e8101
export TRIVY_IMAGE OASDIFF_IMAGE ACTIONLINT_IMAGE ZIZMOR_IMAGE

##@ Setup

.PHONY: help
help: ## List the available commands
	@awk 'BEGIN { FS = ":.*## " } \
	    /^##@/ { printf "\n%s\n", substr($$0, 5) } \
	    /^[a-zA-Z0-9_-]+:.*## / { printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

.PHONY: doctor
doctor: ## Check that the required tools are installed
	@scripts/doctor.sh

.PHONY: setup
setup: doctor ## Install all dependencies and the git hooks
	uv sync --directory $(API_DIR) --locked
	pnpm install --frozen-lockfile
	uv run --project $(API_DIR) --locked pre-commit install --install-hooks
	$(WEB) exec playwright install chromium
	@scripts/env-sync.sh

.PHONY: env
env: ## Create apps/api/.env, or add settings that .env.example gained since
	@scripts/env-sync.sh

##@ Local development

.PHONY: dev
dev: env infra-up migrate ## Run the infrastructure, API, worker and web app together (Ctrl-C stops the apps)
	@scripts/dev.sh

.PHONY: infra-up
infra-up: ## Start PostgreSQL, Valkey, S3 and Mailpit and wait until they are healthy
	$(COMPOSE) up --detach --build --wait

.PHONY: infra-down
infra-down: ## Stop the infrastructure (local data is kept)
	$(COMPOSE) down

.PHONY: infra-reset
infra-reset: ## Stop the infrastructure and delete all its local data
	$(COMPOSE) down --volumes

.PHONY: health
health: ## Check that every local service is up
	@scripts/dev-health.sh

##@ Database

.PHONY: migrate
migrate: env ## Apply all database migrations (alembic upgrade head)
	$(API) alembic upgrade head

.PHONY: migration
migration: ## Generate a migration from model changes: make migration m="add bookings" (review it!)
	@[ -n "$(m)" ] || { echo 'usage: make migration m="what changed"' >&2; exit 2; }
	$(API) alembic revision --autogenerate -m "$(m)"

##@ API client

.PHONY: gen-client
gen-client: ## Export the API's OpenAPI schema and regenerate packages/api-client from it
	@scripts/gen-client.sh

.PHONY: check-client
check-client: ## Fail if packages/api-client is out of date with the API
	@scripts/gen-client.sh --check

##@ Quality

.PHONY: check
check: lint typecheck test-api test-web check-client ## Lint, typecheck, test everything and check the API client is current (run before finishing any step)

.PHONY: lint
lint: lint-api lint-web ## Lint and check formatting and the layer rules (ruff, import-linter, eslint, prettier)

.PHONY: lint-api
lint-api: ## Lint the API (ruff, import-linter)
	$(API) ruff check
	$(API) ruff format --check
	$(API) lint-imports

.PHONY: lint-web
lint-web: ## Lint the web app and check formatting everywhere Prettier applies (eslint, prettier)
	$(WEB) run lint
	pnpm exec prettier --check .

.PHONY: lint-workflows
lint-workflows: ## Check the GitHub Actions workflows for mistakes and security problems (actionlint, zizmor)
	@scripts/lint-workflows.sh

.PHONY: typecheck
typecheck: typecheck-api typecheck-web ## Type-check everything (mypy --strict, tsc --strict)

.PHONY: typecheck-api
typecheck-api: ## Type-check the API (mypy --strict)
	$(API) mypy

.PHONY: typecheck-web
typecheck-web: ## Type-check the web app and the API client (tsc --strict)
	pnpm --recursive run typecheck

.PHONY: fmt
fmt: ## Auto-fix lint findings and format all code
	$(API) ruff check --fix
	$(API) ruff format
	$(WEB) exec eslint --fix .
	pnpm exec prettier --write .

##@ Tests

.PHONY: test-api
test-api: ## Run all API tests, unit and integration (integration tests need Docker)
	$(API) pytest

.PHONY: test-api-unit
test-api-unit: ## Run the API unit tests only (no Docker needed)
	$(API) pytest -m "not integration"

.PHONY: test-web
test-web: ## Run the web unit and component tests (Vitest)
	$(WEB) run test

.PHONY: e2e
e2e: web-build ## Run the browser tests against a production build (Playwright)
	$(WEB) run e2e

.PHONY: lighthouse
lighthouse: web-build ## Audit the home page with Lighthouse (mobile); fails below 90
	$(WEB) run lighthouse

##@ Build

.PHONY: web-build
web-build: ## Build the web app for production
	$(WEB) exec next build $$(scripts/next-bundler-flag.sh)

.PHONY: api-image
api-image: ## Build the API and worker image (API_IMAGE, default pg-platform/api:local)
	docker build --tag $(API_IMAGE) $(API_DIR)

##@ Security

.PHONY: audit
audit: ## Check every locked dependency for known vulnerabilities (pip-audit, pnpm audit)
	@scripts/audit.sh

.PHONY: secrets-scan
secrets-scan: ## Scan the whole git history for committed secrets (gitleaks)
	docker run --rm --volume "$(CURDIR):/repo:ro" $(GITLEAKS_IMAGE) git --no-banner --redact /repo

.PHONY: scan-api-image
scan-api-image: api-image ## Scan the API image for fixable HIGH and CRITICAL vulnerabilities (Trivy)
	@scripts/scan-image.sh $(API_IMAGE)

.PHONY: api-breaking
api-breaking: ## Fail on breaking changes to the API schema since BASE (default origin/main; oasdiff)
	@scripts/api-breaking.sh $(BASE)
