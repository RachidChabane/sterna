<!--
This runbook is verified by infra-migration/tests/test_runbook.py.
Every numbered step MUST contain a "**Verify:**" line. Adding a step
without one fails CI.

Step heading format is strict (regex in test_runbook.py):
    ### Step N — <title>     (em-dash; level-3 heading)
Each section's step numbering MUST be contiguous (1..N, no gaps).
Two parallel numberings are allowed because the staging and
production sections restart at 1.
-->

# Cold bring-up runbook — Hetzner cluster

**Status**: DRAFT (no live cutover yet)
**Author**: Sterna infra
**Date**: 2026-05-23

This runbook walks an operator from `terraform apply` to "DNS
flipped, smoke green" on a freshly provisioned Hetzner cluster,
end-to-end. See `infra-migration/README.md` for the module layout
and secrets flow this runbook drives.

The same flow applies to a parallel **production** bring-up (§ F.1.d);
the differences are called out per-step.

---

## Pre-conditions

These are prerequisites operators check BEFORE starting. They are NOT
numbered steps and do not require verify lines.

- [ ] Hetzner project created; `HCLOUD_TOKEN` in repo secrets.
- [ ] SSH key in `HETZNER_SSH_KEYS_JSON`; operator IP in
      `HETZNER_OPERATOR_CIDRS_JSON`.
- [ ] Scaleway Secret Manager populated (see
      `infra-migration/README.md` for how).
- [ ] ESO API keys set: `ESO_ACCESS_KEY`, `ESO_SECRET_KEY`.
- [ ] GHCR write token in `GITHUB_TOKEN` (default); GHCR pull token
      in `GHCR_PULL_TOKEN`.
- [ ] Cloudflare zone token in `CLOUDFLARE_API_TOKEN`; tunnel token
      in `CLOUDFLARE_TUNNEL_TOKEN`.
- [ ] Neon DB exists; `NEON_DATABASE_URL_STAGING` in Scaleway
      Secret Manager.
