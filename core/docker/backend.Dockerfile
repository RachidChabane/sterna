# =============================================================================
# Backend (Django) image — builder/runtime split
# =============================================================================
# - Stage 1 compiles/installs Python deps with the build toolchain.
# - Stage 2 is the slim runtime: no gcc/build-essential, static assets
#   pre-collected at build time.
#
# Consumers (keep compatible):
# - .github/workflows/ci.yml builds with context ./core and this file
#   (no --target, so the final runtime stage is built).
# - core/docker-compose.yml `web` overrides CMD with `uvicorn --reload`
#   and bind-mounts the source for hot reload; celery-worker/celery-beat
#   override CMD with celery commands.
# - infra-migration web/consigliere/celery-* Deployments: web uses the
#   image CMD below; the others set their own command.

# --- Stage 1: builder ---------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build-only system dependencies (dropped from the runtime image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --prefix=/install --no-cache-dir -r /tmp/requirements.txt

# --- Stage 2: runtime ---------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Runtime system dependencies:
# - postgresql-client: psql/pg_dump for ops + backup jobs
# - curl: healthchecks
# - nodejs: MCP stdio servers spawned by the backend
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Python deps from the builder stage (same base image, same prefix)
COPY --from=builder /install /usr/local

# Copy project
COPY . /app/

# Create necessary directories
RUN mkdir -p /app/logs /app/media /app/static /app/staticfiles

# Collect static assets at build time. Only a dummy SECRET_KEY is
# needed: settings load with defaults and collectstatic never touches
# the database. The real key is injected at runtime via env/secrets.
RUN DJANGO_ENV=dev SECRET_KEY=dummy-build-only-collectstatic-key \
    python manage.py collectstatic --noinput

# Create a non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Serve the ASGI application. Django Channels WebSocket endpoints
# (voice_rooms, code_sessions — see sterna/asgi.py) require an ASGI
# server; plain gunicorn+WSGI silently drops all /ws/ upgrade requests.
# NOTE: uvicorn.workers.UvicornWorker is deprecated upstream in favor of
# the `uvicorn-worker` package; it still ships and works in uvicorn
# 0.35.0 (pinned in requirements.txt). Swap to uvicorn-worker on the
# next uvicorn major bump.
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "sterna.asgi:application", "--bind", "0.0.0.0:8000", "--workers", "4"]
