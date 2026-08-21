# Kapsule Cluster Outputs
output "cluster_id" {
  description = "Kapsule cluster ID"
  value       = scaleway_k8s_cluster.main.id
}

output "cluster_name" {
  description = "Kapsule cluster name"
  value       = scaleway_k8s_cluster.main.name
}

output "cluster_endpoint" {
  description = "Kapsule cluster API endpoint"
  value       = scaleway_k8s_cluster.main.apiserver_url
}

output "cluster_ca_certificate" {
  description = "Kapsule cluster CA certificate (base64)"
  value       = scaleway_k8s_cluster.main.kubeconfig[0].cluster_ca_certificate
  sensitive   = true
}

output "kubeconfig" {
  description = "Raw kubeconfig for kubectl access"
  value       = scaleway_k8s_cluster.main.kubeconfig[0].config_file
  sensitive   = true
}

output "kubeconfig_host" {
  description = "Kubernetes API server host"
  value       = scaleway_k8s_cluster.main.kubeconfig[0].host
}

output "kubeconfig_token" {
  description = "Kubernetes authentication token"
  value       = scaleway_k8s_cluster.main.kubeconfig[0].token
  sensitive   = true
}

# Container Registry Outputs
output "registry_endpoint" {
  description = "Container registry endpoint"
  value       = scaleway_registry_namespace.main.endpoint
}

output "registry_namespace" {
  description = "Container registry namespace name"
  value       = scaleway_registry_namespace.main.name
}

output "registry_pull_secret" {
  description = "Registry pull credentials (for Kubernetes secrets)"
  value = {
    server   = scaleway_registry_namespace.main.endpoint
    username = scaleway_iam_api_key.registry_pull.access_key
    password = scaleway_iam_api_key.registry_pull.secret_key
  }
  sensitive = true
}

# VPC Outputs
output "vpc_id" {
  description = "VPC ID"
  value       = scaleway_vpc.main.id
}

output "private_network_id" {
  description = "Private network ID"
  value       = scaleway_vpc_private_network.main.id
}

output "public_gateway_id" {
  description = "Public gateway ID for internet egress"
  value       = scaleway_vpc_public_gateway.main.id
}

output "public_gateway_ip" {
  description = "Public gateway IP address"
  value       = scaleway_vpc_public_gateway_ip.main.address
}

# Node Pool Outputs
output "node_pools" {
  description = "Node pool information"
  value = {
    for name, pool in scaleway_k8s_pool.pools : name => {
      id        = pool.id
      name      = pool.name
      size      = pool.size
      node_type = pool.node_type
      status    = pool.status
    }
  }
}

# Cluster Info for CI/CD
output "cluster_info" {
  description = "Cluster information for CI/CD pipelines"
  value = {
    cluster_id = scaleway_k8s_cluster.main.id
    region     = var.region
    zone       = var.zone
    project_id = var.scaleway_project_id
  }
}

# =============================================================================
# Secret Manager Outputs
# =============================================================================

output "external_secrets_credentials" {
  description = "Credentials for External Secrets Operator"
  value = {
    access_key = scaleway_iam_api_key.external_secrets.access_key
    secret_key = scaleway_iam_api_key.external_secrets.secret_key
  }
  sensitive = true
}

output "secret_ids" {
  description = "Environment-specific secret IDs"
  value = {
    api_secrets        = scaleway_secret.api_secrets.id
    database_secrets   = scaleway_secret.database_secrets.id
    cloudflare_secrets = scaleway_secret.cloudflare_secrets.id
    redis_secrets      = scaleway_secret.redis_secrets.id
    frontend_secrets   = scaleway_secret.frontend_secrets.id
  }
}

output "secret_names" {
  description = "Environment-specific secret names"
  value = {
    api_secrets        = scaleway_secret.api_secrets.name
    database_secrets   = scaleway_secret.database_secrets.name
    cloudflare_secrets = scaleway_secret.cloudflare_secrets.name
    redis_secrets      = scaleway_secret.redis_secrets.name
    frontend_secrets   = scaleway_secret.frontend_secrets.name
  }
}
