terraform {
  required_version = ">= 1.5.0"

  required_providers {
    scaleway = {
      source  = "scaleway/scaleway"
      version = "~> 2.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.20"
    }
    neon = {
      source  = "kislerdm/neon"
      version = "~> 0.6"
    }
  }

  # Backend configuration in backend.tf
}

# Shared Secrets (used by both staging and production)
module "shared_secrets" {
  source = "../../modules/shared-secrets"

  scaleway_access_key      = var.scaleway_access_key
  scaleway_secret_key      = var.scaleway_secret_key
  scaleway_project_id      = var.scaleway_project_id
  scaleway_organization_id = var.scaleway_organization_id
  region                   = "fr-par"
}

# =============================================================================
# Cloudflare Zone-Level Resources
# =============================================================================
# WAF and rate limiting rules are zone-scoped, not environment-scoped.
# They must be managed centrally since Cloudflare only allows one custom
# ruleset per phase per zone.

module "cloudflare_zone" {
  source = "../../modules/cloudflare-zone"

  cloudflare_api_token  = var.cloudflare_api_token
  cloudflare_account_id = var.cloudflare_account_id
  domain                = var.domain

  # Rate limiting for all environment API endpoints
  environments = [
    { name = "production", api_prefix = "api" },
    { name = "staging", api_prefix = "api-staging" }
  ]

  rate_limit_config = {
    requests_per_period = 100
    period              = 10
    mitigation_timeout  = 10
  }
}

# =============================================================================
# Neon PostgreSQL Project
# =============================================================================
# Single Neon project shared by all environments.
# Each environment creates its own branch within this project.

module "neon_project" {
  source = "../../modules/neon-project"

  neon_api_key = var.neon_api_key
  neon_org_id  = var.neon_org_id
  project_name = "sternaway"
  region       = "aws-eu-central-1"
}
