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
  description = "Domain name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "origin_ip" {
  description = "Origin server IP (load balancer or server)"
  type        = string
  default     = ""
}

variable "enable_tunnel" {
  description = "Enable Cloudflare Tunnel"
  type        = bool
  default     = true
}

variable "r2_bucket_name" {
  description = "R2 bucket name for storage"
  type        = string
  default     = ""
}

variable "enable_waf" {
  description = "Enable WAF rules"
  type        = bool
  default     = true
}

variable "create_tfstate_bucket" {
  description = "Create R2 bucket for Terraform state (only needed once, bucket may already exist)"
  type        = bool
  default     = false
}

variable "create_backup_bucket" {
  description = "Create R2 bucket for database backups"
  type        = bool
  default     = true
}
