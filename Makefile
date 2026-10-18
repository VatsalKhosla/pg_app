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
# Message for `make migration m="..."`.
m ?=

##@ Setup

.PHONY: help
help: ## List the available commands
	@awk 'BEGIN { FS = ":.*## " } \
	    /^##@/ { printf "\n%s\n", substr($$0, 5) } \
	    /^[a-zA-Z0-9_-]+:.*## / { printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

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

##@ Quality

.PHONY: check
check: lint typecheck test-api test-web ## Lint, typecheck and test everything (run before finishing any step)

.PHONY: lint
lint: ## Lint and check formatting and the layer rules (ruff, import-linter, eslint, prettier)
	$(API) ruff check
	$(API) ruff format --check
	$(API) lint-imports
	$(WEB) run lint
	pnpm exec prettier --check .

.PHONY: typecheck
typecheck: ## Type-check everything (mypy --strict, tsc --strict)
	$(API) mypy
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
