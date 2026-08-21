# =============================================================================
# Scaleway Secret Manager - Environment-Specific Secrets
# =============================================================================
# Manages secrets that differ per environment (staging vs production)
# Shared secrets (LLM, OAuth, External, Voice) are in the shared-secrets module

# -----------------------------------------------------------------------------
# IAM Application for External Secrets Operator
# -----------------------------------------------------------------------------

resource "scaleway_iam_application" "external_secrets" {
  name        = "sternaway-external-secrets-${var.environment}"
  description = "IAM application for External Secrets Operator to access Secret Manager"
}

resource "scaleway_iam_api_key" "external_secrets" {
  application_id = scaleway_iam_application.external_secrets.id
  description    = "API key for External Secrets Operator - ${var.environment}"
}

resource "scaleway_iam_policy" "external_secrets_policy" {
  name           = "sternaway-external-secrets-policy-${var.environment}"
  application_id = scaleway_iam_application.external_secrets.id

  rule {
    project_ids          = [var.scaleway_project_id]
    permission_set_names = ["SecretManagerReadOnly", "SecretManagerSecretAccess"]
  }
}

# -----------------------------------------------------------------------------
# Environment-Specific Secret Definitions
# -----------------------------------------------------------------------------

locals {
  env_tags = distinct(concat(local.common_tags, ["scope:${var.environment}"]))
}

# API Secrets (JWT, Django SECRET_KEY, encryption keys, URLs)
resource "scaleway_secret" "api_secrets" {
  name        = "sternaway-${var.environment}-api-secrets"
  description = "API authentication, encryption secrets, and environment-specific URLs"
  project_id  = var.scaleway_project_id
  tags        = local.env_tags
}

# Database Secrets (Neon PostgreSQL connection - different per environment)
resource "scaleway_secret" "database_secrets" {
  name        = "sternaway-${var.environment}-database-secrets"
  description = "Database connection credentials"
  project_id  = var.scaleway_project_id
  tags        = local.env_tags
}

# Cloudflare Tunnel Token (different tunnel per environment)
resource "scaleway_secret" "cloudflare_secrets" {
  name        = "sternaway-${var.environment}-cloudflare-secrets"
  description = "Cloudflare tunnel and service credentials"
  project_id  = var.scaleway_project_id
  tags        = local.env_tags
}

# Redis Secrets (if using external Redis)
resource "scaleway_secret" "redis_secrets" {
  name        = "sternaway-${var.environment}-redis-secrets"
  description = "Redis connection credentials"
  project_id  = var.scaleway_project_id
  tags        = local.env_tags
}

# Frontend Configuration Secrets (environment-specific URLs)
resource "scaleway_secret" "frontend_secrets" {
  name        = "sternaway-${var.environment}-frontend-secrets"
  description = "Frontend configuration (API URLs, feature flags)"
  project_id  = var.scaleway_project_id
  tags        = local.env_tags
}
