"""
Kubernetes Pod Manager for Sandbox Containers

Handles creating, managing, and destroying sandbox pods using the Kubernetes Python client.
"""

import logging
import time
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream

from .config import SandboxConfig

logger = logging.getLogger(__name__)


class PodManager:
    """Manages Kubernetes pods for sandbox execution."""

    def __init__(self, sandbox_config: Optional[SandboxConfig] = None):
        self.config = sandbox_config or SandboxConfig()

        # Load Kubernetes config (in-cluster or from kubeconfig)
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            config.load_kube_config()
            logger.info("Loaded local Kubernetes config")

        self.core_v1 = client.CoreV1Api()
        self.networking_v1 = client.NetworkingV1Api()

    def _generate_pod_name(self, user_id: str) -> str:
        """Generate unique pod name for user."""
        # One pod per user - isolation via workspace directories
        return f"sandbox-{user_id}"

    def _get_pod_spec(self, user_id: str) -> client.V1Pod:
        """Generate pod specification for a user's sandbox."""
        pod_name = self._generate_pod_name(user_id)
        labels = self.config.get_pod_labels(user_id)
        resources = self.config.get_resource_requirements()

        # Security context for the container
        container_security_context = client.V1SecurityContext(
            run_as_non_root=True,
            run_as_user=self.config.run_as_user,
            run_as_group=self.config.run_as_group,
            allow_privilege_escalation=False,
            read_only_root_filesystem=False,  # Need writable for temp files
            capabilities=client.V1Capabilities(drop=["ALL"]),
        )

        # Pod security context
        pod_security_context = client.V1PodSecurityContext(
            run_as_non_root=True,
            run_as_user=self.config.run_as_user,
            run_as_group=self.config.run_as_group,
            fs_group=self.config.run_as_group,
            seccomp_profile=client.V1SeccompProfile(type="RuntimeDefault")
            if self.config.enable_seccomp
            else None,
        )

        # Environment variables
        env_vars = [
            client.V1EnvVar(name="HTTP_PROXY", value=self.config.egress_proxy_url),
            client.V1EnvVar(name="HTTPS_PROXY", value=self.config.egress_proxy_url),
            client.V1EnvVar(name="http_proxy", value=self.config.egress_proxy_url),
            client.V1EnvVar(name="https_proxy", value=self.config.egress_proxy_url),
            client.V1EnvVar(name="NO_PROXY", value="localhost,127.0.0.1,.sterna,.sterna-sandboxes"),
            client.V1EnvVar(name="USER_ID", value=user_id),
            client.V1EnvVar(name="HOME", value="/workspace"),
        ]

        # Volumes
        volumes = [
            # Workspace volume for user data
            client.V1Volume(
                name="workspace",
                empty_dir=client.V1EmptyDirVolumeSource(
                    size_limit=self.config.storage_size
                ),
            ),
            # Tmp volume
            client.V1Volume(
                name="tmp",
                empty_dir=client.V1EmptyDirVolumeSource(size_limit="1Gi"),
            ),
        ]

        # Volume mounts
        volume_mounts = [
            client.V1VolumeMount(name="workspace", mount_path="/workspace"),
            client.V1VolumeMount(name="tmp", mount_path="/tmp"),
        ]

        # Main container
        container = client.V1Container(
            name="sandbox",
            image=self.config.sandbox_image,
            image_pull_policy="Always",
            command=["sleep", "infinity"],  # Keep pod running
            env=env_vars,
            resources=client.V1ResourceRequirements(**resources),
            security_context=container_security_context,
            volume_mounts=volume_mounts,
            # Liveness probe to detect stuck pods
            liveness_probe=client.V1Probe(
                _exec=client.V1ExecAction(command=["true"]),
                initial_delay_seconds=30,
                period_seconds=30,
                timeout_seconds=5,
                failure_threshold=3,
            ),
        )

        # Pod spec
        pod_spec = client.V1PodSpec(
            containers=[container],
            volumes=volumes,
            security_context=pod_security_context,
            runtime_class_name=self.config.runtime_class,
            service_account_name=self.config.service_account,
            restart_policy="Never",
            # Tolerations for gVisor nodes
            tolerations=[
                client.V1Toleration(
                    key="sternaway.ai/gvisor",
                    operator="Exists",
                    effect="NoSchedule",
                )
            ],
            # Node selector for gVisor nodes
            node_selector={"sternaway.ai/gvisor": "true"},
            # Termination grace period
            termination_grace_period_seconds=10,
            # Prevent scheduling on control plane
            affinity=client.V1Affinity(
                node_affinity=client.V1NodeAffinity(
                    required_during_scheduling_ignored_during_execution=client.V1NodeSelector(
                        node_selector_terms=[
                            client.V1NodeSelectorTerm(
                                match_expressions=[
                                    client.V1NodeSelectorRequirement(
                                        key="node-role.kubernetes.io/control-plane",
                                        operator="DoesNotExist",
                                    )
                                ]
                            )
                        ]
                    )
                )
            ),
        )

        # Pod metadata with annotations for tracking
        metadata = client.V1ObjectMeta(
            name=pod_name,
            namespace=self.config.namespace,
            labels=labels,
            annotations={
                "sternaway.ai/created-at": datetime.utcnow().isoformat(),
                "sternaway.ai/last-activity": datetime.utcnow().isoformat(),
                "sternaway.ai/user-id": user_id,
            },
        )

        return client.V1Pod(
            api_version="v1",
            kind="Pod",
            metadata=metadata,
            spec=pod_spec,
        )

    def create_pod(self, user_id: str) -> Tuple[str, bool]:
        """
        Create or get existing sandbox pod for user.

        Returns:
            Tuple of (pod_name, created) where created is True if new pod was created
        """
        pod_name = self._generate_pod_name(user_id)

        try:
            # Check if pod already exists
            existing_pod = self.core_v1.read_namespaced_pod(
                name=pod_name,
                namespace=self.config.namespace,
            )

            # Check pod status
            if existing_pod.status.phase == "Running":
                logger.info(f"Reusing existing pod: {pod_name}")
                self._update_last_activity(pod_name)
                return pod_name, False

            # Pod exists but not running - delete and recreate
            logger.info(
                f"Pod {pod_name} exists but status is {existing_pod.status.phase}, recreating..."
            )
            self.delete_pod(user_id)

        except ApiException as e:
            if e.status != 404:
                raise

        # Create new pod
        pod_spec = self._get_pod_spec(user_id)
        logger.info(f"Creating new sandbox pod: {pod_name}")

        try:
            self.core_v1.create_namespaced_pod(
                namespace=self.config.namespace,
                body=pod_spec,
            )
        except ApiException as e:
            logger.error(f"Failed to create pod {pod_name}: {e}")
            raise

        # Wait for pod to be running
        self._wait_for_pod_ready(pod_name)

        # Create network policy for this pod
        if self.config.enable_network_policy:
            self._create_network_policy(user_id, pod_name)

        return pod_name, True

    def _wait_for_pod_ready(self, pod_name: str, timeout: int = 60) -> None:
        """Wait for pod to be ready."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                pod = self.core_v1.read_namespaced_pod(
                    name=pod_name,
                    namespace=self.config.namespace,
                )

                if pod.status.phase == "Running":
                    # Check container status
                    if pod.status.container_statuses:
                        container_status = pod.status.container_statuses[0]
                        if container_status.ready:
                            logger.info(f"Pod {pod_name} is ready")
                            return

                elif pod.status.phase in ["Failed", "Unknown"]:
                    raise RuntimeError(
                        f"Pod {pod_name} failed to start: {pod.status.phase}"
                    )

            except ApiException as e:
                if e.status != 404:
                    raise

            time.sleep(1)

        raise TimeoutError(f"Pod {pod_name} did not become ready within {timeout}s")

    def _update_last_activity(self, pod_name: str) -> None:
        """Update last activity annotation on pod."""
        try:
            self.core_v1.patch_namespaced_pod(
                name=pod_name,
                namespace=self.config.namespace,
                body={
                    "metadata": {
                        "annotations": {
                            "sternaway.ai/last-activity": datetime.utcnow().isoformat()
                        }
                    }
                },
            )
        except ApiException as e:
            logger.warning(f"Failed to update last activity for {pod_name}: {e}")

    def _create_network_policy(self, user_id: str, pod_name: str) -> None:
        """Create network policy to restrict pod egress to proxy only."""
        policy_name = f"sandbox-policy-{user_id}"

        policy = client.V1NetworkPolicy(
            api_version="networking.k8s.io/v1",
            kind="NetworkPolicy",
            metadata=client.V1ObjectMeta(
                name=policy_name,
                namespace=self.config.namespace,
            ),
            spec=client.V1NetworkPolicySpec(
                pod_selector=client.V1LabelSelector(
                    match_labels={"sternaway.ai/user-id": user_id}
                ),
                policy_types=["Egress"],
                egress=[
                    # Allow DNS
                    client.V1NetworkPolicyEgressRule(
                        to=[
                            client.V1NetworkPolicyPeer(
                                namespace_selector=client.V1LabelSelector(
                                    match_labels={
                                        "kubernetes.io/metadata.name": "kube-system"
                                    }
                                )
                            )
                        ],
                        ports=[
                            client.V1NetworkPolicyPort(protocol="UDP", port=53),
                            client.V1NetworkPolicyPort(protocol="TCP", port=53),
                        ],
                    ),
                    # Allow egress proxy
                    client.V1NetworkPolicyEgressRule(
                        to=[
                            client.V1NetworkPolicyPeer(
                                namespace_selector=client.V1LabelSelector(
                                    match_labels={
                                        "kubernetes.io/metadata.name": "sterna"
                                    }
                                ),
                                pod_selector=client.V1LabelSelector(
                                    match_labels={"app": "egress-proxy"}
                                ),
                            )
                        ],
                        ports=[
                            client.V1NetworkPolicyPort(protocol="TCP", port=3128),
                        ],
                    ),
                ],
            ),
        )

        try:
            self.networking_v1.create_namespaced_network_policy(
                namespace=self.config.namespace,
                body=policy,
            )
            logger.info(f"Created network policy: {policy_name}")
        except ApiException as e:
            if e.status == 409:  # Already exists
                logger.debug(f"Network policy {policy_name} already exists")
            else:
                logger.warning(f"Failed to create network policy: {e}")

    def delete_pod(self, user_id: str) -> bool:
        """Delete sandbox pod for user."""
        pod_name = self._generate_pod_name(user_id)

        try:
            self.core_v1.delete_namespaced_pod(
                name=pod_name,
                namespace=self.config.namespace,
                grace_period_seconds=10,
            )
            logger.info(f"Deleted pod: {pod_name}")

            # Also delete network policy
            if self.config.enable_network_policy:
                try:
                    self.networking_v1.delete_namespaced_network_policy(
                        name=f"sandbox-policy-{user_id}",
                        namespace=self.config.namespace,
                    )
                except ApiException:
                    pass

            return True

        except ApiException as e:
            if e.status == 404:
                logger.debug(f"Pod {pod_name} not found")
                return False
            raise

    def exec_in_pod(
        self,
        user_id: str,
        command: list,
        timeout: int = 30,
        workdir: Optional[str] = None,
    ) -> Tuple[int, str, str]:
        """
        Execute command in user's sandbox pod.

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        pod_name = self._generate_pod_name(user_id)

        # Ensure pod exists
        self.create_pod(user_id)

        # Update activity
        self._update_last_activity(pod_name)

        # Build exec command
        if workdir:
            command = ["sh", "-c", f"cd {workdir} && {' '.join(command)}"]

        try:
            resp = stream(
                self.core_v1.connect_get_namespaced_pod_exec,
                name=pod_name,
                namespace=self.config.namespace,
                command=command,
                container="sandbox",
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
                _preload_content=False,
            )

            stdout = ""
            stderr = ""

            # Read with timeout
            start_time = time.time()
            while resp.is_open():
                if time.time() - start_time > timeout:
                    resp.close()
                    raise TimeoutError(f"Command timed out after {timeout}s")

                resp.update(timeout=1)
                if resp.peek_stdout():
                    stdout += resp.read_stdout()
                if resp.peek_stderr():
                    stderr += resp.read_stderr()

            # Get exit code from response
            exit_code = resp.returncode if hasattr(resp, "returncode") else 0

            return exit_code, stdout, stderr

        except ApiException as e:
            logger.error(f"Failed to exec in pod {pod_name}: {e}")
            raise

    def copy_to_pod(
        self,
        user_id: str,
        local_path: str,
        remote_path: str,
    ) -> bool:
        """Copy file to pod using tar."""
        import tarfile
        import io
        import base64

        # Create tar archive
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
            tar.add(local_path, arcname=remote_path.split("/")[-1])

        tar_data = base64.b64encode(tar_buffer.getvalue()).decode()

        # Extract in pod
        exit_code, stdout, stderr = self.exec_in_pod(
            user_id=user_id,
            command=[
                "sh",
                "-c",
                f"echo '{tar_data}' | base64 -d | tar -xf - -C {'/'.join(remote_path.split('/')[:-1])}",
            ],
        )

        return exit_code == 0

    def get_pod_status(self, user_id: str) -> Optional[Dict]:
        """Get pod status information."""
        pod_name = self._generate_pod_name(user_id)

        try:
            pod = self.core_v1.read_namespaced_pod(
                name=pod_name,
                namespace=self.config.namespace,
            )

            return {
                "name": pod_name,
                "phase": pod.status.phase,
                "ready": (
                    pod.status.container_statuses[0].ready
                    if pod.status.container_statuses
                    else False
                ),
                "created_at": pod.metadata.annotations.get("sternaway.ai/created-at"),
                "last_activity": pod.metadata.annotations.get(
                    "sternaway.ai/last-activity"
                ),
            }

        except ApiException as e:
            if e.status == 404:
                return None
            raise

    def list_inactive_pods(self, inactivity_threshold: int) -> list:
        """List pods that have been inactive longer than threshold."""
        inactive_pods = []
        threshold_time = datetime.utcnow() - timedelta(seconds=inactivity_threshold)

        try:
            pods = self.core_v1.list_namespaced_pod(
                namespace=self.config.namespace,
                label_selector="sternaway.ai/sandbox-type=execution",
            )

            for pod in pods.items:
                last_activity_str = pod.metadata.annotations.get(
                    "sternaway.ai/last-activity"
                )
                if last_activity_str:
                    last_activity = datetime.fromisoformat(
                        last_activity_str.replace("Z", "+00:00")
                    )
                    if last_activity.replace(tzinfo=None) < threshold_time:
                        inactive_pods.append(
                            {
                                "name": pod.metadata.name,
                                "user_id": pod.metadata.annotations.get(
                                    "sternaway.ai/user-id"
                                ),
                                "last_activity": last_activity_str,
                            }
                        )

        except ApiException as e:
            logger.error(f"Failed to list pods: {e}")

        return inactive_pods

    def cleanup_inactive_pods(self, inactivity_threshold: int) -> int:
        """Delete pods that have been inactive longer than threshold."""
        inactive_pods = self.list_inactive_pods(inactivity_threshold)
        deleted_count = 0

        for pod_info in inactive_pods:
            user_id = pod_info.get("user_id")
            if user_id:
                logger.info(
                    f"Cleaning up inactive pod for user {user_id} "
                    f"(last activity: {pod_info['last_activity']})"
                )
                if self.delete_pod(user_id):
                    deleted_count += 1

        return deleted_count
