# =============================================================================
# Shared Secrets Module
# =============================================================================
# Creates secrets that are shared across all environments (staging, production)
# These contain API keys that are the same regardless of environment

# Scaleway Provider Configuration
provider "scaleway" {
  access_key      = var.scaleway_access_key
  secret_key      = var.scaleway_secret_key
  project_id      = var.scaleway_project_id
  organization_id = var.scaleway_organization_id
  region          = var.region
}

locals {
  common_tags = [
    "scope:shared",
    "managed-by:terraform",
    "project:sternaway"
  ]
}

# -----------------------------------------------------------------------------
# IAM Application for External Secrets Operator (shared access)
# -----------------------------------------------------------------------------

resource "scaleway_iam_application" "shared_secrets" {
  name        = "sternaway-shared-secrets"
  description = "IAM application for External Secrets Operator to access shared secrets"
}

resource "scaleway_iam_api_key" "shared_secrets" {
  application_id = scaleway_iam_application.shared_secrets.id
  description    = "API key for External Secrets Operator - shared secrets"
}

resource "scaleway_iam_policy" "shared_secrets_policy" {
  name           = "sternaway-shared-secrets-policy"
  application_id = scaleway_iam_application.shared_secrets.id

  rule {
    project_ids          = [var.scaleway_project_id]
    permission_set_names = ["SecretManagerReadOnly", "SecretManagerSecretAccess"]
  }
}

# -----------------------------------------------------------------------------
# Shared Secret Definitions
# -----------------------------------------------------------------------------

# LLM Provider Secrets (OpenRouter, OpenAI, Google AI Studio, Runway)
resource "scaleway_secret" "llm_secrets" {
  name        = "sternaway-shared-llm-secrets"
  description = "LLM and AI provider API keys (shared across environments)"
  project_id  = var.scaleway_project_id
  tags        = local.common_tags
}

# OAuth Secrets (Google, GitHub, Notion)
resource "scaleway_secret" "oauth_secrets" {
  name        = "sternaway-shared-oauth-secrets"
  description = "OAuth provider credentials (shared across environments)"
  project_id  = var.scaleway_project_id
  tags        = local.common_tags
}

# External Service Secrets (Brave, Google Maps)
resource "scaleway_secret" "external_secrets" {
  name        = "sternaway-shared-external-secrets"
  description = "External service API keys (shared across environments)"
  project_id  = var.scaleway_project_id
  tags        = local.common_tags
}

# Voice Provider Secrets (Deepgram, ElevenLabs)
resource "scaleway_secret" "voice_secrets" {
  name        = "sternaway-shared-voice-secrets"
  description = "Voice provider API keys (shared across environments)"
  project_id  = var.scaleway_project_id
  tags        = local.common_tags
}

# Storage Secrets (R2/S3 credentials for backups and file storage)
resource "scaleway_secret" "storage_secrets" {
  name        = "sternaway-shared-storage-secrets"
  description = "R2/S3 storage credentials (shared across environments)"
  project_id  = var.scaleway_project_id
  tags        = local.common_tags
}

# Alerting Secrets (Slack webhook, PagerDuty, etc.)
resource "scaleway_secret" "alerting_secrets" {
  name        = "sternaway-shared-alerting-secrets"
  description = "Alerting and notification credentials (shared across environments)"
  project_id  = var.scaleway_project_id
  tags        = local.common_tags
}
