output "project_id" {
  description = "Neon project ID"
  value       = neon_project.main.id
}

output "project_name" {
  description = "Neon project name"
  value       = neon_project.main.name
}

output "default_branch_id" {
  description = "Default branch ID (main)"
  value       = neon_project.main.default_branch_id
}

output "database_user" {
  description = "Default database user"
  value       = neon_project.main.database_user
}

output "database_password" {
  description = "Default database password"
  value       = neon_project.main.database_password
  sensitive   = true
}

output "connection_uri" {
  description = "Default database connection URI"
  value       = neon_project.main.connection_uri
  sensitive   = true
}
