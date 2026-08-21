# Scaleway Kapsule - Managed Kubernetes Cluster

resource "scaleway_k8s_cluster" "main" {
  name    = local.cluster_name
  version = var.kapsule_config.kubernetes_version
  cni     = var.kapsule_config.cni
  region  = var.region
  tags    = local.common_tags

  # Use private network for internal communication
  private_network_id = scaleway_vpc_private_network.main.id

  # Delete additional resources when cluster is deleted
  delete_additional_resources = true

  # Auto-upgrade settings
  auto_upgrade {
    enable                        = true
    maintenance_window_start_hour = 3 # 3 AM
    maintenance_window_day        = "sunday"
  }

  # Autoscaler configuration
  autoscaler_config {
    disable_scale_down               = false
    scale_down_delay_after_add       = "5m"
    scale_down_unneeded_time         = "5m"
    estimator                        = "binpacking"
    expander                         = "random"
    ignore_daemonsets_utilization    = true
    balance_similar_node_groups      = true
    expendable_pods_priority_cutoff  = -10
    scale_down_utilization_threshold = 0.5
    max_graceful_termination_sec     = 600
  }

  # Feature gates for advanced features
  feature_gates = [
    "HPAScaleToZero"
  ]

  # Admission plugins - PSP removed in K8s 1.25+, using Pod Security Admission instead
  admission_plugins = []
}

# Node pools for the Kapsule cluster
resource "scaleway_k8s_pool" "pools" {
  for_each = { for idx, pool in var.kapsule_config.node_pools : pool.name => pool }

  cluster_id  = scaleway_k8s_cluster.main.id
  name        = each.value.name
  node_type   = each.value.node_type
  size        = each.value.size
  min_size    = each.value.min_size
  max_size    = each.value.max_size
  autoscaling = each.value.autoscaling
  autohealing = true
  region      = var.region
  zone        = var.zone
  tags        = local.common_tags

  # Container runtime
  container_runtime = "containerd"

  # Upgrade policy
  upgrade_policy {
    max_surge       = 1
    max_unavailable = 1
  }

  # Wait for pool to be ready
  wait_for_pool_ready = true
}

# Kubeconfig data source
data "scaleway_k8s_cluster" "main" {
  cluster_id = scaleway_k8s_cluster.main.id
  region     = var.region
}
