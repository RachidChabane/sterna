# infra-migration

Infrastructure as code for the Sterna platform: Terraform for cloud
resources, Kustomize for Kubernetes manifests. This document maps the
directory so the current-vs-legacy environment story is explicit.

## Directory map

```
infra-migration/
├── terraform/
│   ├── modules/          # Reusable, provider-scoped modules
│   └── environments/     # Environment root modules (compose the modules above)
├── kubernetes/
│   ├── base/              # Environment-agnostic manifests
│   ├── overlays/          # Per-environment Kustomize overlays
│   └── components/        # Reusable Kustomize components
├── scripts/                # Operational scripts (secret population, apply helpers)
├── tests/                  # Runbook lint + Terraform module tests
└── RUNBOOK.md               # Operational runbook for the Scaleway staging plane
```

## Terraform

### `terraform/modules/`

Provider-scoped, reusable modules — no environment-specific values, all
inputs are variables:

| Module | Purpose |
|---|---|
| `scaleway` | Kapsule (managed Kubernetes), container registry, Secret Manager, VPC |
| `cloudflare` | DNS, Tunnel, R2 bucket, WAF (environment-scoped) |
| `cloudflare-zone` | Zone-level WAF/rate-limiting (shared across environments — see below) |
| `neon`, `neon-project`, `neon-branch` | Neon Postgres project + per-environment branch |
| `hetzner` | Self-managed k3s cluster on Hetzner Cloud (cloud-init templates, gVisor) |
| `shared-secrets` | Secret Manager entries shared by every environment |

`modules/hetzner` carries native `terraform test` coverage
(`tests/hetzner_module.tftest.hcl`) using `mock_provider`, run in CI
without touching the real Hetzner API.

### `terraform/environments/`

Root modules that compose the modules above into a deployable stack.
Each has its own state (Cloudflare R2, S3-compatible backend) and its
own `variables.tf` / `terraform.tfvars.example`.

| Environment | Status | Notes |
|---|---|---|
| `shared` | **Current** | Zone-level Cloudflare WAF/rate-limiting + the single Neon project, applied once and read by `staging`/`production` via `terraform_remote_state`. |
| `staging` | **Current** | Scaleway Kapsule-backed staging cluster. The live, actively-deployed environment. |
| `staging-hetzner` | **Parallel migration target** | Self-managed k3s on Hetzner Cloud, applied alongside `staging` while the platform migrates off Scaleway Kapsule for cost reasons. See `docs/migration/hetzner.md`. |
| `_production_disabled` | **Parked** | Leading underscore is deliberate: this directory is excluded from Terraform's directory-based module discovery and from CI's terraform-apply-production job (see `.github/workflows/terraform.yml`). It held the Scaleway-Kapsule production design; production is being rebuilt Hetzner-backed per `docs/migration/cold-bring-up-runbook.md` before this is restored to an active `production/` directory. |

Root modules deliberately do **not** commit `import { }` blocks for
resource adoption: once a pre-existing resource has been imported into
state, Terraform's own guidance is to remove the import block from
configuration, since the block itself no longer changes plan output
and only exists as an audit trail. When adopting a new pre-existing
resource, run the import as a one-off command instead of committing
the resource ID to source:

```bash
terraform import module.<name>.<resource_type>.<name> <resource-id>
```

Resource IDs (Scaleway registry/IAM/secret UUIDs, Cloudflare tunnel
ID) are not committed to this tree; they live in each operator's
gitignored `terraform.tfvars` or are looked up via `scw`/`cloudflared`
at import time.

### Backend configuration

All environments use Cloudflare R2 as an S3-compatible Terraform
backend. The bucket, state key, and R2-compatibility flags
(`skip_*`, `use_path_style`) are committed in each `backend.tf` —
Terraform backend blocks cannot reference input variables, so the R2
account-scoped endpoint is a literal in this tree. Credentials for the
backend itself are supplied out-of-band as `AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY` (R2 API token), never committed.

## Kubernetes (`kubernetes/`)

Kustomize, structured as base/overlays/components:

- **`base/`** — one directory per service (Deployment, Service,
  ServiceAccount, HPA where relevant), plus cross-cutting concerns:
  `network-policies/` (default-deny + explicit allow rules),
  `external-secrets/` (SecretStore + ExternalSecret resources — see
  below), `backup/` (scheduled CronJob + restore-validation CronJob),
  `configmaps/`.
- **`overlays/staging/`, `overlays/production/`** — environment-specific
  patches: replica counts, resource limits, image tags/registry,
  service-name prefixing.
- **`overlays/production-external-secrets/`** — a standalone overlay
  that builds only the SecretStore/ExternalSecret manifests, applied
  during production cold bring-up before the CRDs the full overlay
  depends on exist. See `docs/migration/cold-bring-up-runbook.md`.
- **`components/production-secret-names/`** — a reusable Kustomize
  Component that rewrites every per-environment `remoteRef` from the
  `sternaway-staging-*` names baked into `base/` to their
  `sternaway-production-*` counterparts. Included by both production
  overlays above instead of duplicating the ExternalSecret manifests.

### Secrets flow

Kubernetes secrets are never committed. The `SecretStore` in
`base/external-secrets/secret-store.yaml` points External Secrets
Operator at Scaleway Secret Manager (region + project scoped); each
`ExternalSecret` in the same directory declares which Secret Manager
entry (`name:sterna-<env>-<group>-secrets`) backs which Kubernetes
Secret, refreshed hourly. The actual secret **values** live only in
Scaleway Secret Manager, populated via `scripts/populate-secrets-staging-v3.sh`
(reads from environment variables the operator sources locally — see
that script's header) or `scripts/apply-secrets.sh`.

`base/secrets/secrets-template.yaml` is a plain-Kubernetes-Secret
fallback template (pre-ExternalSecrets), kept for reference; the
`external-secrets/` path is what staging and production actually run.

## `scripts/`

- `apply-secrets.sh` — legacy path: creates plain Kubernetes Secrets
  directly via `kubectl create secret generic` from environment
  variables (pre-ExternalSecrets fallback, matching
  `base/secrets/secrets-template.yaml`).
- `populate-secrets-staging-v3.sh` — writes the actual secret values
  into Scaleway Secret Manager. Env-var-driven (no embedded
  credentials); see the script header for usage and rotation history.

## `tests/`

Two independent test families — see `tests/README.md`:

- `test_runbook.py` — lints `docs/migration/cold-bring-up-runbook.md`
  (numbered steps each carry a `**Verify:**` line, no TODO/FIXME left
  in an operator-facing document), run by the `runbook-lint` CI job.
- `terraform/` — documents the `modules/hetzner` `terraform test`
  suite (the test files themselves live inside that module, per
  Terraform 1.7+'s `-test-directory` constraint).

## RUNBOOK.md

Operational runbook for the Scaleway-Kapsule staging plane: bring-up,
backup/restore, and troubleshooting. Superseded in part by
`docs/migration/hetzner.md` and `docs/migration/cold-bring-up-runbook.md`
as the platform migrates to Hetzner; kept as the authority for the
not-yet-decommissioned Scaleway resources (Secret Manager, R2 state,
Cloudflare zones).
