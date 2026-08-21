# Direct A records (when not using tunnel)
resource "cloudflare_record" "root" {
  count = var.enable_tunnel ? 0 : (var.origin_ip != "" ? 1 : 0)

  zone_id = data.cloudflare_zone.main.id
  name    = local.subdomain == "" ? "@" : local.subdomain
  value   = var.origin_ip
  type    = "A"
  proxied = true
  ttl     = 1 # Auto
}

resource "cloudflare_record" "api" {
  count = var.enable_tunnel ? 0 : (var.origin_ip != "" ? 1 : 0)

  zone_id = data.cloudflare_zone.main.id
  name    = local.api_subdomain
  value   = var.origin_ip
  type    = "A"
  proxied = true
  ttl     = 1
}

# Wildcard for sandboxes (if needed)
resource "cloudflare_record" "sandbox" {
  count = var.enable_tunnel ? 0 : (var.origin_ip != "" ? 1 : 0)

  zone_id = data.cloudflare_zone.main.id
  name    = var.environment == "production" ? "*.sandbox" : "*.sandbox-${var.environment}"
  value   = var.origin_ip
  type    = "A"
  proxied = true
  ttl     = 1
}
