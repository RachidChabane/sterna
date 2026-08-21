# Optional Hetzner Load Balancer in front of the in-cluster ingress.
# Disabled by default — the cluster uses Cloudflare Tunnel
# (kubernetes/base/cloudflare-tunnel/) for public traffic, which hides
# the cluster IP and avoids the recurring LB charge. Enable by setting
# var.enable_load_balancer = true; future tasks may use this to expose
# the k8s API for external kubectl.

resource "hcloud_load_balancer" "ingress" {
  count = var.enable_load_balancer ? 1 : 0

  name               = "${local.cluster_name}-ingress"
  load_balancer_type = "lb11"
  location           = var.location
  labels             = merge(local.common_labels, var.tags)
}

resource "hcloud_load_balancer_network" "ingress" {
  count = var.enable_load_balancer ? 1 : 0

  load_balancer_id = hcloud_load_balancer.ingress[0].id
  network_id       = hcloud_network.main.id
}

resource "hcloud_load_balancer_target" "ingress_workers" {
  count = var.enable_load_balancer ? var.worker_count : 0

  type             = "server"
  load_balancer_id = hcloud_load_balancer.ingress[0].id
  # `hcloud_server.id` is string in the provider schema but
  # `hcloud_load_balancer_target.server_id` expects number — cast.
  server_id      = tonumber(hcloud_server.workers[count.index].id)
  use_private_ip = true

  depends_on = [hcloud_load_balancer_network.ingress]
}

resource "hcloud_load_balancer_service" "https" {
  count = var.enable_load_balancer ? 1 : 0

  load_balancer_id = hcloud_load_balancer.ingress[0].id
  protocol         = "tcp"
  listen_port      = 443
  destination_port = 443
}
