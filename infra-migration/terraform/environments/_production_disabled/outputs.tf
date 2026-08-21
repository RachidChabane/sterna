# Scaleway Kapsule outputs
output "cluster_endpoint" {
  description = "Kapsule cluster API endpoint"
  value       = module.scaleway.cluster_endpoint
}

output "cluster_id" {
  description = "Kapsule cluster ID"
  value       = module.scaleway.cluster_id
}

output "kubeconfig" {
  description = "Kubeconfig for kubectl access"
  value       = module.scaleway.kubeconfig
  sensitive   = true
}

output "registry_endpoint" {
  description = "Container registry endpoint"
  value       = module.scaleway.registry_endpoint
}

output "registry_namespace" {
  description = "Container registry namespace"
  value       = module.scaleway.registry_namespace
}

output "registry_pull_secret" {
  description = "Registry pull credentials for Kubernetes"
  value       = module.scaleway.registry_pull_secret
  sensitive   = true
}

# Cloudflare outputs
output "tunnel_id" {
  description = "Cloudflare Tunnel ID"
  value       = module.cloudflare.tunnel_id
}

output "tunnel_token" {
  description = "Cloudflare Tunnel token"
  value       = module.cloudflare.tunnel_token
  sensitive   = true
}

output "app_domain" {
  description = "Application domain"
  value       = module.cloudflare.app_domain
}

output "api_domain" {
  description = "API domain"
  value       = module.cloudflare.api_domain
}

output "r2_bucket_name" {
  description = "R2 bucket name"
  value       = module.cloudflare.r2_bucket_name
}

# Neon outputs
output "database_connection_uri" {
  description = "Database connection URI"
  value       = module.neon_branch.connection_uri
  sensitive   = true
}

output "database_host" {
  description = "Database host"
  value       = module.neon_branch.endpoint_host
}

# Combined cluster info for CI/CD
output "cluster_info" {
  description = "Cluster information for CI/CD pipelines"
  value       = module.scaleway.cluster_info
}

# Secret Manager outputs
output "external_secrets_credentials" {
  description = "Credentials for External Secrets Operator"
  value       = module.scaleway.external_secrets_credentials
  sensitive   = true
}

output "secret_names" {
  description = "Secret names for External Secrets configuration"
  value       = module.scaleway.secret_names
}
