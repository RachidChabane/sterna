# 0006 — Delete `infra-migration/sandbox-k8s/`

- Status: Accepted.
- Date: 2026-08-27.

## Context

`infra-migration/sandbox-k8s/` held a Kubernetes-native sandbox
executor (a pod-per-execution adapter, separate from the Docker
Engine executor the orchestrator actually runs). It was selected, in
principle, by an `ORCHESTRATOR_MODE` setting read from the K8s
manifests. Auditing the live orchestrator
(`core/sandbox/orchestrator/sandbox_executor.py`) showed it never
reads `ORCHESTRATOR_MODE`: the only Docker Engine call it makes runs
unconditionally, with no branch that could ever select the K8s
package. Nothing outside `sandbox-k8s/`'s own directory imported it.

## Decision

Delete `infra-migration/sandbox-k8s/` in full, along with every
`ORCHESTRATOR_MODE` and `SANDBOX_RUNTIME_CLASS` reference that
selected it in the Kubernetes manifests (the orchestrator configmap,
deployment, and the staging kustomization patch).

## Rationale

1. Code that no live code path can reach is a maintenance and audit
   liability with no offsetting benefit: it still needs reading,
   reasoning about, and keeping compatible with the rest of the
   codebase, for a branch that never executes.
2. `kustomize build` plus `kubeconform -strict` against the base,
   staging, and production overlays before and after the deletion
   produced identical output apart from the removed
   `ORCHESTRATOR_MODE`/`SANDBOX_RUNTIME_CLASS` lines, confirming the
   manifests carried no other dependency on the deleted settings.
3. Documentation that pointed at the two now-removed environment
   variables as the reason the Kubernetes deployment's isolation
   scope differs from the single-VPS path was re-anchored on the
   underlying fact instead (no `docker.sock` mount, no Kubernetes
   API client, `sandbox_executor` unset in that pod) — a description
   of unreachable configuration knobs is not itself the safeguard;
   the absence of the docker-socket mount is.

## Trade-off accepted

None functional: the package was unreachable from any live code path
before deletion. The Kubernetes-native sandbox-execution approach it
represented is not preserved anywhere; building a K8s-pod-per-
execution executor again in the future starts from nothing.
