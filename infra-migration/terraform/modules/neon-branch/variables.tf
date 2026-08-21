variable "neon_api_key" {
  description = "Neon API key"
  type        = string
  sensitive   = true
}

variable "project_id" {
  description = "Neon project ID"
  type        = string
}

variable "default_branch_id" {
  description = "Default branch ID (for production)"
  type        = string
}

variable "parent_branch_id" {
  description = "Parent branch ID (for creating child branches)"
  type        = string
  default     = ""
}

variable "branch_name" {
  description = "Branch name"
  type        = string
}

variable "use_default_branch" {
  description = "Use the default (main) branch instead of creating a new one"
  type        = bool
  default     = false
}

variable "database_name" {
  description = "Database name"
  type        = string
}

variable "database_user" {
  description = "Database owner user"
  type        = string
}

variable "database_password" {
  description = "Database password"
  type        = string
  default     = ""
  sensitive   = true
}

variable "min_compute_units" {
  description = "Minimum compute units"
  type        = number
  default     = 0.25
}

variable "max_compute_units" {
  description = "Maximum compute units"
  type        = number
  default     = 1
}

variable "default_connection_uri" {
  description = "Connection URI for default branch (when use_default_branch = true)"
  type        = string
  default     = ""
  sensitive   = true
}
