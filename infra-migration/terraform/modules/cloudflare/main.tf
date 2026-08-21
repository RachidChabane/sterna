# Cloudflare Provider Configuration
provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# Get zone
data "cloudflare_zone" "main" {
  name = var.domain
}

locals {
  subdomain     = var.environment == "production" ? "" : var.environment
  api_subdomain = var.environment == "production" ? "api" : "api-${var.environment}"
}
