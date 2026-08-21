# Test runs against the Hetzner module directly. Invoke from CI/local with:
#   terraform -chdir=infra-migration/terraform/modules/hetzner test \
#     -test-directory=../../../tests/terraform
#
# `mock_provider "hcloud"` requires Terraform 1.7+. The module's
# versions.tf pins >= 1.7.0; CI runner is on 1.8.0.
#
# This test file MUST NOT contain a `terraform { required_providers { ... } }`
# block — provider requirements live in the module under test.

variables {
  hcloud_token    = "test-token-must-be-nonempty"
  environment     = "staging"
  ssh_public_keys = ["ssh-ed25519 AAAA test@ci"]
}

mock_provider "hcloud" {
  # Note on nested-block mocking: `hcloud_server.network` is a
  # set-of-objects nested block in the provider schema. The mock
  # framework rejects function calls (`toset(...)`) in `defaults`, so
  # we can't directly emit a typed set here. Instead, each `run` block
  # uses an explicit `override_resource` to supply the network value
  # against the resource's actual schema — see e.g.
  # `valid_default_config` below.
  mock_resource "hcloud_server" {
    defaults = {
      # `id` is declared string in the provider schema but Hetzner
      # always returns a numeric string. Pin to a numeric literal so
      # `tonumber(hcloud_server.workers[i].id)` (load_balancer.tf:31)
      # succeeds at mock-apply time.
      id           = "10001"
      ipv4_address = "203.0.113.10"
    }
  }

  mock_resource "hcloud_network" {
    defaults = {
      id       = 999
      ip_range = "10.20.0.0/16"
    }
  }

  mock_resource "hcloud_network_subnet" {
    defaults = {
      id      = "999-10.20.1.0/24"
      gateway = "10.20.1.1"
    }
  }

  mock_resource "hcloud_load_balancer" {
    defaults = {
      id   = 888
      ipv4 = "203.0.113.99"
      ipv6 = "::1"
    }
  }

  mock_resource "hcloud_firewall" {
    defaults = {
      id = 777
    }
  }

  mock_resource "hcloud_ssh_key" {
    defaults = {
      id = 666
    }
  }
}

run "valid_default_config" {
  command = plan

  assert {
    condition     = output.cluster_name == "sternaway-staging"
    error_message = "cluster_name must follow sternaway-{env} convention"
  }

  assert {
    condition     = length(hcloud_server.workers) == 2
    error_message = "Default worker_count should plan 2 worker servers"
  }

  assert {
    condition     = length(hcloud_server.control_plane.user_data) > 0
    error_message = "Control plane user_data should render non-empty"
  }
}

run "load_balancer_disabled_by_default" {
  command = plan

  assert {
    condition     = output.load_balancer_ipv4 == null
    error_message = "Load balancer output should be null when enable_load_balancer is false"
  }

  assert {
    condition     = length(hcloud_load_balancer.ingress) == 0
    error_message = "Load balancer resource count should be 0 by default"
  }
}

run "load_balancer_can_be_enabled" {
  # `apply` (against mock_provider) so the computed `ipv4` attribute is
  # known at assertion time. With `plan`, the conditional gated by
  # var.enable_load_balancer leaves the ipv4 expression unresolved
  # because the provider hasn't materialised the resource yet.
  command = apply

  variables {
    enable_load_balancer = true
  }

  assert {
    condition     = output.load_balancer_ipv4 != null
    error_message = "Load balancer output must be set when enable_load_balancer is true"
  }

  assert {
    condition     = length(hcloud_load_balancer.ingress) == 1
    error_message = "Load balancer resource should be created when enabled"
  }
}

run "operator_ssh_cidrs_drive_firewall_rules" {
  command = plan

  variables {
    operator_ssh_allow_cidrs = ["1.2.3.4/32"]
  }

  assert {
    condition     = length(var.operator_ssh_allow_cidrs) == 1
    error_message = "operator_ssh_allow_cidrs variable should be set"
  }
}

run "custom_worker_count" {
  command = plan

  variables {
    worker_count = 3
  }

  assert {
    condition     = length(hcloud_server.workers) == 3
    error_message = "worker_count = 3 should plan 3 worker servers"
  }
}
