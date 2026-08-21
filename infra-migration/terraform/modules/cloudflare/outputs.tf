output "zone_id" {
  description = "Cloudflare zone ID"
  value       = data.cloudflare_zone.main.id
}

output "tunnel_id" {
  description = "Cloudflare Tunnel ID"
  value       = var.enable_tunnel ? cloudflare_zero_trust_tunnel_cloudflared.main[0].id : null
}

output "tunnel_token" {
  description = "Cloudflare Tunnel token (for running cloudflared)"
  value       = var.enable_tunnel ? cloudflare_zero_trust_tunnel_cloudflared.main[0].tunnel_token : null
  sensitive   = true
}

output "tunnel_cname" {
  description = "Cloudflare Tunnel CNAME"
  value       = var.enable_tunnel ? "${cloudflare_zero_trust_tunnel_cloudflared.main[0].id}.cfargotunnel.com" : null
}

output "r2_bucket_name" {
  description = "R2 bucket name"
  value       = var.r2_bucket_name != "" ? cloudflare_r2_bucket.main[0].name : null
}

output "r2_backup_bucket_name" {
  description = "R2 backup bucket name"
  value       = var.create_backup_bucket ? cloudflare_r2_bucket.backups[0].name : null
}

output "api_domain" {
  description = "API domain"
  value       = var.environment == "production" ? "api.${var.domain}" : "api-${var.environment}.${var.domain}"
}

output "app_domain" {
  description = "Application domain"
  value       = var.environment == "production" ? var.domain : "${var.environment}.${var.domain}"
}
