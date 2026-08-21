# k3s configuration is delivered via cloud-init from cluster.tf
# (templates/k3s-server.sh.tftpl and k3s-agent.sh.tftpl). This file is a
# stub. CCM/CSI install is a post-apply step
# (see ../../kubernetes/base/hetzner-cloud/) so the module stays free
# of the kubernetes provider.
#
# The kubeconfig is retrievable via
#   ssh root@<cp-public-ip> 'cat /etc/rancher/k3s/k3s.yaml'
# after the cluster bootstraps; task 27 automates that retrieval and
# stores it as a workflow secret.

locals {
  k3s_api_endpoint = "https://${hcloud_server.control_plane.ipv4_address}:6443"
}
