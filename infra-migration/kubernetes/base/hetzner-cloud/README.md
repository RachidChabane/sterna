# Hetzner Cloud add-ons — CCM + CSI

This directory holds the upstream **Hetzner Cloud Controller Manager**
(CCM) and **CSI driver** manifests that the k3s cluster on Hetzner
needs in order to:

- Clear the `node.cloudprovider.kubernetes.io/uninitialized:NoSchedule`
  taint that `--kubelet-arg=cloud-provider=external` places on every
  node at boot (CCM).
- Provision Hetzner Cloud volumes for stateful PVCs (CSI).

## Status

**NOT YET WIRED IN `base/kustomization.yaml`.** Task 27 enables this
directory after the first `terraform apply` of the Hetzner module
succeeds. The manifests are committed here so they're version-pinned
and reviewable.

## Apply order (task 27)

1. `terraform apply` of `terraform/environments/staging-hetzner/` —
   provisions the Hetzner cluster. **Expect `kubectl get nodes` to
   show `NotReady` after this completes**; that is correct, not a
   failure.
2. Create the `hcloud` secret in `kube-system` (CCM/CSI both consume
   it). The Hetzner network ID comes from the terraform output:
   ```bash
   kubectl create secret generic hcloud -n kube-system \
     --from-literal=token="$HCLOUD_TOKEN" \
     --from-literal=network="$(terraform -chdir=infra-migration/terraform/environments/staging-hetzner output -raw network_id)"
   ```
3. Apply this directory's manifests:
   ```bash
   kubectl apply -f infra-migration/kubernetes/base/hetzner-cloud/ccm.yaml
   kubectl apply -f infra-migration/kubernetes/base/hetzner-cloud/csi.yaml
   ```
4. Wait for nodes to become `Ready`: `kubectl get nodes -w`.
5. Add `- hetzner-cloud` to `base/kustomization.yaml`'s `resources:`
   list (task 27 PR).

## Troubleshooting

- **CCM pod stuck `Pending`**: verify the toleration block on the
  CCM Deployment still tolerates
  `node.cloudprovider.kubernetes.io/uninitialized:NoSchedule`. The
  pinned `ccm.yaml` carries it; a future version bump may move or
  remove it.
- **CSI pods stuck `Pending`**: same toleration story; CSI node
  daemonset must tolerate the uninitialized taint too.
- **Both pods `CrashLoopBackOff` with auth errors**: the `hcloud`
  secret token is invalid or missing. Re-create it from
  `HCLOUD_TOKEN` per step 2 above (see `infra-migration/README.md`
  for how that secret is generated and populated).

## Version provenance

Every manifest in this directory has a header comment recording the
upstream URL, version, and SHA-256 of the downloaded file. To
update:

1. Bump the version in the upstream URL.
2. Re-download with `curl -fsSL <url> -o <file>` and update the
   SHA-256 in the header.
3. Verify the CCM toleration block is still present.
4. Open a separate PR (don't combine with feature work).
