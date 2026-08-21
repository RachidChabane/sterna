#!/bin/bash
# =============================================================================
# Apply Kubernetes Secrets for Sterna
# =============================================================================
#
# Usage:
#   ./apply-secrets.sh [environment]
#
# Environment: staging (default) or production
#
# This script creates all required secrets from environment variables.
# Set the variables before running, or use a .env file:
#   source .env.secrets && ./apply-secrets.sh staging
#
# =============================================================================

set -euo pipefail

ENVIRONMENT="${1:-staging}"
NAMESPACE="sterna"

echo "=== Applying secrets for ${ENVIRONMENT} environment ==="

# Check required variables
check_required() {
    local var_name="$1"
    if [[ -z "${!var_name:-}" ]]; then
        echo "ERROR: Required variable ${var_name} is not set"
        exit 1
    fi
}

# Required variables
check_required "JWT_SECRET_KEY"
check_required "DATABASE_URL"

# Optional with defaults
FIELD_ENCRYPTION_KEY="${FIELD_ENCRYPTION_KEY:-}"
OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}"
OPENAI_API_KEY="${OPENAI_API_KEY:-}"
ELEVENLABS_API_KEY="${ELEVENLABS_API_KEY:-}"
DEEPGRAM_API_KEY="${DEEPGRAM_API_KEY:-}"
R2_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID:-}"
R2_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY:-}"
R2_BUCKET_NAME="${R2_BUCKET_NAME:-sternaway-storage}"
R2_ENDPOINT_URL="${R2_ENDPOINT_URL:-}"
BRAVE_API_KEY="${BRAVE_API_KEY:-}"
GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:-}"
GOOGLE_CLIENT_SECRET="${GOOGLE_CLIENT_SECRET:-}"
REDIS_URL="${REDIS_URL:-}"
TUNNEL_TOKEN="${TUNNEL_TOKEN:-}"

# Parse DATABASE_URL for individual components
DB_HOST=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^:/]*\).*|\1|p')
DB_PORT=$(echo "$DATABASE_URL" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')
DB_PORT="${DB_PORT:-5432}"
DB_USER=$(echo "$DATABASE_URL" | sed -n 's|.*://\([^:]*\):.*|\1|p')
DB_PASSWORD=$(echo "$DATABASE_URL" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')
DB_NAME=$(echo "$DATABASE_URL" | sed -n 's|.*/\([^?]*\).*|\1|p')

echo "Creating namespace ${NAMESPACE} if not exists..."
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

echo "Creating api-secrets..."
kubectl create secret generic api-secrets \
    --from-literal=JWT_SECRET_KEY="${JWT_SECRET_KEY}" \
    --from-literal=SECRET_KEY="${JWT_SECRET_KEY}" \
    --from-literal=FIELD_ENCRYPTION_KEY="${FIELD_ENCRYPTION_KEY}" \
    -n "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

echo "Creating database-secrets..."
kubectl create secret generic database-secrets \
    --from-literal=DATABASE_URL="${DATABASE_URL}" \
    --from-literal=DB_HOST="${DB_HOST}" \
    --from-literal=DB_PORT="${DB_PORT}" \
    --from-literal=DB_USER="${DB_USER}" \
    --from-literal=DB_PASSWORD="${DB_PASSWORD}" \
    --from-literal=DB_NAME="${DB_NAME}" \
    -n "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

echo "Creating llm-secrets..."
kubectl create secret generic llm-secrets \
    --from-literal=OPENROUTER_API_KEY="${OPENROUTER_API_KEY}" \
    --from-literal=ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}" \
    --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY}" \
    --from-literal=ELEVENLABS_API_KEY="${ELEVENLABS_API_KEY}" \
    --from-literal=DEEPGRAM_API_KEY="${DEEPGRAM_API_KEY}" \
    -n "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

echo "Creating storage-secrets..."
kubectl create secret generic storage-secrets \
    --from-literal=R2_ACCESS_KEY_ID="${R2_ACCESS_KEY_ID}" \
    --from-literal=R2_SECRET_ACCESS_KEY="${R2_SECRET_ACCESS_KEY}" \
    --from-literal=R2_BUCKET_NAME="${R2_BUCKET_NAME}" \
    --from-literal=R2_ENDPOINT_URL="${R2_ENDPOINT_URL}" \
    -n "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

echo "Creating external-services-secrets..."
kubectl create secret generic external-services-secrets \
    --from-literal=BRAVE_API_KEY="${BRAVE_API_KEY}" \
    --from-literal=GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID}" \
    --from-literal=GOOGLE_CLIENT_SECRET="${GOOGLE_CLIENT_SECRET}" \
    -n "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

if [[ -n "${REDIS_URL}" ]]; then
    echo "Creating redis-secrets..."
    kubectl create secret generic redis-secrets \
        --from-literal=REDIS_URL="${REDIS_URL}" \
        -n "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
fi

if [[ -n "${TUNNEL_TOKEN}" ]]; then
    echo "Creating cloudflare-tunnel-secrets..."
    kubectl create secret generic cloudflare-tunnel-secrets \
        --from-literal=TUNNEL_TOKEN="${TUNNEL_TOKEN}" \
        -n "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
fi

echo ""
echo "=== Secrets applied successfully ==="
echo ""
echo "To verify:"
echo "  kubectl get secrets -n ${NAMESPACE}"
echo ""
echo "To view a secret:"
echo "  kubectl get secret api-secrets -n ${NAMESPACE} -o jsonpath='{.data.JWT_SECRET_KEY}' | base64 -d"
