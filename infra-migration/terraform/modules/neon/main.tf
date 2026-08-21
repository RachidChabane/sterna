# Neon Provider Configuration
provider "neon" {
  api_key = var.neon_api_key
}

# Neon project
resource "neon_project" "main" {
  name       = var.project_name
  region_id  = var.region
  pg_version = var.pg_version
  org_id     = var.neon_org_id

  # Free tier limit: max 6 hours (21600 seconds)
  history_retention_seconds = 21600
}

# Create a branch for this environment
resource "neon_branch" "env" {
  project_id = neon_project.main.id
  name       = var.branch_name
}

# Database on this branch
resource "neon_database" "main" {
  project_id = neon_project.main.id
  branch_id  = neon_branch.env.id
  name       = var.database_name
  owner_name = neon_project.main.database_user

  # Endpoint must be available before database can be created
  depends_on = [neon_endpoint.main]
}

# Read-write endpoint
resource "neon_endpoint" "main" {
  project_id = neon_project.main.id
  branch_id  = neon_branch.env.id
  type       = "read_write"

  autoscaling_limit_min_cu = 0.25
  autoscaling_limit_max_cu = var.max_compute_units
  # Note: suspend_timeout_seconds requires paid plan
}
