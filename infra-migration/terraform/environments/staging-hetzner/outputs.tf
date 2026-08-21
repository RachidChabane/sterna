output "control_plane_public_ip" {
  description = "Public IPv4 of the k3s control plane"
  value       = module.hetzner.control_plane_public_ip
}

output "control_plane_private_ip" {
  description = "Private IPv4 of the k3s control plane"
  value       = module.hetzner.control_plane_private_ip
}

output "worker_public_ips" {
  description = "Public IPs of worker nodes (debugging only — firewalled)"
  value       = module.hetzner.worker_public_ips
}

output "network_id" {
  description = "Hetzner private network ID"
  value       = module.hetzner.network_id
}

output "k3s_api_endpoint" {
  description = "k3s API endpoint"
  value       = module.hetzner.k3s_api_endpoint
}

output "k3s_join_token" {
  description = "k3s join token (sensitive)"
  value       = module.hetzner.k3s_join_token
  sensitive   = true
}
