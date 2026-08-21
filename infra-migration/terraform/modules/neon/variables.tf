variable "neon_api_key" {
  description = "Neon API key"
  type        = string
  sensitive   = true
}

variable "neon_org_id" {
  description = "Neon Organization ID"
  type        = string
}

variable "project_name" {
  description = "Neon project name"
  type        = string
}

variable "region" {
  description = "Neon region"
  type        = string
  default     = "aws-eu-central-1" # Frankfurt
}

variable "database_name" {
  description = "Database name"
  type        = string
  default     = "sternaway"
}

variable "branch_name" {
  description = "Branch name for this environment"
  type        = string
  default     = "main"
}

variable "pg_version" {
  description = "PostgreSQL version"
  type        = number
  default     = 16
}

variable "max_compute_units" {
  description = "Maximum compute units for autoscaling"
  type        = number
  default     = 2
}

variable "suspend_timeout" {
  description = "Seconds of inactivity before suspending compute"
  type        = number
  default     = 300
}
