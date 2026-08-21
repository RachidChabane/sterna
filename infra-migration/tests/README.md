# infra-migration tests

Two test families live under `infra-migration/tests/`. They run in
separate CI jobs because they have very different dependency footprints.

## Terraform tests

- See `terraform/README.md`.
- Run via the `terraform.yml` workflow.
- Heavy: needs Terraform installed; some tests run real-ish plan
  cycles against module fixtures.

## Runbook-lint tests

- See `test_runbook.py`.
- Run via the `runbook-lint` job in `.github/workflows/ci.yml`.
- Light: just `pip install pytest==8.3.4` and `pytest` — no
  Terraform, no Django, no DB.
- Lints `docs/migration/cold-bring-up-runbook.md` for the per-step
  `**Verify:**` invariant + contiguous step numbering + no TODO/FIXME.

## How to run locally

```bash
# Runbook lint only (fast):
pip install pytest==8.3.4
pytest infra-migration/tests/test_runbook.py -v

# Terraform tests:
# (see terraform/README.md — has its own toolchain prerequisites)
```

Adding a new test file under `infra-migration/tests/` (e.g.,
`test_kustomize.py` for kustomize-build-on-CI) — wire it into the
runbook-lint job in `ci.yml` if it has the same lightweight
dependency profile. Heavy tests should get their own job, like
Terraform.
