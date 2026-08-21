# =============================================================================
# Neon Branch Module
# =============================================================================
# Creates a branch within an existing Neon project.
# Used by staging/production to create environment-specific branches.
# When use_default_branch = true, uses existing resources from the main branch.

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

# Create a branch for this environment
# For production, we use the default main branch
# For staging, we create a new branch
resource "neon_branch" "env" {
  count = var.use_default_branch ? 0 : 1

  project_id = var.project_id
  name       = var.branch_name
  parent_id  = var.parent_branch_id
}

locals {
  branch_id = var.use_default_branch ? var.default_branch_id : neon_branch.env[0].id
}

# Database on this branch
# For default branch, the database already exists - skip creation
resource "neon_database" "main" {
  count = var.use_default_branch ? 0 : 1

  project_id = var.project_id
  branch_id  = local.branch_id
  name       = var.database_name
  owner_name = var.database_user

  depends_on = [neon_endpoint.main]
}

# Read-write endpoint for this branch
# For default branch, the endpoint already exists - skip creation
resource "neon_endpoint" "main" {
  count = var.use_default_branch ? 0 : 1

  project_id = var.project_id
  branch_id  = local.branch_id
  type       = "read_write"

  autoscaling_limit_min_cu = var.min_compute_units
  autoscaling_limit_max_cu = var.max_compute_units
}

locals {
  # For default branch, use the provided connection_uri
  # For new branches, construct URI from created resources including password
  endpoint_host  = var.use_default_branch ? "" : neon_endpoint.main[0].host
  database_name  = var.use_default_branch ? var.database_name : neon_database.main[0].name
  connection_uri = var.use_default_branch ? var.default_connection_uri : "postgresql://${var.database_user}:${var.database_password}@${neon_endpoint.main[0].host}/${neon_database.main[0].name}?sslmode=require"
}
