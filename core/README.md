# Sterna — Application Code

Backend (Django), frontend (React), and microservices for the Sterna multi-model AI chat platform. See the repository root `README.md` for the product overview, `docs/architecture.md` for the service layout, and `docs/self-hosting.md` for deployment.

## Quick Start

### Prerequisites
- Python 3.12+
- Docker Desktop (or Docker Engine) with the **Compose v2 plugin** — `docker compose version` should print a `v2.x` line. `make dev` and every other `make` target shell out to `docker compose`, not the older standalone `docker-compose` v1 binary.
- PostgreSQL 16 (or use Docker)
- Redis 7 (or use Docker)

### Setup with Docker (Recommended)

This starts the stack defined in `docker-compose.yml` — frontend, API gateway, Django (`web`), Postgres, Redis, Celery worker/beat, and the search/maps microservices. `web`/`celery-worker` no longer depend on an external Docker network created by a separate compose file, and Django no longer needs a `logs/` directory to exist on the host to boot (logging is console-only — see `sterna/logging.py`). Verified end-to-end on a fresh clone for `postgres`, `redis`, and `web`.

1. Copy environment variables:
```bash
cp .env.example .env
```

2. Start all services:
```bash
make dev
```

3. Run migrations:
```bash
make migrate
```

4. Create a superuser:
```bash
make createsuperuser
```

5. Access the application:
- Frontend: http://localhost:5173
- API: http://localhost:8000
- Admin: http://localhost:8000/admin
- Health Check: http://localhost:8000/api/health/

### Optional: coding-agent sandbox stack

The AI coding-agent sandbox (spawns per-session containers to run opencode against a cloned repo) lives in its own compose file, `sandbox/docker-compose.sandbox.yml`. It's optional and separate from the quickstart above because it needs the core stack's network to already exist:

```bash
# after `make dev` has created the core_default network
make sandbox-build   # first run only: builds orchestrator, egress-proxy, sandbox-base, sandbox-datascience
cd sandbox
docker compose -f docker-compose.sandbox.yml up -d
```

`sandbox-base`/`sandbox-datascience` aren't compose services `up` starts — the
orchestrator spawns per-session containers from `sandbox-datascience:latest` by
name (`sandbox-base:latest` is only its build-time FROM base) — so skipping the
build step fails with `pull access denied` the first time a sandbox is created.
See `sandbox/README.md` for details.

Start core first, sandbox second — the sandbox stack's `orchestrator` service joins `core_default` as an external network to reach `web`/`api-gateway`. There's no reverse dependency: the core stack above never requires the sandbox stack to be running.

### Setup without Docker

1. Create virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up PostgreSQL and Redis locally

4. Copy and configure environment:
```bash
cp .env.example .env
# Edit .env with your local settings
```

5. Run migrations:
```bash
python manage.py migrate
```

6. Start the server:
```bash
python manage.py runserver
```

## Available Commands

Run `make help` to see all available commands:

- `make dev` - Start development environment (docker compose up -d)
- `make test` - Run backend tests with coverage (inside the web container)
- `make lint` - Run ruff + mypy + ESLint
- `make migrate` - Run database migrations
- `make shell` - Open Django shell
- `make logs` - View container logs
- `make seed` - Seed the database (tiers, preconfigured MCP servers, …)

## Layout

```
core/
├── sterna/            # Django project (modular settings, celery, urls, middleware)
├── authentication/       # Auth, OAuth, GDPR export/deletion
├── llm/                  # Chat orchestration, tools, image/video generation, model catalog
├── conversations/        # Conversation & message storage
├── code_sessions/        # Coding agent sessions, plans, GitHub integration
├── sandbox/              # Sandbox orchestrator + egress proxy (separate compose file)
├── usage_quota/          # Billing, quotas, Stripe, BYOK
├── knowledge_base/       # RAG (pgvector)
├── voice_rooms/          # Multi-agent voice (Channels/WebRTC)
├── sparks/               # AI-generated mini-apps
├── mcp/                  # MCP server integration
├── frontend/             # React 19 + TypeScript + Vite SPA
├── api-gateway/          # FastAPI gateway (JWT check, rate limit, routing)
├── brave-search/         # Web-search microservice
├── google-maps/          # Maps microservice
├── user-preferences-service/  # Preferences microservice
├── smoke/                # Post-deploy smoke checks
├── docker-compose.yml    # Dev stack
├── docker-compose.prod.yml   # Single-VPS production stack
└── Makefile              # Development commands
```

## Testing

With Docker running:
```bash
make test
```

Directly (in a venv with `requirements.txt` installed):
```bash
pytest -q
```

For a coverage report:
```bash
make coverage
```

## Development

The project uses:
- Django 5.2 (LTS) for the web framework
- Django REST Framework for APIs
- Django Channels (Daphne/Uvicorn ASGI) for WebSockets
- PostgreSQL 16 + pgvector for the database and embeddings
- Redis for caching, rate limiting, and the Celery broker
- Celery (worker + beat) for async task processing
- FastAPI for the microservices

## License

Copyright (c) 2025 Sterna
