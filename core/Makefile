.PHONY: help install dev build test coverage lint format clean migrate shell logs down up restart

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

help: ## Show this help message
	@echo '${BLUE}Sterna - Available Commands${NC}'
	@echo ''
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make ${GREEN}<target>${NC}\n\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  ${GREEN}%-15s${NC} %s\n", $$1, $$2 } /^##@/ { printf "\n${YELLOW}%s${NC}\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Development

install: ## Install all dependencies (backend + frontend)
	@echo '${BLUE}Installing Python dependencies...${NC}'
	python3 -m venv venv
	./venv/bin/pip install --upgrade pip
	./venv/bin/pip install -r requirements.txt
	@echo '${GREEN}Dependencies installed successfully!${NC}'

dev: ## Start full stack with hot reload (Docker Compose)
	@echo '${BLUE}Starting development environment...${NC}'
	docker compose up -d
	@echo '${GREEN}Development environment is running!${NC}'
	@echo 'API: http://localhost:8000'
	@echo 'Flower (Celery monitoring): http://localhost:5555'

build: ## Production build (all containers)
	@echo '${BLUE}Building production containers...${NC}'
	docker compose build --no-cache
	@echo '${GREEN}Build complete!${NC}'

# sandbox-base MUST build before sandbox-datascience: its Dockerfile does
# `FROM ${BASE_IMAGE:-sandbox-base:latest}`, and `docker compose build` does
# not reliably serialize builds by `depends_on` across versions, so order is
# made explicit below rather than left to compose to infer.
sandbox-build: ## Build the coding-agent sandbox images (orchestrator, egress-proxy, sandbox-base, sandbox-datascience)
	@echo '${BLUE}Building sandbox images...${NC}'
	docker compose -f sandbox/docker-compose.sandbox.yml build sandbox-base
	docker compose -f sandbox/docker-compose.sandbox.yml --profile build-only build
	@echo '${GREEN}Sandbox images built!${NC}'

##@ Database

migrate: ## Run database migrations
	@echo '${BLUE}Running database migrations...${NC}'
	docker compose exec web python manage.py migrate
	@echo '${GREEN}Migrations complete!${NC}'

makemigrations: ## Create new migrations
	@echo '${BLUE}Creating new migrations...${NC}'
	docker compose exec web python manage.py makemigrations
	@echo '${GREEN}Migrations created!${NC}'

createsuperuser: ## Create Django superuser
	@echo '${BLUE}Creating superuser...${NC}'
	docker compose exec web python manage.py createsuperuser

shell: ## Open Django shell
	@echo '${BLUE}Opening Django shell...${NC}'
	docker compose exec web python manage.py shell_plus

dbshell: ## Open database shell
	@echo '${BLUE}Opening database shell...${NC}'
	docker compose exec postgres psql -U postgres sterna_dev

##@ Testing

test: ## Run all tests with coverage
	@echo '${BLUE}Running tests...${NC}'
	docker compose exec web pytest --cov=. --cov-report=term-missing
	@echo '${GREEN}Tests complete!${NC}'

test-fast: ## Run tests without coverage
	@echo '${BLUE}Running tests (fast mode)...${NC}'
	docker compose exec web pytest -x
	@echo '${GREEN}Tests complete!${NC}'

coverage: ## Generate detailed coverage report
	@echo '${BLUE}Generating coverage report...${NC}'
	docker compose exec web pytest --cov=. --cov-report=html
	@echo '${GREEN}Coverage report generated in htmlcov/index.html${NC}'

##@ Load Testing

load-test: ## Run load tests (default profile)
	@echo '${BLUE}Running load tests...${NC}'
	python3 load_testing/run_tests.py --profile load --headless
	@echo '${GREEN}Load tests complete!${NC}'

load-test-smoke: ## Run smoke tests (quick validation)
	@echo '${BLUE}Running smoke tests...${NC}'
	python3 load_testing/run_tests.py --profile smoke --headless
	@echo '${GREEN}Smoke tests complete!${NC}'

load-test-stress: ## Run stress tests (high load)
	@echo '${BLUE}Running stress tests...${NC}'
	python3 load_testing/run_tests.py --profile stress --headless
	@echo '${GREEN}Stress tests complete!${NC}'

