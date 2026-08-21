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

variable "environment" {
  description = "Environment name (staging, production)"
  type        = string
}

variable "region" {
  description = "Scaleway region"
  type        = string
  default     = "fr-par" # Paris, France
}

variable "zone" {
  description = "Scaleway zone"
  type        = string
  default     = "fr-par-1"
}

variable "kapsule_config" {
  description = "Kapsule (managed Kubernetes) configuration"
  type = object({
    kubernetes_version = string
    cni                = string
    node_pools = list(object({
      name        = string
      node_type   = string
      size        = number
      min_size    = number
      max_size    = number
      autoscaling = bool
    }))
  })
  default = {
    kubernetes_version = "1.29"
    cni                = "cilium"
    node_pools = [
      {
        name        = "main"
        node_type   = "PLAY2-NANO" # 1 vCPU, 2GB RAM - cost effective
        size        = 3
        min_size    = 2
        max_size    = 5
        autoscaling = true
      }
    ]
  }
}

variable "registry_config" {
  description = "Container Registry configuration"
  type = object({
    is_public = bool
  })
  default = {
    is_public = false
  }
}

variable "vpc_cidr" {
  description = "VPC private network CIDR (Kapsule needs at least /22)"
  type        = string
  default     = "10.0.0.0/20"
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = list(string)
  default     = []
}
