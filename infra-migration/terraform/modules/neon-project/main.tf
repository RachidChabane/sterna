# =============================================================================
# Neon Project Module
# =============================================================================
# Creates a single Neon project that will be shared across environments.
# Each environment creates its own branch within this project.

terraform {
  required_providers {
    neon = {
      source  = "kislerdm/neon"
      version = "~> 0.6"
    }
  }
}

provider "neon" {
  api_key = var.neon_api_key
}

# Single Neon project for all environments
resource "neon_project" "main" {
  name       = var.project_name
  region_id  = var.region
  pg_version = var.pg_version
  org_id     = var.neon_org_id

  # Free tier limit: max 6 hours (21600 seconds)
  history_retention_seconds = var.history_retention_seconds
}
