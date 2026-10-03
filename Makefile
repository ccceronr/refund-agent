# Everyday commands (CLAUDE.md "Commands"). Run them from the repo root.
SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND := uv run --project backend
FRONTEND := npm --prefix frontend run
APP_URL ?= http://localhost:8000
# Backend tests use their own database (refunds_test) on the compose Postgres,
# reached on the host port from .env (DB_HOST_PORT).

.PHONY: help install hooks up down reset-db smoke-models check lint typecheck test test-backend test-frontend fmt health evals

help: ## List the commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'

install: ## Install backend and frontend dependencies from the lockfiles
	uv sync --project backend --locked
	npm --prefix frontend ci

hooks: ## Install the pre-commit hooks (ruff, mypy, eslint, prettier, gitleaks)
	$(BACKEND) pre-commit install

up: ## Start db, migrations and the app (http://localhost:8000)
	docker compose up --build

down: ## Stop everything (keeps the database volume)
	docker compose down

reset-db: ## Wipe the local data and reload the demo seed (refused in production)
	docker compose run --rm migrate python -m seed.seed --reset

smoke-models: ## One tiny real call to Jev, Haiku and Sonnet (paid, well under $0.05)
	docker compose run --rm --build app python -m app.agents.smoke

check: lint typecheck test ## Everything CI runs, except the audits and the image build

lint: ## ruff, ruff format --check, eslint, prettier --check
	$(BACKEND) ruff check backend tests
	$(BACKEND) ruff format --check backend tests
	$(FRONTEND) lint
	$(FRONTEND) format:check

typecheck: ## mypy (strict) and tsc
	cd backend && uv run mypy
	$(FRONTEND) typecheck

test: test-backend test-frontend ## pytest + vitest

test-backend: ## pytest against the compose Postgres (needs .env)
	@test -f .env || { echo "Create .env first: cp .env.example .env (then set the passwords)"; exit 1; }
	docker compose up -d --wait db
	set -a && source ./.env && set +a && \
	TEST_DATABASE_ADMIN_URL="postgresql://postgres:$${POSTGRES_PASSWORD}@127.0.0.1:$${DB_HOST_PORT:-54320}/refunds_test" \
	$(BACKEND) pytest

test-frontend: ## vitest
	$(FRONTEND) test

fmt: ## Format and auto-fix (ruff, prettier)
	$(BACKEND) ruff format backend tests
	$(BACKEND) ruff check --fix backend tests
	$(FRONTEND) format

health: ## Ask the running app for its health
	curl -fsS $(APP_URL)/api/health && echo

evals: ## Run the eval set (P8; makes paid model calls)
	$(BACKEND) python evals/run_evals.py
