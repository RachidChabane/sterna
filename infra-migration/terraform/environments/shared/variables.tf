# Scaleway credentials
variable "scaleway_access_key" {
  description = "Scaleway Access Key"
  type        = string
  sensitive   = true
}

variable "scaleway_secret_key" {
  description = "Scaleway Secret Key"
  type        = string
  sensitive   = true
}

variable "scaleway_project_id" {
  description = "Scaleway Project ID"
  type        = string
}

variable "scaleway_organization_id" {
  description = "Scaleway Organization ID"
  type        = string
}

# Cloudflare credentials
variable "cloudflare_api_token" {
  description = "Cloudflare API token"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare Account ID"
  type        = string
}

variable "domain" {
  description = "Domain name for the zone"
  type        = string
}

# Neon credentials
variable "neon_api_key" {
  description = "Neon API key"
  type        = string
  sensitive   = true
}

variable "neon_org_id" {
  description = "Neon organization ID"
  type        = string
  default     = ""
}
