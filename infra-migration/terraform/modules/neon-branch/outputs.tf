output "branch_id" {
  description = "Branch ID"
  value       = local.branch_id
}

output "branch_name" {
  description = "Branch name"
  value       = var.branch_name
}

output "database_name" {
  description = "Database name"
  value       = local.database_name
}

output "endpoint_host" {
  description = "Endpoint host (empty for default branch)"
  value       = local.endpoint_host
}

output "connection_uri" {
  description = "Full connection URI"
  value       = local.connection_uri
  sensitive   = true
}
