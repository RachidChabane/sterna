variable "hcloud_token" {
  description = "Hetzner Cloud API token (write scope)"
  type        = string
  sensitive   = true
}

variable "environment" {
  description = "Environment name (staging, production)"
  type        = string
}

variable "location" {
  description = "Hetzner datacenter location"
  type        = string
  default     = "nbg1"
}

# Hetzner's June 2026 repricing raised dedicated-vCPU CCX lines 113-169%
# for NEW orders (ccx23 went from ~24 EUR to an estimated 55-65 EUR/mo);
# shared-vCPU CX gives the same RAM for a fraction of the price. Servers
# provisioned before the repricing keep their old price — do not rescale
# them casually. Set these back to a CCX type only if dedicated cores are
# demonstrably needed.
variable "control_plane_type" {
  description = "Server type for the k3s control plane (cx43: 8 shared vCPU, 16 GB)"
  type        = string
  default     = "cx43"
}

variable "worker_type" {
  description = "Server type for k3s workers (cx43: 8 shared vCPU, 16 GB)"
  type        = string
  default     = "cx43"
}

variable "worker_count" {
  description = "Number of k3s worker nodes"
  type        = number
  default     = 2
}

variable "ssh_public_keys" {
  description = "SSH public keys allowed on cluster nodes (operator access)"
  type        = list(string)
}

variable "operator_ssh_allow_cidrs" {
  description = "Source CIDRs allowed to reach SSH (22) and k8s API (6443) on the CP public IP"
  type        = list(string)
  default     = []
}

variable "k3s_version" {
  description = "k3s version channel (e.g. v1.30, stable)"
  type        = string
  default     = "v1.30"
}

variable "private_network_cidr" {
  description = "CIDR for the Hetzner private network"
  type        = string
  default     = "10.20.0.0/16"
}

variable "private_subnet_cidr" {
  description = "Subnet inside the private network for cluster nodes"
  type        = string
  default     = "10.20.1.0/24"
}

variable "control_plane_private_ip" {
  description = "Static private IPv4 for the k3s control plane within private_subnet_cidr (must be inside the subnet; workers reach the API at https://<ip>:6443)"
  type        = string
  default     = "10.20.1.10"
}

variable "enable_load_balancer" {
  description = "If true, provision an hcloud_load_balancer for ingress (default: false; we use Cloudflare Tunnel)"
  type        = bool
  default     = false
}

variable "install_gvisor" {
  description = "Install gVisor (runsc) on worker nodes and label them with sternaway.ai/gvisor=true"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Additional labels to apply to all Hetzner resources"
  type        = map(string)
  default     = {}
}
