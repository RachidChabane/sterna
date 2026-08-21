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

# Get shared environment state for Neon project info
# Uses Cloudflare R2 as S3-compatible backend
data "terraform_remote_state" "shared" {
  backend = "s3"
  config = {
    bucket                      = "sternaway-tfstate"
    key                         = "shared/terraform.tfstate"
    region                      = "us-east-1" # Required but ignored by R2
    endpoints                   = { s3 = "https://${var.cloudflare_account_id}.r2.cloudflarestorage.com" }
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    use_path_style              = true
  }
}

# Scaleway Provider for root module resources
provider "scaleway" {
  access_key      = var.scaleway_access_key
  secret_key      = var.scaleway_secret_key
  project_id      = var.scaleway_project_id
  organization_id = var.scaleway_organization_id
  region          = "fr-par"
}

# Neon provider for root module
provider "neon" {
  api_key = var.neon_api_key
}

# Scaleway Kapsule (Managed Kubernetes)
module "scaleway" {
  source = "../../modules/scaleway"

  scaleway_access_key      = var.scaleway_access_key
  scaleway_secret_key      = var.scaleway_secret_key
  scaleway_project_id      = var.scaleway_project_id
  scaleway_organization_id = var.scaleway_organization_id
  environment              = "production"
  region                   = "fr-par"
  zone                     = "fr-par-1"

  kapsule_config = {
    kubernetes_version = "1.31" # Updated to available version
    cni                = "cilium"
    node_pools = [
      {
        name        = "main"
        node_type   = "PLAY2-NANO" # 2 vCPU, 4GB RAM - production workloads
        size        = 3
        min_size    = 3
        max_size    = 6
        autoscaling = true
      }
    ]
  }

  registry_config = {
    is_public = false
  }

  tags = [
    "project:sternaway",
    "environment:production",
    "managed-by:terraform"
  ]
}

# Cloudflare
module "cloudflare" {
  source = "../../modules/cloudflare"

  cloudflare_api_token  = var.cloudflare_api_token
  cloudflare_account_id = var.cloudflare_account_id
  domain                = var.domain
  environment           = "production"
  # Cloudflare Tunnel connects to Kubernetes ingress, no direct IP needed
  origin_ip = "" # Tunnel handles routing

  # Tunnel enabled (fresh creation)
  enable_tunnel = true
  # R2 bucket for user-generated content (optional)
  r2_bucket_name = ""
  # WAF disabled - managed by shared environment (zone-level resources)
  enable_waf = false
}

# Neon PostgreSQL Branch (uses shared project's main branch)
module "neon_branch" {
  source = "../../modules/neon-branch"

  neon_api_key           = var.neon_api_key
  project_id             = data.terraform_remote_state.shared.outputs.neon_project_id
  default_branch_id      = data.terraform_remote_state.shared.outputs.neon_default_branch_id
  default_connection_uri = data.terraform_remote_state.shared.outputs.neon_connection_uri
  database_user          = data.terraform_remote_state.shared.outputs.neon_database_user
  branch_name            = "main"
  use_default_branch     = true # Use the default main branch for production
  database_name          = "sternaway"
  max_compute_units      = 2
}

# =============================================================================
# Sync Neon DATABASE_URL to Scaleway Secret Manager
# =============================================================================
# This ensures the database-secrets in Scaleway always has the correct
# connection string from Neon, including the password.

resource "scaleway_secret_version" "database_secrets" {
  secret_id = module.scaleway.secret_ids.database_secrets
  data = jsonencode({
    DATABASE_URL = module.neon_branch.connection_uri
  })
  description = "Auto-synced from Neon Terraform output"

  depends_on = [module.neon_branch, module.scaleway]
}
