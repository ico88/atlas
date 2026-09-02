.DEFAULT_GOAL := help
COMPOSE := docker compose
COMPOSE_DEV := docker compose -f docker-compose.yml -f docker-compose.dev.yml
BACKEND := apps/backend

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Install host prerequisites on Ubuntu 24.04 (Docker, Compose, git, make)
	sudo ./infrastructure/scripts/install.sh

.PHONY: env
env: ## Create .env from .env.example if missing
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

.PHONY: up
up: env ## Start the full stack
	$(COMPOSE) up --build

.PHONY: dev
dev: env ## Start the stack with development overrides
	$(COMPOSE_DEV) up --build

.PHONY: node-up
node-up: env ## Start a worker node agent (run on a node host)
	$(COMPOSE) -f docker-compose.node.yml up --build -d

.PHONY: update
update: ## Update the whole stack safely (backup first; keeps settings & data)
	./atlas update

.PHONY: ai-up
ai-up: env ## Start the stack including local AI (Ollama, profile 'ai')
	$(COMPOSE) --profile ai up --build -d

.PHONY: model-update
model-update: ## Pull + activate a model: make model-update MODEL=llama3.3
	./atlas model-update $(MODEL)

.PHONY: model-rollback
model-rollback: ## Roll back to the previous model
	./atlas model-rollback

.PHONY: model-list
model-list: ## List installed models and the active one
	./atlas model-list

.PHONY: down
down: ## Stop the stack
	$(COMPOSE) down

.PHONY: logs
logs: ## Tail service logs
	$(COMPOSE) logs -f

.PHONY: backend-install
backend-install: ## Install backend dev dependencies (in a local venv)
	cd $(BACKEND) && python -m venv .venv && . .venv/bin/activate && \
		pip install -r requirements-dev.txt

.PHONY: test
test: ## Run backend tests
	cd $(BACKEND) && . .venv/bin/activate && pytest

.PHONY: lint
lint: ## Run backend lint + type check
	cd $(BACKEND) && . .venv/bin/activate && ruff check app tests && mypy app

.PHONY: fmt
fmt: ## Auto-fix backend lint issues
	cd $(BACKEND) && . .venv/bin/activate && ruff check --fix app tests

.PHONY: frontend-install
frontend-install: ## Install frontend dependencies
	cd apps/frontend && npm install

.PHONY: frontend-check
frontend-check: ## Typecheck + lint the frontend
	cd apps/frontend && npm run typecheck && npm run lint

.PHONY: migrate
migrate: ## Apply database migrations inside the backend container
	$(COMPOSE) run --rm backend alembic upgrade head