- [ ] `SMOKE_TEST_USER_PASSWORD` set (16+ chars) in Scaleway
      Secret Manager AND mirrored to repo secrets (so the deploy
      workflow's pytest container can read it).
- [ ] `SMOKE_STRIPE_WEBHOOK_SECRET` in Scaleway Secret Manager
      (Stripe webhook signing key; test mode for staging, live mode
      for prod). Optional — if unset, smoke test #5 (webhook) skips
      cleanly both in-cluster and runner-side.
- [ ] Optional: `vars.PRODUCTION_SKIP_SMOKE_USER=true` set as a
      GitHub Actions **repository variable** (not secret — uses the
      `vars` context) if the prod policy disallows the smoke user.
      Unset / "false" → `seed_smoke_user` runs in prod (the default).
      Only relevant in prod; ignored by staging.

---

## Why no cert-manager and ingress-nginx

The task description lists "cert-manager + ingress-nginx" alongside
CCM + CSI as bootstrap components. Neither is installed in this
runbook on purpose:

- **cert-manager**: TLS terminates at Cloudflare. There are no
  in-cluster certificates to manage. Installing it would add a
  controller + CRDs nothing references.
- **ingress-nginx**: The cluster's ingress is
  `cloudflare-tunnel/deployment.yaml` — a cloudflared pod that
  dials out to the Cloudflare edge. No in-cluster nginx routing.

YAGNI. Revisit if a future deployment grows a direct-LB ingress
path.

---

## F.1.c — Staging cold bring-up

### Step 1 — Terraform apply (staging-hetzner)

**Run:**
```bash
terraform -chdir=infra-migration/terraform/environments/staging-hetzner apply
```

**Verify:**
```bash
terraform -chdir=infra-migration/terraform/environments/staging-hetzner \
  output -raw control_plane_public_ip
```
Returns an IPv4 address. (Output name is `control_plane_public_ip`,
not `cp_public_ip`.)

### Step 2 — Retrieve kubeconfig + write to repo secret

**Run:**
```bash
CP_IP=$(terraform -chdir=infra-migration/terraform/environments/staging-hetzner \
  output -raw control_plane_public_ip)
ssh root@$CP_IP cat /etc/rancher/k3s/k3s.yaml \
  | sed "s/127.0.0.1/$CP_IP/" \
  > /tmp/staging-kubeconfig
base64 -w 0 < /tmp/staging-kubeconfig
# Paste the base64 output into GitHub Actions secret
# KUBECONFIG_HETZNER_STAGING.
```

**Verify:**
```bash
kubectl --kubeconfig /tmp/staging-kubeconfig get nodes
```
Returns at least one node (likely `NotReady` until step 4 lands
CCM).

### Step 3 — Wait for nodes to register (NotReady is expected)

**Run:**
```bash
kubectl get nodes -w
# Ctrl-C when all expected nodes appear (NotReady is fine here).
```

**Verify:**
```bash
kubectl get nodes -o jsonpath='{.items[*].metadata.name}'
```
Shows the expected node count (1 CP + N workers for staging).

### Step 4 — Install sterna namespace + CCM + CSI via bootstrap-staging kustomization

**Run:**
```bash
kubectl create secret generic hcloud -n kube-system \
  --from-literal=token="$HCLOUD_TOKEN" \
  --from-literal=network="$(terraform -chdir=infra-migration/terraform/environments/staging-hetzner output -raw network_id)"
kubectl apply -k infra-migration/kubernetes/base/bootstrap-staging/
```

This bootstrap kustomization creates the `sterna` namespace + CCM +
CSI only. The namespace must exist before step 5's
`kubectl create secret -n sterna` and step 6's ExternalSecret
apply. ExternalSecret manifests are applied separately in step 6
after ESO Helm installs the CRDs (see "Why two steps for secrets"
in `bootstrap-staging/README.md`).

**Verify:**
```bash
kubectl get namespace sterna -o jsonpath='{.status.phase}'
# → Active
kubectl get nodes
# → all Ready (CCM cleared the uninitialized taint)
```

### Step 5 — Install External Secrets Operator (Helm)

**Run:**
```bash
kubectl create secret generic scaleway-credentials -n sterna \
  --from-literal=access-key="$ESO_ACCESS_KEY" \
  --from-literal=secret-key="$ESO_SECRET_KEY"

helm repo add external-secrets https://charts.external-secrets.io
helm repo update
helm upgrade --install external-secrets \
  external-secrets/external-secrets \
  --namespace external-secrets \
  --create-namespace \
  --version 0.10.5 \
  --wait
```

Use the exact version pinned by the deploy workflow so the
controller stays in lockstep.

**Verify:**
```bash
kubectl get pods -n external-secrets
# → external-secrets-* Running
kubectl api-resources | grep external-secrets.io
# → ExternalSecret, SecretStore CRDs listed
```

### Step 6 — Apply SecretStore + ExternalSecret manifests

**Run:**
```bash
kubectl apply -k infra-migration/kubernetes/base/external-secrets/
```

**Verify:**
```bash
kubectl get externalsecrets -n sterna \
  -o jsonpath='{.items[*].status.conditions[?(@.type=="Ready")].status}'
```
Returns only `True` values (no `False`). This is a fresh apply —
the CRDs only exist as of step 5.

### Step 7 — Wait for all ExternalSecrets to reach SecretSynced

**Run:**
```bash
kubectl wait --for=condition=Ready externalsecrets --all \
  -n sterna --timeout=300s
```

**Verify:**
```bash
kubectl get secrets -n sterna
```
Lists the expected populated secrets (`api-secrets`,
`database-secrets`, `redis-credentials`, `stripe`, `llm-secrets`,
`smoke-secrets`, …).

### Step 8 — Apply the rest of the kustomize base + staging overlay

The overlay is NOT applyable as checked in: the
`patches/image-pull-secret.yaml` patch carries a `__SECRET_NAME__`
placeholder and the `images:` block points at the legacy Scaleway
registry — both are normally rewritten by
`.github/workflows/deploy-staging.yml`. When applying by hand,
perform the same three rewrites first.

**Run:**
```bash
# 1. Create the GHCR image-pull secret the deployments reference.
#    GHCR_OWNER must be the LOWERCASED GitHub org/user (Docker rejects
#    mixed-case namespaces); GHCR_PULL_TOKEN is a read:packages PAT
#    (see infra-migration/README.md for how repo secrets are populated).
GHCR_OWNER="<lowercased-github-owner>"
kubectl create secret docker-registry ghcr-registry \
  --docker-server=ghcr.io \
  --docker-username="$GHCR_OWNER" \
  --docker-password="$GHCR_PULL_TOKEN" \
  -n sterna --dry-run=client -o yaml | kubectl apply -f -

# 2. Resolve the imagePullSecrets placeholder to the secret above.
sed -i "s/__SECRET_NAME__/ghcr-registry/g" \
  infra-migration/kubernetes/overlays/staging/patches/image-pull-secret.yaml

# 3. Point all nine service images at GHCR (same mapping the deploy
#    workflow performs; TAG is normally develop-latest for staging).
TAG="develop-latest"
cd infra-migration/kubernetes/overlays/staging
kustomize edit set image \
  ghcr.io/sterna-ai/api-gateway=ghcr.io/${GHCR_OWNER}/sterna-api-gateway:${TAG} \
  ghcr.io/sterna-ai/web=ghcr.io/${GHCR_OWNER}/sterna-web:${TAG} \
  ghcr.io/sterna-ai/frontend=ghcr.io/${GHCR_OWNER}/sterna-frontend:${TAG} \
  ghcr.io/sterna-ai/orchestrator=ghcr.io/${GHCR_OWNER}/sterna-orchestrator:${TAG} \
  ghcr.io/sterna-ai/sandbox-datascience=ghcr.io/${GHCR_OWNER}/sterna-sandbox-datascience:${TAG} \
  ghcr.io/sterna-ai/egress-proxy=ghcr.io/${GHCR_OWNER}/sterna-egress-proxy:${TAG} \
  ghcr.io/sterna-ai/brave-search=ghcr.io/${GHCR_OWNER}/sterna-brave-search:${TAG} \
  ghcr.io/sterna-ai/user-preferences=ghcr.io/${GHCR_OWNER}/sterna-user-preferences:${TAG} \
  ghcr.io/sterna-ai/google-maps=ghcr.io/${GHCR_OWNER}/sterna-google-maps:${TAG}
cd -

# 4. Build + apply.
kustomize build infra-migration/kubernetes/overlays/staging \
  | kubectl apply -f -
```

Do NOT commit the `sed` / `kustomize edit` rewrites — they are
working-tree-only, exactly like in the deploy workflow
(`git checkout -- infra-migration/kubernetes/overlays/staging`
afterwards).

**Verify:**
```bash
kustomize build infra-migration/kubernetes/overlays/staging \
  | grep -E "__SECRET_NAME__|rg\.fr-par\.scw\.cloud" || echo "rewrites OK"
kubectl get deployments -n sterna
```
The grep prints nothing (no unresolved placeholder, no Scaleway
registry paths left) and all expected deployments are created (not
yet Ready — that's step 9).

### Step 9 — Wait for all Deployments to be Ready

**Run:**
```bash
for d in $(kubectl get deployments -n sterna \
    -o jsonpath='{.items[*].metadata.name}'); do
  kubectl rollout status deployment/$d -n sterna --timeout=300s
done
```

**Verify:**
```bash
kubectl get deployments -n sterna -o jsonpath='{range .items[*]}{.metadata.name}: {.status.readyReplicas}/{.spec.replicas}{"\n"}{end}'
```
Every line shows `readyReplicas == spec.replicas`.

### Step 10 — Verify the Cloudflare Tunnel is connected

**Run:**
```bash
kubectl logs -n sterna deployment/staging-cloudflare-tunnel \
  | grep -i "Registered tunnel connection" \
  | head -5
```
The tunnel pod is created by step 8's overlay apply; this step
just confirms it dialed out to the edge.

**Verify:**
```bash
kubectl logs -n sterna deployment/staging-cloudflare-tunnel \
  | grep -E "Registered tunnel connection|Connection [a-z0-9-]+ registered"
```
Returns at least one connection line. (Or `cloudflared tunnel info
<tunnel-name>` shows >=1 connector.)

### Step 11 — Seed data: re-apply seed_all in the web pod

**Run:**
```bash
POD=$(kubectl get pods -n sterna -l app=web \
  -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n sterna "$POD" -- python manage.py seed_all
```

The web pod inherits `SMOKE_TEST_USER_PASSWORD` from its Deployment
env (fed by the `smoke-secrets` ExternalSecret — see Group E in
the task-28 plan). No `-e` flag on `kubectl exec`; that flag does
not exist.

**Verify:** the command exits zero; the final stdout line is
`seed_all: all steps OK`.

### Step 12 — Run smoke suite from inside the web pod (in-cluster)

**Run:**
```bash
POD=$(kubectl get pods -n sterna -l app=web \
  -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n sterna "$POD" -- bash -c '
  SMOKE_BASE_URL=http://staging-web.sterna.svc.cluster.local:8000 \
  python -m pytest smoke/ -v --tb=short
'
```

`SMOKE_TEST_USER_PASSWORD` and `SMOKE_STRIPE_WEBHOOK_SECRET` come
from the pod env via the `smoke-secrets` ExternalSecret; only
`SMOKE_BASE_URL` is overridden inline (in-cluster service URL).
The in-pod pytest uses `core/pytest.ini` — pytest-django is
installed in the web image, so `--reuse-db` is OK there.

**Verify:** all smoke tests pass (or skip cleanly for missing
optional env vars — e.g., the Stripe webhook test skips if
`SMOKE_STRIPE_WEBHOOK_SECRET` was intentionally left out of the
Scaleway payload).

### Step 13 — Flip DNS in Cloudflare

**Run:** (manual one-shot)

1. Log into Cloudflare → DNS for `<your-domain>`.
2. Update the `staging` CNAME to point at the new tunnel hostname
   (`<tunnel-id>.cfargotunnel.com`).

**Verify:**
```bash
dig +short staging.<your-domain>
# From a network OUTSIDE the cluster:
curl -sf https://staging.<your-domain>/livez
```
Returns 200.

### Step 14 — Run smoke suite against the public URL (final gate)

**Run:** from a local workstation (NOT inside the cluster):
```bash
cd core
pip install pytest==8.3.4 httpx==0.28.1
SMOKE_BASE_URL=https://staging.<your-domain> \
SMOKE_TEST_USER_PASSWORD="$SMOKE_TEST_USER_PASSWORD" \
pytest -c /dev/null smoke/ -v --tb=short
```

`-c /dev/null` bypasses `core/pytest.ini` because
`addopts = … --reuse-db` requires pytest-django, which is not
installed on the workstation. The `smoke` marker is registered
inside `core/smoke/conftest.py` via `pytest_configure`, so the
suite works in either mode.

**Verify:** all smoke tests pass.

---

## F.1.d — Production cold bring-up

> **Prerequisite (NOT in scope for task 28):** create
> `infra-migration/terraform/environments/production-hetzner/`.
> Template from `staging-hetzner/main.tf` with these var overrides:
> `enable_load_balancer = true`, `control_plane_count = 3` (HA),
> `worker_count = 3`. Open the production env as a separate PR after
> staging has been stable for ≥7 consecutive days.

The production flow mirrors §F.1.c step-for-step. Differences:

### Step 1 — Terraform apply (production-hetzner)

**Run:**
```bash
terraform -chdir=infra-migration/terraform/environments/production-hetzner apply
```
tfvars must include `enable_load_balancer = true`,
`control_plane_count = 3`, `worker_count = 3`.

**Verify:** kubeconfig output points at the LB IP, not a single CP.

### Step 2 — Retrieve kubeconfig pinned to LB IP

**Run:** copy `/etc/rancher/k3s/k3s.yaml` from any CP and edit the
`server:` field to the LB IPv4 (NOT a CP's IP — survives CP
failover). Paste base64 into `KUBECONFIG_HETZNER_PRODUCTION`.

**Verify:**
```bash
kubectl --kubeconfig /tmp/prod-kubeconfig get nodes
```
Returns 3 CPs + 3 workers.

### Step 3 — Wait for nodes to register

**Run:** `kubectl get nodes -w` until 6 nodes appear.

**Verify:**
```bash
kubectl get nodes -o jsonpath='{.items[*].metadata.name}' | wc -w
```
Returns `6`.

### Step 4 — Bootstrap: sterna namespace + CCM + CSI

**Run:**
```bash
kubectl create secret generic hcloud -n kube-system \
  --from-literal=token="$HCLOUD_TOKEN_PROD" \
  --from-literal=network="$(terraform -chdir=infra-migration/terraform/environments/production-hetzner output -raw network_id)"
kubectl apply -k infra-migration/kubernetes/base/bootstrap-staging/
```
(Same bootstrap kustomization is reused; it is environment-agnostic.)

**Verify:** namespace `Active`; all 6 nodes `Ready`.

### Step 5 — Install ESO (Helm)

**Run:** same as staging step 5, but with prod credentials
(`scaleway-credentials` secret values).

**Verify:** ESO controller `Running`; CRDs listed.

### Step 6 — Apply production ExternalSecret manifests

**Run:**
```bash
kubectl apply -k infra-migration/kubernetes/overlays/production-external-secrets/
```

This kustomization builds ONLY the SecretStore + ExternalSecrets,
with the production names (`production-` prefix,
`sterna-production-*` remoteRefs). It exists precisely because
the base manifests reference the staging-named Scaleway secrets.
The `sterna-production-*` secrets must already exist in Scaleway
Secret Manager — see `infra-migration/README.md` for the full list.

**Verify:** all ExternalSecrets have `Ready=True`, and:
```bash
kubectl get externalsecrets -n sterna -o yaml \
  | grep "sterna-staging-" || echo "no staging refs — OK"
```
prints `no staging refs — OK`.

### Step 7 — Wait for SecretSynced

**Run:**
```bash
kubectl wait --for=condition=Ready externalsecrets --all \
  -n sterna --timeout=300s
```

**Verify:** every expected k8s Secret exists in `sterna` namespace.

### Step 8 — Apply production overlay

Same placeholder/registry rewrites as staging step 8, against the
production overlay directory.

**Run:**
```bash
# 1. GHCR pull secret (same command as staging step 8).
GHCR_OWNER="<lowercased-github-owner>"
kubectl create secret docker-registry ghcr-registry \
  --docker-server=ghcr.io \
  --docker-username="$GHCR_OWNER" \
  --docker-password="$GHCR_PULL_TOKEN" \
  -n sterna --dry-run=client -o yaml | kubectl apply -f -

# 2. Resolve the imagePullSecrets placeholder.
sed -i "s/__SECRET_NAME__/ghcr-registry/g" \
  infra-migration/kubernetes/overlays/production/patches/image-pull-secret.yaml

# 3. Same nine-service `kustomize edit set image` one-liner as
#    staging step 8, but run inside
#    infra-migration/kubernetes/overlays/production with
#    TAG="master-latest" (or a pinned semver tag).

# 4. Build + apply.
kustomize build infra-migration/kubernetes/overlays/production \
  | kubectl apply -f -
```

**Verify:**
```bash
kustomize build infra-migration/kubernetes/overlays/production \
  | grep -E "__SECRET_NAME__|rg\.fr-par\.scw\.cloud" || echo "rewrites OK"
kubectl get deployments -n sterna
```
The grep prints nothing and all Deployments are created.

### Step 9 — Wait for Deployments Ready

**Run:** same loop as staging step 9.

**Verify:** every Deployment shows `readyReplicas == spec.replicas`.

### Step 10 — Verify Cloudflare Tunnel connection

**Run:** same as staging step 10 with the prod tunnel name.

**Verify:** tunnel logs show "Registered tunnel connection".

### Step 11 — Seed data: re-apply seed_all in the prod web pod

**Run:**
```bash
POD=$(kubectl get pods -n sterna -l app=web \
  -o jsonpath='{.items[0].metadata.name}')
SKIP_FLAG=""
# Set vars.PRODUCTION_SKIP_SMOKE_USER=true to opt out of the smoke
# user in prod (zero-trust posture).
if [ "$PRODUCTION_SKIP_SMOKE_USER" = "true" ]; then
  SKIP_FLAG="--skip-smoke-user"
fi
kubectl exec -n sterna "$POD" -- python manage.py seed_all $SKIP_FLAG
```

**Verify:** exit 0; final line `seed_all: all steps OK`.

### Step 12 — In-cluster smoke against prod service URL

**Run:**
```bash
POD=$(kubectl get pods -n sterna -l app=web \
  -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n sterna "$POD" -- bash -c '
  SMOKE_BASE_URL=http://production-web.sterna.svc.cluster.local:8000 \
  python -m pytest smoke/ -v --tb=short
'
```

**Verify:** all smoke tests pass (or skip cleanly).

### Step 13 — Flip DNS (production)

**Run:** Cloudflare → DNS. Update `app.<your-domain>` and
`api.<your-domain>` CNAMEs to point at the production tunnel.

**Verify:**
```bash
dig +short app.<your-domain>
curl -sf https://app.<your-domain>/livez
```
Returns 200.

### Step 14 — Public-URL smoke (production)

**Run:**
```bash
cd core
pip install pytest==8.3.4 httpx==0.28.1
SMOKE_BASE_URL=https://app.<your-domain> \
SMOKE_TEST_USER_PASSWORD="$SMOKE_TEST_USER_PASSWORD_PROD" \
pytest -c /dev/null smoke/ -v --tb=short
```

**Verify:** all smoke tests pass.

---

## F.1.e — Failure recovery

Common failure modes and where in the runbook to restart:

| Symptom | Restart at | Cross-link |
|---|---|---|
| Nodes stuck `NotReady` after step 4 | Step 4 (check `hcloud` secret, CCM logs) | `infra-migration/kubernetes/base/hetzner-cloud/README.md` |
| ESO Helm install hangs | Step 5 (check Scaleway credentials, ESO chart version) | `infra-migration/README.md` |
| ExternalSecret stuck `Ready=False` | Step 7 (check secret name in Scaleway payload matches `extract:` key) | `bootstrap-staging/README.md` |
| Deployment Pending — image pull error | Step 8 (verify `imagePullSecrets` references GHCR token) | `infra-migration/README.md` |
| Cloudflare Tunnel logs show `auth_failure` | Step 10 (regenerate tunnel token) | `infra-migration/README.md` |
| `seed_all` fails on `sync_stripe_prices` | Step 11 (Stripe key not yet synced; wait for ExternalSecret refresh) | `seed_all` docstring |
| Smoke `test_authed_user_can_send_chat_message` fails | Step 11 (smoke user not seeded — re-run `seed_all`) | `core/smoke/README.md` |
| Public-URL smoke times out | Step 13 (DNS may still be propagating; wait + retry) | this file |

A failure at any step does NOT require redoing earlier ones. The
kustomize applies are all idempotent; `seed_all` is idempotent;
`kubectl exec` re-runs are safe.

If the cluster needs a clean re-bring-up, `terraform destroy` from
the environment directory and start at step 1.
