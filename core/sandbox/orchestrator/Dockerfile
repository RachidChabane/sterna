# Orchestrator Service Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (including Node.js for JavaScript execution)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY *.py .

# Create non-root user
RUN useradd -m -u 1001 orchestrator && \
    chown -R orchestrator:orchestrator /app

USER orchestrator

# Expose API port
EXPOSE 8003

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

# Default: Start API server (can be overridden for Celery worker/beat).
# Production CMD — no --reload; local dev hot reload comes from the
# `command:` override in core/sandbox/docker-compose.sandbox.yml.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
