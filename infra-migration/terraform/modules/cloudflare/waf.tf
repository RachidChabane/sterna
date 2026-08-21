# WAF ruleset
resource "cloudflare_ruleset" "waf" {
  count = var.enable_waf ? 1 : 0

  zone_id = data.cloudflare_zone.main.id
  name    = "Sternaway WAF ${var.environment}"
  kind    = "zone"
  phase   = "http_request_firewall_custom"

  # Block path traversal
  rules {
    action      = "block"
    expression  = "(http.request.uri.path contains \"../\") or (http.request.uri.path contains \"..%2f\")"
    description = "Block path traversal"
    enabled     = true
  }

  # Block XSS attempts
  rules {
    action      = "block"
    expression  = "(http.request.uri.query contains \"<script\") or (lower(http.request.uri.query) contains \"javascript:\")"
    description = "Block XSS attempts in query"
    enabled     = true
  }

  # Challenge high threat score
  rules {
    action      = "managed_challenge"
    expression  = "(cf.threat_score gt 30)"
    description = "Challenge high threat score"
    enabled     = true
  }

  # Block known bad bots
  rules {
    action      = "block"
    expression  = "(cf.client.bot) and not (cf.verified_bot_category in {\"search_engine\"})"
    description = "Block unverified bots"
    enabled     = true
  }
}

# Rate limiting using modern Cloudflare ruleset (replaces deprecated cloudflare_rate_limit)
resource "cloudflare_ruleset" "rate_limit" {
  count = var.enable_waf ? 1 : 0

  zone_id = data.cloudflare_zone.main.id
  name    = "Rate Limiting ${var.environment}"
  kind    = "zone"
  phase   = "http_ratelimit"

  rules {
    action = "block"
    ratelimit {
      characteristics     = ["cf.colo.id", "ip.src"]
      period              = 10
      requests_per_period = 100
      mitigation_timeout  = 10
    }
    expression  = "(http.host eq \"${var.environment == "production" ? "api" : "api-${var.environment}"}.${var.domain}\")"
    description = "API rate limit - ${var.environment}"
    enabled     = true
  }
}
