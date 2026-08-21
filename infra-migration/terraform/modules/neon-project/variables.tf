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

variable "project_name" {
  description = "Neon project name"
  type        = string
}

variable "region" {
  description = "Neon region"
  type        = string
  default     = "aws-eu-central-1"
}

variable "pg_version" {
  description = "PostgreSQL version"
  type        = number
  default     = 16
}

variable "history_retention_seconds" {
  description = "History retention in seconds (free tier max: 21600)"
  type        = number
  default     = 21600
}
