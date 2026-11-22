.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help message
	@echo "Usage:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sed -E 's/^([^:]*:)?([a-zA-Z_-]+): ## (.*)$$/\2|\3/' | awk -F '|' '{if ($$1 == "help") printf "  \033[36mmake%-16s\033[0m %s\n", "", $$2; else printf "  \033[36mmake %-15s\033[0m %s\n", $$1, $$2}'

.PHONY: compile
compile: ## Compile dependencies to requirements.txt
	uv pip compile pyproject.toml > requirements.txt

.PHONY: install
install: ## Install dependencies
	uv pip install -r requirements.txt

.PHONY: checks
checks: ## Run ruff format check, linting, and tests
	ruff format --check .
	ruff check .
	pytest

.PHONY: format
format: ## Format code with ruff
	ruff format .

.PHONY: test
test: ## Run tests
	pytest

.PHONY: web
web: ## Build the web app into web/dist
	cd web && npm ci && npm run build

.PHONY: web-checks
web-checks: ## Typecheck, lint and test the web app
	cd web && npm run typecheck && npm run lint && npm test

.PHONY: dev
dev: ## Run the API on :8094 as DEV_USER=dragos on ./data (run `npm run dev` in web/ for the UI)
	mkdir -p data/dragos
	DATA_ROOT=data DEV_USER=dragos PYTHONPATH=src uvicorn server.app:create_app --factory --reload --no-proxy-headers --port 8094
