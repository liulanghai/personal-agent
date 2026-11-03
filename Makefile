# Single entry point for local development and CI.
# CI runs exactly `make install check build`; keep targets in sync with AGENTS.md.

UV  := uv run --frozen
GEN := docs/openapi.json sdk/src/schema.d.ts

.PHONY: help install fmt lint typecheck test gen check-gen check build dev

help: ## Show available targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

install: ## Install Python and Node dependencies from lock files
	uv sync --frozen
	npm ci

fmt: ## Auto-format and apply safe lint fixes
	$(UV) ruff format
	$(UV) ruff check --fix

lint: ## Lint and check formatting (no changes)
	$(UV) ruff check
	$(UV) ruff format --check

typecheck: ## Static type checks for backend and frontend
	$(UV) mypy
	npm run typecheck

test: ## Run backend tests with coverage report
	$(UV) pytest -q

gen: ## Regenerate OpenAPI contract and SDK types
	$(UV) python scripts/export_openapi.py
	npx openapi-typescript docs/openapi.json -o sdk/src/schema.d.ts

check-gen: gen ## Fail if generated contract/SDK differ from committed files
	@git diff --exit-code -- $(GEN) || \
		(echo "Generated files are stale: run 'make gen' and commit the result." && exit 1)

check: lint typecheck test check-gen ## Everything required before a PR is merged

build: ## Production build of the web frontend
	npm run build -w frontend

dev: ## Run backend with reload (use `npm run dev` for the frontend)
	$(UV) uvicorn agent.app:create_app --factory --app-dir backend --reload \
		--host 127.0.0.1 --port 8000
