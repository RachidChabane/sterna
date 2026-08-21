"""
Kubernetes Sandbox Executor

Manages ephemeral sandbox pods on Kubernetes with intelligent lifecycle:
- Creates sandbox pod on first execution
- Reuses sandbox for same context (user + conversation/chat)
- Destroys sandbox after inactivity timeout
- Uses gVisor RuntimeClass for security isolation
"""

from .executor import KubernetesSandboxExecutor
from .pod_manager import PodManager
from .config import SandboxConfig

__all__ = ["KubernetesSandboxExecutor", "PodManager", "SandboxConfig"]
