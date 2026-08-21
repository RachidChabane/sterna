terraform {
  required_version = ">= 1.7.0"

  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.48"
    }
  }
}

module "hetzner" {
  source = "../../modules/hetzner"

  environment              = "staging"
  hcloud_token             = var.hcloud_token
  ssh_public_keys          = var.ssh_public_keys
  operator_ssh_allow_cidrs = var.operator_ssh_allow_cidrs

  # cx43 (8 shared vCPU / 16 GB, ~16 EUR/mo) instead of ccx23: Hetzner's
  # June 2026 repricing put new ccx23 orders at ~55-65 EUR/mo. CAUTION:
  # changing server_type on an ALREADY-provisioned cluster makes terraform
  # replace the nodes (and re-provisioned nodes pay new prices) — review
  # the plan before applying against existing infrastructure.
  control_plane_type = "cx43"
  worker_type        = "cx43"
  worker_count       = 2

  install_gvisor = true

  tags = {
    "cost-center" = "engineering"
  }
}
