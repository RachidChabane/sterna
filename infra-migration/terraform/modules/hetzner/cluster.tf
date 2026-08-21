resource "hcloud_ssh_key" "operator" {
  for_each   = { for idx, k in var.ssh_public_keys : tostring(idx) => k }
  name       = "${local.cluster_name}-operator-${each.key}"
  public_key = each.value
  labels     = merge(local.common_labels, var.tags)
}

resource "hcloud_network" "main" {
  name     = "${local.cluster_name}-net"
  ip_range = var.private_network_cidr
  labels   = merge(local.common_labels, var.tags)
}

resource "hcloud_network_subnet" "main" {
  network_id   = hcloud_network.main.id
  type         = "cloud"
  network_zone = "eu-central"
  ip_range     = var.private_subnet_cidr
}

resource "hcloud_firewall" "cp" {
  name = "${local.cluster_name}-cp"

  dynamic "rule" {
    for_each = length(var.operator_ssh_allow_cidrs) > 0 ? ["ssh", "api"] : []
    content {
      direction  = "in"
      protocol   = "tcp"
      port       = rule.value == "ssh" ? "22" : "6443"
      source_ips = var.operator_ssh_allow_cidrs
    }
  }

  labels = merge(local.common_labels, var.tags)
}

resource "hcloud_firewall" "workers" {
  name   = "${local.cluster_name}-workers"
  labels = merge(local.common_labels, var.tags)
}

resource "hcloud_server" "control_plane" {
  name         = "${local.cluster_name}-cp"
  location     = var.location
  server_type  = var.control_plane_type
  image        = "ubuntu-24.04"
  ssh_keys     = [for k in hcloud_ssh_key.operator : k.id]
  firewall_ids = [hcloud_firewall.cp.id]

  user_data = templatefile("${path.module}/templates/k3s-server.sh.tftpl", {
    k3s_version    = var.k3s_version
    k3s_token      = random_password.k3s_token.result
    install_gvisor = var.install_gvisor
    private_cidr   = var.private_subnet_cidr
  })

  # Pin the CP's private IP so workers' `K3S_URL` is computable at plan
  # time (without reading the Set<object> `network` attribute that's
  # "known after apply"). The chosen IP must sit inside var.private_subnet_cidr.
  network {
    network_id = hcloud_network.main.id
    ip         = var.control_plane_private_ip
  }

  labels = merge(local.common_labels, var.tags, { role = "control-plane" })

  depends_on = [hcloud_network_subnet.main]
}

resource "hcloud_server" "workers" {
  count = var.worker_count

  name         = "${local.cluster_name}-worker-${count.index + 1}"
  location     = var.location
  server_type  = var.worker_type
  image        = "ubuntu-24.04"
  ssh_keys     = [for k in hcloud_ssh_key.operator : k.id]
  firewall_ids = [hcloud_firewall.workers.id]

  user_data = templatefile("${path.module}/templates/k3s-agent.sh.tftpl", {
    k3s_version    = var.k3s_version
    k3s_token      = random_password.k3s_token.result
    k3s_server_url = local.k3s_server_url
    install_gvisor = var.install_gvisor
    private_cidr   = var.private_subnet_cidr
  })

  network {
    network_id = hcloud_network.main.id
  }

  labels = merge(local.common_labels, var.tags, { role = "worker" })

  depends_on = [hcloud_server.control_plane]
}
