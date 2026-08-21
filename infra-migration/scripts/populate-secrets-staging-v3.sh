#!/bin/bash
# Populate Scaleway Secret Manager with staging secrets - RAW JSON VERSION
#
# task-29 C5 SANITIZATION (2026-05-23): this script previously
# embedded real staging credentials (Neon DB password, OpenAI key,
# OpenRouter key, Google AI key, Stripe keys, OAuth client secrets,
# Cloudflare tunnel token, Brave/Google Maps API keys). Those values
# are still in git history. **All of them MUST be rotated** — see
# tracked issue C5 / #30. This script now reads from env vars so
# future runs do not re-leak.
#
# Usage:
#
#   export API_SECRETS_JSON='{"SECRET_KEY":"...","FIELD_ENCRYPTION_KEY":"...",...}'
#   export DATABASE_URL='postgresql://...'
#   export LLM_SECRETS_JSON='{"OPENROUTER_API_KEY":"...","OPENAI_API_KEY":"..."}'
#   export VOICE_SECRETS_JSON='{"DEEPGRAM_API_KEY":"...","ELEVENLABS_API_KEY":"..."}'
#   export OAUTH_SECRETS_JSON='{"GOOGLE_OAUTH_CLIENT_ID":"...","GOOGLE_OAUTH_CLIENT_SECRET":"...",...}'
#   export EXTERNAL_SECRETS_JSON='{"BRAVE_API_KEY":"...","GOOGLE_MAPS_API_KEY":"..."}'
#   export CLOUDFLARE_TUNNEL_TOKEN='...'
#   ./populate-secrets-staging-v3.sh
#
# Each env var holds the FULL JSON payload for that Scaleway Secret
# Manager entry. Operators source these from a local untracked file
# (e.g. ~/.secrets/sternaway-staging.env, sourced via `set -a`).

set -euo pipefail

echo "Populating Scaleway Secret Manager secrets for staging..."

REQUIRED_VARS=(
  API_SECRETS_JSON
  DATABASE_URL
  LLM_SECRETS_JSON
  VOICE_SECRETS_JSON
  OAUTH_SECRETS_JSON
  EXTERNAL_SECRETS_JSON
  CLOUDFLARE_TUNNEL_TOKEN
)
missing=0
for v in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!v:-}" ]]; then
    echo "ERROR: env var $v is not set" >&2
    missing=1
  fi
done
if [[ $missing -ne 0 ]]; then
  echo "Aborting: required env vars missing. See script header for usage." >&2
  exit 2
fi

# Secret IDs come from terraform output. Opaque references that do not
# grant access on their own, but environment-specific, so they are
# supplied via env rather than committed:
#   export API_SECRET_ID=$(terraform output -raw api_secret_id) ...
SECRET_ID_VARS=(API_SECRET_ID DATABASE_SECRET_ID LLM_SECRET_ID VOICE_SECRET_ID OAUTH_SECRET_ID EXTERNAL_SECRET_ID CLOUDFLARE_SECRET_ID REDIS_SECRET_ID)
for v in "${SECRET_ID_VARS[@]}"; do
  if [[ -z "${!v:-}" ]]; then
    echo "ERROR: env var $v is not set (get it from 'terraform output')" >&2
    exit 2
  fi
done

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

echo "Creating api-secrets version..."
printf '%s' "$API_SECRETS_JSON" > "$TMPDIR/api.json"
scw secret version create "$API_SECRET_ID" data=@"$TMPDIR/api.json"

echo "Creating database-secrets version..."
printf '{"DATABASE_URL":"%s"}' "$DATABASE_URL" > "$TMPDIR/db.json"
scw secret version create "$DATABASE_SECRET_ID" data=@"$TMPDIR/db.json"

echo "Creating llm-secrets version..."
printf '%s' "$LLM_SECRETS_JSON" > "$TMPDIR/llm.json"
scw secret version create "$LLM_SECRET_ID" data=@"$TMPDIR/llm.json"

echo "Creating voice-secrets version..."
printf '%s' "$VOICE_SECRETS_JSON" > "$TMPDIR/voice.json"
scw secret version create "$VOICE_SECRET_ID" data=@"$TMPDIR/voice.json"

echo "Creating oauth-secrets version..."
printf '%s' "$OAUTH_SECRETS_JSON" > "$TMPDIR/oauth.json"
scw secret version create "$OAUTH_SECRET_ID" data=@"$TMPDIR/oauth.json"

echo "Creating external-secrets version..."
printf '%s' "$EXTERNAL_SECRETS_JSON" > "$TMPDIR/external.json"
scw secret version create "$EXTERNAL_SECRET_ID" data=@"$TMPDIR/external.json"

echo "Creating cloudflare-secrets version..."
printf '{"TUNNEL_TOKEN":"%s"}' "$CLOUDFLARE_TUNNEL_TOKEN" > "$TMPDIR/cloudflare.json"
scw secret version create "$CLOUDFLARE_SECRET_ID" data=@"$TMPDIR/cloudflare.json"

echo "Creating redis-secrets version..."
printf '{"REDIS_URL":"redis://redis:6379/0"}' > "$TMPDIR/redis.json"
scw secret version create "$REDIS_SECRET_ID" data=@"$TMPDIR/redis.json"

echo ""
echo "All secrets populated successfully!"
echo "Verify with: scw secret version access secret-id=$API_SECRET_ID revision=latest"
