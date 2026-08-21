output "project_id" {
  description = "Neon project ID"
  value       = neon_project.main.id
}

output "branch_id" {
  description = "Neon branch ID"
  value       = neon_branch.env.id
}

output "host" {
  description = "Database host"
  value       = neon_project.main.database_host
}

output "connection_uri" {
  description = "Full connection URI with credentials"
  value       = neon_project.main.connection_uri
  sensitive   = true
}

output "connection_uri_pooler" {
  description = "Connection URI via connection pooler"
  value       = neon_project.main.connection_uri_pooler
  sensitive   = true
}

output "database_name" {
  description = "Database name"
  value       = neon_project.main.database_name
}

output "database_user" {
  description = "Database user"
  value       = neon_project.main.database_user
}

output "database_password" {
  description = "Database password"
  value       = neon_project.main.database_password
  sensitive   = true
}
