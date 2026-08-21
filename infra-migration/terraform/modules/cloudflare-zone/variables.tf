variable "cloudflare_api_token" {
  description = "Cloudflare API token"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare account ID"
  type        = string
}

variable "domain" {
  description = "Domain name (zone)"
  type        = string
}

variable "environments" {
  description = "List of environments to create rate limiting rules for"
  type = list(object({
    name       = string
    api_prefix = string # e.g., "api" for production, "api-staging" for staging
  }))
  default = [
    { name = "production", api_prefix = "api" },
    { name = "staging", api_prefix = "api-staging" }
  ]
}

variable "rate_limit_config" {
  description = "Rate limiting configuration"
  type = object({
    requests_per_period = number
    period              = number
    mitigation_timeout  = number
  })
  default = {
    requests_per_period = 100
    period              = 10
    mitigation_timeout  = 10
  }
}
