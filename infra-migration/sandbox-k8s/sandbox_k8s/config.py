"""
Configuration for Kubernetes Sandbox Executor
"""

import os
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class SandboxConfig:
    """Configuration for sandbox pods."""

    # Kubernetes settings
    namespace: str = field(
        default_factory=lambda: os.getenv("SANDBOX_NAMESPACE", "sterna-sandboxes")
    )
    runtime_class: str = field(
        default_factory=lambda: os.getenv("SANDBOX_RUNTIME_CLASS", "gvisor")
    )
    service_account: str = field(
        default_factory=lambda: os.getenv("SANDBOX_SERVICE_ACCOUNT", "sandbox-runner")
    )

    # Container image
    sandbox_image: str = field(
        default_factory=lambda: os.getenv(
            "SANDBOX_IMAGE", "ghcr.io/sterna-ai/sandbox:latest"
        )
    )

    # Resource limits
    cpu_request: str = field(
        default_factory=lambda: os.getenv("SANDBOX_CPU_REQUEST", "100m")
    )
    cpu_limit: str = field(
        default_factory=lambda: os.getenv("SANDBOX_CPU_LIMIT", "1000m")
    )
    memory_request: str = field(
        default_factory=lambda: os.getenv("SANDBOX_MEMORY_REQUEST", "256Mi")
    )
    memory_limit: str = field(
        default_factory=lambda: os.getenv("SANDBOX_MEMORY_LIMIT", "1536Mi")
    )

    # Storage
    storage_class: str = field(
        default_factory=lambda: os.getenv("SANDBOX_STORAGE_CLASS", "hcloud-volumes")
    )
    storage_size: str = field(
        default_factory=lambda: os.getenv("SANDBOX_STORAGE_SIZE", "5Gi")
    )

    # Lifecycle
    inactivity_timeout: int = field(
        default_factory=lambda: int(os.getenv("SANDBOX_IDLE_TIMEOUT", "3600"))
    )
    max_lifetime: int = field(
        default_factory=lambda: int(os.getenv("SANDBOX_MAX_LIFETIME", "86400"))
    )
    cleanup_interval: int = field(
        default_factory=lambda: int(os.getenv("SANDBOX_CLEANUP_INTERVAL", "60"))
    )

    # Network
    egress_proxy_url: str = field(
        default_factory=lambda: os.getenv("EGRESS_PROXY_URL", "http://egress-proxy:3128")
    )
    enable_network_policy: bool = field(
        default_factory=lambda: os.getenv("ENABLE_NETWORK_POLICY", "true").lower() == "true"
    )

    # Security
    enable_seccomp: bool = True
    enable_apparmor: bool = False  # gVisor provides isolation
    run_as_user: int = 1000
    run_as_group: int = 1000

    # Timeouts
    file_operation_timeout: int = 30
    directory_operation_timeout: int = 60
    code_execution_default_timeout: int = 120

    # Size limits
    max_file_size_bytes: int = 50 * 1024 * 1024  # 50MB
    max_code_execution_size: int = 1 * 1024 * 1024  # 1MB

    # Labels applied to all sandbox pods
    default_labels: Dict[str, str] = field(default_factory=lambda: {
        "app.kubernetes.io/name": "sandbox",
        "app.kubernetes.io/component": "user-sandbox",
        "app.kubernetes.io/managed-by": "orchestrator",
    })

    def get_pod_labels(self, user_id: str) -> Dict[str, str]:
        """Get labels for a user's sandbox pod."""
        labels = self.default_labels.copy()
        labels["sternaway.ai/user-id"] = user_id
        labels["sternaway.ai/sandbox-type"] = "execution"
        return labels

    def get_resource_requirements(self) -> Dict:
        """Get Kubernetes resource requirements dict."""
        return {
            "requests": {
                "cpu": self.cpu_request,
                "memory": self.memory_request,
            },
            "limits": {
                "cpu": self.cpu_limit,
                "memory": self.memory_limit,
            },
        }
