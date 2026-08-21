output "cluster_name" {
  description = "k3s cluster name"
  value       = local.cluster_name
}

output "control_plane_public_ip" {
  description = "Public IPv4 of the k3s control plane (for SSH/kubectl)"
  value       = hcloud_server.control_plane.ipv4_address
}

output "control_plane_private_ip" {
  description = "Private IPv4 of the k3s control plane (for worker join)"
  value       = var.control_plane_private_ip
}

output "worker_public_ips" {
  description = "Public IPs of worker nodes (debugging only — firewalled)"
  value       = [for s in hcloud_server.workers : s.ipv4_address]
}

# `worker_private_ips` is omitted from outputs because the workers
# don't get a pinned private IP at plan time — they pick the next
# available address from the subnet at apply. Use `hcloud-cli` or the
# kubernetes node list to inspect after apply.

output "network_id" {
  description = "Hetzner private network ID"
  value       = hcloud_network.main.id
}

output "k3s_api_endpoint" {
  description = "k3s API endpoint (use over SSH tunnel from operator)"
  value       = local.k3s_api_endpoint
}

output "k3s_join_token" {
  description = "k3s join token (do not log; bootstrapped into nodes via cloud-init)"
  value       = random_password.k3s_token.result
  sensitive   = true
}

output "load_balancer_ipv4" {
  description = "Public IPv4 of the Hetzner load balancer (null if disabled)"
  value       = var.enable_load_balancer ? hcloud_load_balancer.ingress[0].ipv4 : null
}