load-test-ui: ## Run load tests with web UI
	@echo '${BLUE}Starting Locust web UI...${NC}'
	@echo 'Open browser at http://localhost:8089'
	locust -f load_testing/locustfile.py --host http://localhost:8000

load-test-update-baselines: ## Update performance baselines
	@echo '${BLUE}Updating performance baselines...${NC}'
	python3 load_testing/run_tests.py --profile load --headless --update-baselines
	@echo '${GREEN}Baselines updated!${NC}'

load-test-report: ## Open latest load test report
	@echo '${BLUE}Opening latest report...${NC}'
	@ls -t load_testing/reports/output/*.html 2>/dev/null | head -1 | xargs open 2>/dev/null || \
		ls -t load_testing/reports/output/*.html 2>/dev/null | head -1 | xargs xdg-open 2>/dev/null || \
		echo '${YELLOW}No reports found or unable to open. Check load_testing/reports/output/${NC}'

##@ Code Quality

lint: ## Run ruff + mypy + ESLint
	@echo '${BLUE}Running linters...${NC}'
	@echo 'Running ruff...'
	docker compose exec web ruff check .
	@echo 'Running mypy...'
	docker compose exec web mypy .
	@echo '${GREEN}Linting complete!${NC}'

format: ## Format code with ruff
	@echo '${BLUE}Formatting code...${NC}'
	docker compose exec web ruff format .
	@echo '${GREEN}Code formatted!${NC}'

##@ Docker Management

up: ## Start all containers
	@echo '${BLUE}Starting containers...${NC}'
	docker compose up -d
	@echo '${GREEN}Containers started!${NC}'

down: ## Stop all containers
	@echo '${YELLOW}Stopping containers...${NC}'
	docker compose down
	@echo '${GREEN}Containers stopped!${NC}'

restart: ## Restart all containers
	@echo '${YELLOW}Restarting containers...${NC}'
	docker compose restart
	@echo '${GREEN}Containers restarted!${NC}'

logs: ## Show container logs
	docker compose logs -f

logs-web: ## Show web container logs
	docker compose logs -f web

logs-worker: ## Show worker container logs
	docker compose logs -f worker

ps: ## Show container status
	docker compose ps

##@ Celery

worker: ## Start Celery worker
	@echo '${BLUE}Starting Celery worker...${NC}'
	docker compose exec web celery -A sterna worker -l info

beat: ## Start Celery beat
	@echo '${BLUE}Starting Celery beat...${NC}'
	docker compose exec web celery -A sterna beat -l info

flower: ## Open Flower monitoring
	@echo '${BLUE}Opening Flower monitoring...${NC}'
	open http://localhost:5555

##@ Utilities

clean: ## Clean up generated files
	@echo '${YELLOW}Cleaning up...${NC}'
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".DS_Store" -delete
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	@echo '${GREEN}Cleanup complete!${NC}'

collectstatic: ## Collect static files
	@echo '${BLUE}Collecting static files...${NC}'
	docker compose exec web python manage.py collectstatic --noinput
	@echo '${GREEN}Static files collected!${NC}'

seed: ## Seed database with sample data
	@echo '${BLUE}Seeding database...${NC}'
	docker compose exec web python manage.py seed_data
	@echo '${GREEN}Database seeded!${NC}'

##@ Local Development (without Docker)

local-install: ## Install dependencies locally
	@echo '${BLUE}Installing dependencies locally...${NC}'
	python3 -m venv venv
	./venv/bin/pip install --upgrade pip
	./venv/bin/pip install -r requirements.txt
	@echo '${GREEN}Local installation complete!${NC}'

local-run: ## Run Django server locally
	@echo '${BLUE}Starting Django server locally...${NC}'
	./venv/bin/python manage.py runserver

local-migrate: ## Run migrations locally
	@echo '${BLUE}Running migrations locally...${NC}'
	./venv/bin/python manage.py migrate
	@echo '${GREEN}Local migrations complete!${NC}'

local-test: ## Run tests locally
	@echo '${BLUE}Running tests locally...${NC}'
	./venv/bin/pytest
	@echo '${GREEN}Local tests complete!${NC}'

##@ Git Hooks

pre-commit: ## Run pre-commit checks
	@echo '${BLUE}Running pre-commit checks...${NC}'
	make lint
	make test-fast
	@echo '${GREEN}Pre-commit checks passed!${NC}'