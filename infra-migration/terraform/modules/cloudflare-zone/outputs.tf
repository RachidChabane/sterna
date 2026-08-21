output "zone_id" {
  description = "Cloudflare zone ID"
  value       = data.cloudflare_zone.main.id
}

output "waf_ruleset_id" {
  description = "WAF ruleset ID"
  value       = cloudflare_ruleset.waf.id
}

output "rate_limit_ruleset_id" {
  description = "Rate limiting ruleset ID"
  value       = cloudflare_ruleset.rate_limit.id
}
