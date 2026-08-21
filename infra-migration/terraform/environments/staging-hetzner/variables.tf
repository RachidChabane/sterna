variable "hcloud_token" {
  description = "Hetzner Cloud API token"
  type        = string
  sensitive   = true
}

variable "ssh_public_keys" {
  description = "SSH public keys allowed on cluster nodes"
  type        = list(string)
}

variable "operator_ssh_allow_cidrs" {
  description = "Source CIDRs allowed to reach SSH+API on the CP public IP"
  type        = list(string)
  default     = []
}
