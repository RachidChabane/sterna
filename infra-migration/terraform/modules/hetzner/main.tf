provider "hcloud" {
  token = var.hcloud_token
}

locals {
  cluster_name = "sternaway-${var.environment}"
  common_labels = {
    "managed-by"  = "terraform"
    "project"     = "sternaway"
    "environment" = var.environment
  }
  # The CP gets a STATIC private IP (var.control_plane_private_ip,
  # default 10.20.1.10). Workers reach the API at this address; the
  # value is also passed into the cloud-init template that bootstraps
  # the workers. A static IP avoids reading from
  # `hcloud_server.control_plane.network` (a Set<object> attribute
  # whose `ip` is "known after apply"), which keeps the worker
  # user_data renderable at plan time and makes `terraform test`
  # against mock_provider deterministic.
  k3s_server_url = "https://${var.control_plane_private_ip}:6443"
}

resource "random_password" "k3s_token" {
  length  = 48
  special = false
}
