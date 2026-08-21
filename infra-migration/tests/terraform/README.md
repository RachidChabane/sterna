# Terraform module tests

Tests live in `*.tftest.hcl` files and run against the modules under
`../terraform/modules/`. They use Terraform's built-in test framework
(`terraform test`) and `mock_provider` blocks so plans don't touch the
real Hetzner Cloud API.

## Running tests locally

Tests live INSIDE the module under
`../terraform/modules/hetzner/tests/`. Terraform 1.7+ requires
`-test-directory` to be a relative path local to the configuration
directory, so we can't put the tests in this directory and point
across. The test file is committed in the module's tree; this
directory holds documentation only.

Run from the module root:

```bash
terraform -chdir=infra-migration/terraform/modules/hetzner init -backend=false
terraform -chdir=infra-migration/terraform/modules/hetzner test
```

Or, equivalently:

```bash
cd infra-migration/terraform/modules/hetzner
terraform init -backend=false
terraform test
```

## Requirements

- Terraform >= 1.7.0 (`mock_provider` is 1.7+ only). CI runner uses 1.8.0
  per `.github/workflows/terraform.yml`.
- No real Hetzner API token needed — tests pass a placeholder string;
  `mock_provider` intercepts all hcloud API calls.

## CI integration

`.github/workflows/terraform.yml` runs `terraform test` against the
Hetzner module on every PR and push that touches `infra-migration/`.

## Future work

- Add similar tests for the Scaleway module (`modules/scaleway`),
  which currently has none. Track in a follow-up task once the
  Hetzner migration stabilises.
- Extend the Hetzner test suite with negative cases (e.g. invalid
  `worker_count` values once we add variable validation).
