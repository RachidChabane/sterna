# Bootstrap-staging kustomization

Post-Terraform bootstrap for a cold Hetzner cluster. Applied via:

```bash
kubectl apply -k infra-migration/kubernetes/base/bootstrap-staging/
```

## What it does

Aggregates:

1. `namespace.yaml` — creates the `sterna` Namespace. This is a
   local copy of `../namespace.yaml`, kept in sync by hand. The
   duplicate is needed because kustomize's default load restrictor
   (`LoadRestrictionsRootOnly`) forbids referencing files in a parent
   directory; only sibling directories are allowed.
2. `../hetzner-cloud/` — applies the Hetzner CCM + CSI manifests
   (clears the `uninitialized` taint, enables volume provisioning).
   Sibling directory; allowed under the default load restrictor.

That's it. Nothing else.

**Sync caveat**: if `../namespace.yaml` ever gains labels, annotations,
or finalizers, mirror the change into this directory's
`namespace.yaml`. Both files are short and rarely change.

## Apply order

1. `terraform apply` of `environments/staging-hetzner/`.
2. **This kustomization** — sterna namespace + CCM + CSI.
3. `helm upgrade --install external-secrets …` — ESO controller +
   CRDs.
4. `kubectl apply -k ../external-secrets/` — SecretStore +
   ExternalSecret manifests now that the CRDs exist.

The full operator-facing flow is documented in
`docs/migration/cold-bring-up-runbook.md` §F.1.c.

## Why the namespace is included here

Subsequent runbook steps create k8s objects with `-n sterna` before
the base overlay's full apply runs. Without the namespace already
present, those steps fail with `namespaces 'sterna' not found`.
Including `namespace.yaml` here keeps each runbook step a single
declarative `kubectl apply -k`.

## Why NOT external-secrets

The `../external-secrets/` directory defines `ExternalSecret` and
`SecretStore` resources. Their CRDs are installed by the ESO Helm
chart (runbook step 5). If we bundled them here, the first apply
would fail with:

```
no matches for kind "ExternalSecret" in version
"external-secrets.io/v1"
```

…because the CRDs do not yet exist at bootstrap-time. Two-step
ordering avoids the chicken-and-egg loop. Cross-link: runbook §F.1.c
steps 4–6 for the full sequence.

## Why no cert-manager + ingress-nginx

- **cert-manager**: TLS terminates at Cloudflare. The cluster has no
  certificates to manage, so installing cert-manager would add attack
  surface, controller CPU/memory cost, and CRDs nothing references.
- **ingress-nginx**: the ingress is `cloudflare-tunnel/deployment.yaml`
  — a cloudflared pod that dials out to the Cloudflare edge. There
  is no in-cluster nginx routing.

YAGNI. If a future deployment grows a direct-LB ingress path, revisit.

## Failure modes

- **CCM stuck Pending**: check the `hcloud` secret in `kube-system`
  was created with the right token/network. See `../hetzner-cloud/
  README.md` for the secret payload shape.
- **`kubectl apply -k …/hetzner-cloud` complains "unable to find
  kustomization.yaml"**: the `hetzner-cloud/kustomization.yaml`
  (also added in task 28) must be present. Check `git log -- infra-
  migration/kubernetes/base/hetzner-cloud/kustomization.yaml`.
- **Re-applying after the base overlay landed**: safe. Namespace
  and CCM/CSI are idempotent under `kubectl apply -k`.
