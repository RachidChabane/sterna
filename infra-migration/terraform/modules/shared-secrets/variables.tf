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

variable "region" {
  description = "Scaleway region"
  type        = string
  default     = "fr-par"
}
