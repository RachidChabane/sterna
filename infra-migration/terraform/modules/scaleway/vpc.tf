# Scaleway VPC (Private Network)

resource "scaleway_vpc" "main" {
  name   = "sternaway-vpc-${var.environment}"
  region = var.region
  tags   = local.common_tags
}

resource "scaleway_vpc_private_network" "main" {
  name   = "sternaway-private-${var.environment}"
  vpc_id = scaleway_vpc.main.id
  region = var.region
  tags   = local.common_tags

  ipv4_subnet {
    subnet = var.vpc_cidr
  }
}

# Public Gateway for internet egress from private network
# This enables pods in the private network to reach external services
resource "scaleway_vpc_public_gateway_ip" "main" {
  zone = var.zone
  tags = local.common_tags
}

resource "scaleway_vpc_public_gateway" "main" {
  name            = "sternaway-gateway-${var.environment}"
  type            = "VPC-GW-S" # Smallest size, sufficient for egress
  zone            = var.zone
  ip_id           = scaleway_vpc_public_gateway_ip.main.id
  bastion_enabled = false
  tags            = local.common_tags
}

# Connect the public gateway to the private network using IPAM (modern approach)
resource "scaleway_vpc_gateway_network" "main" {
  gateway_id         = scaleway_vpc_public_gateway.main.id
  private_network_id = scaleway_vpc_private_network.main.id
  enable_masquerade  = true # Enable NAT for internet access
  zone               = var.zone

  # Use IPAM instead of deprecated DHCP
  ipam_config {
    push_default_route = true # This ensures pods get the default route via gateway
  }
}
