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

##@ Setup

.PHONY: help
help: ## List the available commands
	@awk 'BEGIN { FS = ":.*## " } \
	    /^##@/ { printf "\n%s\n", substr($$0, 5) } \
	    /^[a-zA-Z0-9_-]+:.*## / { printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

.PHONY: doctor
doctor: ## Check that the required tools are installed
	@scripts/doctor.sh

.PHONY: setup
setup: doctor ## Install all dependencies and the git hooks
	uv sync --directory $(API_DIR) --locked
	pnpm install --frozen-lockfile
	uv run --project $(API_DIR) --locked pre-commit install --install-hooks

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
