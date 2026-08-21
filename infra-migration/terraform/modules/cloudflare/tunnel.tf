# Cloudflare Tunnel for secure ingress
resource "random_id" "tunnel_secret" {
  count       = var.enable_tunnel ? 1 : 0
  byte_length = 32
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "main" {
  count = var.enable_tunnel ? 1 : 0

  account_id = var.cloudflare_account_id
  name       = "sternaway-${var.environment}"
  secret     = random_id.tunnel_secret[0].b64_std
}

# Tunnel configuration
resource "cloudflare_zero_trust_tunnel_cloudflared_config" "main" {
  count = var.enable_tunnel ? 1 : 0

  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.main[0].id

  config {
    # Main application (frontend)
    ingress_rule {
      hostname = var.environment == "production" ? var.domain : "${var.environment}.${var.domain}"
      service  = "http://frontend.sternaway.svc.cluster.local:3000"
    }

    # API Gateway
    ingress_rule {
      hostname = var.environment == "production" ? "api.${var.domain}" : "api-${var.environment}.${var.domain}"
      service  = "http://api-gateway.sternaway.svc.cluster.local:80"
    }

    # Catch-all (required)
    ingress_rule {
      service = "http_status:404"
    }
  }
}

# DNS records for tunnel
resource "cloudflare_record" "tunnel_root" {
  count = var.enable_tunnel ? 1 : 0

  zone_id = data.cloudflare_zone.main.id
  name    = local.subdomain == "" ? "@" : local.subdomain
  value   = "${cloudflare_zero_trust_tunnel_cloudflared.main[0].id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
  ttl     = 1
}

resource "cloudflare_record" "tunnel_api" {
  count = var.enable_tunnel ? 1 : 0

  zone_id = data.cloudflare_zone.main.id
  name    = local.api_subdomain
  value   = "${cloudflare_zero_trust_tunnel_cloudflared.main[0].id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
  ttl     = 1
}
