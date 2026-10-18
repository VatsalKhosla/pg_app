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

##@ Local development

.PHONY: dev
dev: infra-up ## Run the infrastructure, API, worker and web app together (Ctrl-C stops the apps)
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

##@ Quality

.PHONY: check
check: lint typecheck test-api ## Lint, typecheck and test everything (run before finishing any step)

.PHONY: lint
lint: ## Lint and check formatting (ruff, eslint, prettier)
	$(API) ruff check
	$(API) ruff format --check
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
test-api: ## Run the API tests (pytest)
	$(API) pytest
