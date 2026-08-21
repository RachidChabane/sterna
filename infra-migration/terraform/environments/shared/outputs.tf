# Shared Secrets Outputs

output "secret_ids" {
  description = "Shared secret IDs"
  value       = module.shared_secrets.secret_ids
}

output "secret_names" {
  description = "Shared secret names"
  value       = module.shared_secrets.secret_names
}

output "credentials" {
  description = "Credentials for External Secrets Operator to access shared secrets"
  value       = module.shared_secrets.credentials
  sensitive   = true
}

# Cloudflare Zone Outputs

output "zone_id" {
  description = "Cloudflare zone ID"
  value       = module.cloudflare_zone.zone_id
}

output "waf_ruleset_id" {
  description = "WAF ruleset ID"
  value       = module.cloudflare_zone.waf_ruleset_id
}

output "rate_limit_ruleset_id" {
  description = "Rate limiting ruleset ID"
  value       = module.cloudflare_zone.rate_limit_ruleset_id
}

# Neon Project Outputs

output "neon_project_id" {
  description = "Neon project ID"
  value       = module.neon_project.project_id
}

output "neon_default_branch_id" {
  description = "Neon default branch ID"
  value       = module.neon_project.default_branch_id
}

output "neon_database_user" {
  description = "Neon database user"
  value       = module.neon_project.database_user
}

output "neon_database_password" {
  description = "Neon database password"
  value       = module.neon_project.database_password
  sensitive   = true
}

output "neon_connection_uri" {
  description = "Neon default database connection URI"
  value       = module.neon_project.connection_uri
  sensitive   = true
}
