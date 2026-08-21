# =============================================================================
# Cloudflare Zone-Level Resources
# =============================================================================
# This module manages resources that are scoped to the entire zone, not to
# individual environments. Since Cloudflare only allows one custom ruleset
# per phase per zone, these must be managed centrally.

terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.20"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# Get zone ID
data "cloudflare_zone" "main" {
  name = var.domain
}

# =============================================================================
# WAF Custom Ruleset
# =============================================================================
# These rules apply to the entire zone and protect all environments

resource "cloudflare_ruleset" "waf" {
  zone_id = data.cloudflare_zone.main.id
  name    = "Zone WAF Rules"
  kind    = "zone"
  phase   = "http_request_firewall_custom"

  # Block path traversal attempts
  rules {
    action      = "block"
    expression  = "(http.request.uri.path contains \"../\") or (http.request.uri.path contains \"..%2f\")"
    description = "Block path traversal"
    enabled     = true
  }

  # Block XSS attempts in query strings
  rules {
    action      = "block"
    expression  = "(http.request.uri.query contains \"<script\") or (lower(http.request.uri.query) contains \"javascript:\")"
    description = "Block XSS attempts in query"
    enabled     = true
  }

  # Challenge requests with high threat scores
  rules {
    action      = "managed_challenge"
    expression  = "(cf.threat_score gt 30)"
    description = "Challenge high threat score"
    enabled     = true
  }

  # Block unverified bots (allow search engines)
  rules {
    action      = "block"
    expression  = "(cf.client.bot) and not (cf.verified_bot_category in {\"search_engine\"})"
    description = "Block unverified bots"
    enabled     = true
  }
}

# =============================================================================
# Rate Limiting Ruleset
# =============================================================================
# Rate limiting for API endpoints across all environments

resource "cloudflare_ruleset" "rate_limit" {
  zone_id = data.cloudflare_zone.main.id
  name    = "Zone Rate Limiting"
  kind    = "zone"
  phase   = "http_ratelimit"

  # Single rate limiting rule for all API endpoints (free plan allows 1 rule)
  rules {
    action = "block"
    ratelimit {
      characteristics     = ["cf.colo.id", "ip.src"]
      period              = var.rate_limit_config.period
      requests_per_period = var.rate_limit_config.requests_per_period
      mitigation_timeout  = var.rate_limit_config.mitigation_timeout
    }
    expression  = join(" or ", [for env in var.environments : "(http.host eq \"${env.api_prefix}.${var.domain}\")"])
    description = "API rate limit - all environments"
    enabled     = true
  }
}
