# Scaleway Provider Configuration
provider "scaleway" {
  access_key      = var.scaleway_access_key
  secret_key      = var.scaleway_secret_key
  project_id      = var.scaleway_project_id
  organization_id = var.scaleway_organization_id
  region          = var.region
  zone            = var.zone
}

# Local values
locals {
  common_tags = distinct(concat(var.tags, [
    "environment:${var.environment}",
    "managed-by:terraform",
    "project:sternaway"
  ]))

  cluster_name  = "sternaway-${var.environment}"
  registry_name = "sternaway-${var.environment}"
}
