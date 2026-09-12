# smart-job-apply — developer tasks.
#
# Written for Linux and macOS (GNU make + POSIX shell). On Windows either use
# WSL, or run the PowerShell equivalent listed next to each target:
#
#   make install        ->  .\scripts\setup.ps1
#   make dev-backend    ->  .venv\Scripts\python -m uvicorn app.main:app --reload
#                             --app-dir backend --port 8000
#   make dev-frontend   ->  cd frontend; npm run dev
#   make dev            ->  run the two commands above in two terminals
#   make build          ->  cd frontend; npm run build
#   make demo           ->  .venv\Scripts\python scripts\demo_server.py --fresh
#   make seed           ->  .venv\Scripts\python scripts\seed_mock.py --fresh
#   make seed-demo      ->  .venv\Scripts\python scripts\seed_demo.py
#   make seed-demo n=10 ->  ... --applications 10
#   make test           ->  .venv\Scripts\python -m pytest
#   make e2e            ->  .venv\Scripts\python -m pytest -m e2e
#   make e2e-frontend   ->  cd frontend; npm run e2e
#   make lint           ->  .venv\Scripts\python -m ruff check .
#   make format         ->  .venv\Scripts\python -m ruff format .;
#                           .venv\Scripts\python -m ruff check . --fix
#   make typecheck      ->  .venv\Scripts\python -m mypy backend/app
#   make migrate        ->  cd backend; ..\.venv\Scripts\alembic upgrade head
#   make migration m=.. ->  cd backend; ..\.venv\Scripts\alembic revision
#                             --autogenerate -m "..."
#   make user           ->  .venv\Scripts\python scripts\create_user.py
#   make admin          ->  .venv\Scripts\python scripts\create_admin.py
#   make docker-*       ->  the same docker compose commands, unchanged
#   make clean          ->  Remove-Item -Recurse -Force .venv, frontend\node_modules,
#                             frontend\dist, .pytest_cache, .ruff_cache, .mypy_cache

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

VENV        := .venv
PY          := $(VENV)/bin/python
PIP         := $(VENV)/bin/pip
ALEMBIC     := $(abspath $(VENV))/bin/alembic
BACKEND_DIR := backend
FRONTEND_DIR:= frontend
BACKEND_PORT ?= 8000

.DEFAULT_GOAL := help
.PHONY: help install dev dev-backend dev-frontend build demo seed seed-demo \
        test e2e e2e-frontend test-all lint format typecheck check-api-types \
        migrate migration \
        user admin docker-build docker-up docker-down docker-logs clean

help: ## Show this help
	@printf 'smart-job-apply — available targets\n\n'
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "} {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@printf '\nFirst run:  make install  &&  make migrate  &&  make user  &&  make dev\n'

install: ## Create the venv, install backend + frontend deps, write .env
	@bash scripts/setup.sh

dev: ## Run backend and frontend together (Ctrl-C stops both)
	@bash scripts/dev.sh

dev-backend: ## Run only the API with autoreload
	$(PY) -m uvicorn app.main:app --reload --app-dir $(BACKEND_DIR) \
		--host 127.0.0.1 --port $(BACKEND_PORT)

dev-frontend: ## Run only the Vite dev server
	cd $(FRONTEND_DIR) && npm run dev

build: ## Build the frontend into frontend/dist
	cd $(FRONTEND_DIR) && npm run build

demo: ## Run the app self-contained: offline AI, fake job portal, seeded account
	@printf 'Backend on :8000 with DEMO_PORTAL and the offline AI provider.\n'
	@printf 'Run `make dev-frontend` in another terminal, then open :5173.\n\n'
	$(PY) scripts/demo_server.py --fresh

seed: ## Fill the demo database with believable data (admin@admin.com / 123)
	$(PY) scripts/seed_mock.py --fresh

# Narrower than `seed` on purpose, and overlapping with it: `seed` fills every
# screen with a broad history, while this seeds one candidate against postings
# chosen to pull their resume in five different directions, then prints what
# each adaptation emphasised. That printout is the point — it makes "five
# vacancies, five different resumes" checkable from a terminal. Shares its
# dataset with the test suite (`app/demo.py`), so the two cannot drift.
seed-demo: ## Seed one candidate and N per-application resumes (make seed-demo n=10)
	$(PY) scripts/seed_demo.py $(if $(n),--applications $(n),)

test: ## Run the test suite (the browser tests are opt-in; see e2e)
	$(PY) -m pytest

e2e: ## Run the browser tests: real Chromium against the bundled fake portal
	$(PY) -m playwright install chromium
	$(PY) -m pytest -m e2e

e2e-frontend: ## Run the Playwright dashboard tests against a demo backend
	cd $(FRONTEND_DIR) && npm run e2e:install && npm run e2e

test-all: ## Everything: unit, browser, and the frontend suites
	$(PY) -m pytest -m 'not e2e'
	$(PY) -m pytest -m e2e
	cd $(FRONTEND_DIR) && npm run test -- --run && npm run e2e

lint: ## Check style and imports without changing files
	$(PY) -m ruff check .

format: ## Format the code and apply safe lint fixes
	$(PY) -m ruff format .
	$(PY) -m ruff check . --fix

typecheck: ## Run mypy over the backend package
	$(PY) -m mypy $(BACKEND_DIR)/app

check-api-types: ## Verify the hand-written TS types still mirror the API
	$(PY) tools/check_api_types.py

migrate: ## Apply all pending database migrations
	cd $(BACKEND_DIR) && $(ALEMBIC) upgrade head

migration: ## Autogenerate a migration from the models (usage: make migration m="add x")
	@if [ -z "$(m)" ]; then \
		echo 'Missing message. Usage: make migration m="add job score index"'; \
		exit 1; \
	fi
	cd $(BACKEND_DIR) && $(ALEMBIC) revision --autogenerate -m "$(m)"

user: ## Create an application account (prompts for the password)
	$(PY) scripts/create_user.py

admin: ## Create or promote the /admin account (reads ADMIN_EMAIL, else prompts)
	$(PY) scripts/create_admin.py

docker-build: ## Build the Docker image
	docker compose build

docker-up: ## Start the container in the background
	docker compose up -d
	@printf 'app:          http://localhost:8000\n'
	@printf 'browser view: http://localhost:6080  (log in to LinkedIn here)\n'

docker-down: ## Stop the container (the data volume is kept)
	docker compose down

docker-logs: ## Follow the container logs
	docker compose logs -f

clean: ## Remove build artefacts, caches, venv and node_modules (keeps backend/data)
	rm -rf $(VENV) $(FRONTEND_DIR)/node_modules $(FRONTEND_DIR)/dist \
		.pytest_cache .ruff_cache .mypy_cache .coverage htmlcov \
		build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.py[co]' -delete
