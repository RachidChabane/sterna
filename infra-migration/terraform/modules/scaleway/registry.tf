# Scaleway Container Registry

resource "scaleway_registry_namespace" "main" {
  name        = local.registry_name
  description = "Container registry for Sternaway ${var.environment}"
  is_public   = var.registry_config.is_public
  region      = var.region
}

# Create registry credentials for Kubernetes to pull images
resource "scaleway_iam_api_key" "registry_pull" {
  application_id = scaleway_iam_application.registry.id
  description    = "Registry pull access for Kapsule - ${var.environment}"
}

resource "scaleway_iam_application" "registry" {
  name        = "sternaway-registry-${var.environment}"
  description = "Application for container registry access"
}

resource "scaleway_iam_policy" "registry_policy" {
  name           = "sternaway-registry-policy-${var.environment}"
  application_id = scaleway_iam_application.registry.id

  rule {
    project_ids          = [var.scaleway_project_id]
    permission_set_names = ["ContainerRegistryReadOnly"]
  }
}
