"""
MCP Registry V2

DEPRECATION NOTICE:
This registry (V2) was a partial sandbox-based implementation that was never fully completed.
It has been superseded by the UnifiedMCPRegistry in unified_registry.py which provides:
- Complete support for both OAuth servers AND custom npm-based servers
- Full sandbox integration via the orchestrator
- Proper tool execution through sandboxed containers

Please use unified_registry.py for all new development.

Original description:
New architecture for MCP server management with per-user sandbox isolation.
Implements on-demand tool discovery pattern.

Key improvements over V1:
- Per-user sandbox isolation for all MCP servers
- On-demand tool discovery (not pre-loaded)
- Proper resource management and limits
- OAuth token management per user
- Health monitoring and auto-recovery
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
import threading
import httpx

logger = logging.getLogger(__name__)


class MCPServerType(str, Enum):
    """Types of MCP servers."""
    SYSTEM = "system"           # Platform-managed (official connectors)
    USER = "user"               # User-installed custom servers
    MARKETPLACE = "marketplace"  # From connector marketplace


class MCPServerStatus(str, Enum):
    """Server lifecycle status."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    STOPPING = "stopping"


@dataclass
class MCPResourceLimits:
    """Resource limits for MCP server sandbox."""
    memory_mb: int = 512
    cpu_shares: int = 256
    timeout_seconds: int = 300
    max_concurrent_requests: int = 10


@dataclass
class MCPServerConfig:
    """
    Configuration for an MCP server.

    Defines how to start and connect to the server.
    """
    server_id: str              # Unique identifier
    name: str                   # Display name
    description: str            # Description for users
    server_type: MCPServerType

    # Execution
    command: str                # Start command (npx, node, python, etc.)
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)

    # Sandbox
    sandbox_required: bool = True
    resource_limits: MCPResourceLimits = field(default_factory=MCPResourceLimits)

    # Discovery
    default_defer_loading: bool = True  # Tools discovered on-demand
    always_loaded_tools: List[str] = field(default_factory=list)

    # Authentication
    requires_oauth: bool = False
    oauth_provider: Optional[str] = None  # "google", "slack", "notion", etc.
    oauth_scopes: List[str] = field(default_factory=list)

    # Health
    health_check_interval_seconds: int = 60
    auto_restart_on_failure: bool = True


@dataclass
class MCPServerInstance:
    """
    Runtime instance of an MCP server for a specific user.

    Each user gets their own isolated instance.
    """
    config: MCPServerConfig
    user_id: str
    sandbox_id: Optional[str] = None

    # State
    status: MCPServerStatus = MCPServerStatus.STOPPED
    started_at: Optional[datetime] = None
    last_health_check: Optional[datetime] = None
    error_message: Optional[str] = None

    # Connection
    endpoint_url: Optional[str] = None

    # Discovered tools
    available_tools: List[str] = field(default_factory=list)
    tools_discovered_at: Optional[datetime] = None

    # Metrics
    request_count: int = 0
    error_count: int = 0
    avg_latency_ms: float = 0

    def is_healthy(self) -> bool:
        """Check if the instance is healthy."""
        if self.status != MCPServerStatus.RUNNING:
            return False

        if self.last_health_check is None:
            return False

        # Check if health check is recent
        max_age = timedelta(seconds=self.config.health_check_interval_seconds * 2)
        if datetime.utcnow() - self.last_health_check > max_age:
            return False

        return True


class MCPRegistryV2:
    """
    MCP Registry V2 with per-user sandbox isolation.

    Manages MCP server configurations and user instances.
    Implements lazy loading - servers start on first use.
    """

    def __init__(
        self,
        sandbox_manager_url: str = "http://orchestrator:8003",
    ):
        """
        Initialize the registry.

        Args:
            sandbox_manager_url: URL of the sandbox orchestrator
        """
        self.sandbox_manager_url = sandbox_manager_url
        self._server_configs: Dict[str, MCPServerConfig] = {}
        self._user_instances: Dict[str, Dict[str, MCPServerInstance]] = {}
        self._lock = threading.RLock()
        self._http_client: Optional[httpx.AsyncClient] = None

        logger.info("[MCPRegistry V2] Initialized")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close(self):
        """Close resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def register_server(self, config: MCPServerConfig):
        """
        Register an MCP server configuration.

        Args:
            config: Server configuration
        """
        with self._lock:
            self._server_configs[config.server_id] = config
            logger.info(f"[MCPRegistry V2] Registered server: {config.server_id}")

    def unregister_server(self, server_id: str):
        """
        Unregister an MCP server.

        Note: Does not stop running instances.
        """
        with self._lock:
            if server_id in self._server_configs:
                del self._server_configs[server_id]
                logger.info(f"[MCPRegistry V2] Unregistered server: {server_id}")

    def get_server_config(self, server_id: str) -> Optional[MCPServerConfig]:
        """Get a server configuration."""
        with self._lock:
            return self._server_configs.get(server_id)

    def list_servers(self, server_type: Optional[MCPServerType] = None) -> List[MCPServerConfig]:
        """
        List registered servers.

        Args:
            server_type: Optional filter by type

        Returns:
            List of server configurations
        """
        with self._lock:
            configs = list(self._server_configs.values())

            if server_type:
                configs = [c for c in configs if c.server_type == server_type]

            return configs

    async def get_user_instance(
        self,
        user_id: str,
        server_id: str,
        auto_start: bool = True
    ) -> Optional[MCPServerInstance]:
        """
        Get or create an MCP server instance for a user.

        Each user gets their own isolated sandbox instance.

        Args:
            user_id: User identifier
            server_id: Server identifier
            auto_start: Start the server if not running

        Returns:
            MCPServerInstance or None if server not found
        """
        config = self.get_server_config(server_id)
        if not config:
            logger.warning(f"[MCPRegistry V2] Unknown server: {server_id}")
            return None

        with self._lock:
            user_instances = self._user_instances.setdefault(user_id, {})

            if server_id not in user_instances:
                # Create new instance
                instance = MCPServerInstance(
                    config=config,
                    user_id=user_id,
                )
                user_instances[server_id] = instance
                logger.info(f"[MCPRegistry V2] Created instance {server_id} for user {user_id}")

        instance = self._user_instances[user_id][server_id]

        # Auto-start if needed
        if auto_start and instance.status == MCPServerStatus.STOPPED:
            await self._start_instance(instance)

        return instance

    async def _start_instance(self, instance: MCPServerInstance):
        """
        Start an MCP server instance in sandbox.

        Args:
            instance: Instance to start
        """
        if instance.status not in [MCPServerStatus.STOPPED, MCPServerStatus.ERROR]:
            return

        instance.status = MCPServerStatus.STARTING
        logger.info(f"[MCPRegistry V2] Starting {instance.config.server_id} for {instance.user_id}")

        try:
            # Request sandbox from orchestrator
            client = await self._get_client()

            request_data = {
                "user_id": instance.user_id,
                "server_id": instance.config.server_id,
                "command": instance.config.command,
                "args": instance.config.args,
                "env": instance.config.env,
                "resource_limits": {
                    "memory_mb": instance.config.resource_limits.memory_mb,
                    "cpu_shares": instance.config.resource_limits.cpu_shares,
                    "timeout_seconds": instance.config.resource_limits.timeout_seconds,
                },
            }

            response = await client.post(
                f"{self.sandbox_manager_url}/mcp/start",
                json=request_data,
            )
            response.raise_for_status()
            result = response.json()

            instance.sandbox_id = result.get("sandbox_id")
            instance.endpoint_url = result.get("endpoint_url")
            instance.status = MCPServerStatus.RUNNING
            instance.started_at = datetime.utcnow()
            instance.error_message = None

            logger.info(
                f"[MCPRegistry V2] Started {instance.config.server_id} "
                f"(sandbox: {instance.sandbox_id})"
            )

        except Exception as e:
            instance.status = MCPServerStatus.ERROR
            instance.error_message = str(e)
            logger.error(f"[MCPRegistry V2] Failed to start {instance.config.server_id}: {e}")

    async def stop_instance(self, user_id: str, server_id: str):
        """
        Stop an MCP server instance.

        Args:
            user_id: User identifier
            server_id: Server identifier
        """
        with self._lock:
            if user_id not in self._user_instances:
                return
            if server_id not in self._user_instances[user_id]:
                return

        instance = self._user_instances[user_id][server_id]

        if instance.status != MCPServerStatus.RUNNING:
            return

        instance.status = MCPServerStatus.STOPPING
        logger.info(f"[MCPRegistry V2] Stopping {server_id} for {user_id}")

        try:
            client = await self._get_client()
            await client.post(
                f"{self.sandbox_manager_url}/mcp/stop",
                json={
                    "sandbox_id": instance.sandbox_id,
                    "user_id": user_id,
                    "server_id": server_id,
                },
            )
        except Exception as e:
            logger.error(f"[MCPRegistry V2] Error stopping {server_id}: {e}")
        finally:
            instance.status = MCPServerStatus.STOPPED
            instance.sandbox_id = None
            instance.endpoint_url = None

    async def discover_tools(
        self,
        user_id: str,
        server_id: str,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Discover tools from an MCP server.

        Implements on-demand discovery pattern.

        Args:
            user_id: User identifier
            server_id: Server identifier
            force_refresh: Force re-discovery even if cached

        Returns:
            List of tool definitions
        """
        instance = await self.get_user_instance(user_id, server_id)
        if not instance:
            return []

        # Check cache
        if not force_refresh and instance.available_tools:
            cache_age = datetime.utcnow() - (instance.tools_discovered_at or datetime.min)
            if cache_age < timedelta(minutes=5):
                logger.debug(f"[MCPRegistry V2] Using cached tools for {server_id}")
                return self._get_cached_tool_definitions(instance)

        # Ensure server is running
        if instance.status != MCPServerStatus.RUNNING:
            await self._start_instance(instance)

        if instance.status != MCPServerStatus.RUNNING:
            logger.error(f"[MCPRegistry V2] Server not running: {server_id}")
            return []

        # Call tools/list via MCP protocol
        try:
            client = await self._get_client()

            response = await client.post(
                f"{instance.endpoint_url}/rpc",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/list",
                    "id": 1,
                },
            )
            response.raise_for_status()
            result = response.json()

            tools = result.get("result", {}).get("tools", [])

            # Update cache
            instance.available_tools = [t.get("name") for t in tools]
            instance.tools_discovered_at = datetime.utcnow()

            logger.info(
                f"[MCPRegistry V2] Discovered {len(tools)} tools from {server_id}"
            )

            return tools

        except Exception as e:
            logger.error(f"[MCPRegistry V2] Tool discovery failed for {server_id}: {e}")
            return []

    def _get_cached_tool_definitions(
        self,
        instance: MCPServerInstance
    ) -> List[Dict[str, Any]]:
        """Get cached tool definitions (basic info only)."""
        return [
            {"name": name, "from_cache": True}
            for name in instance.available_tools
        ]

    async def execute_tool(
        self,
        user_id: str,
        server_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute a tool on an MCP server.

        Args:
            user_id: User identifier
            server_id: Server identifier
            tool_name: Tool name
            arguments: Tool arguments
            auth_token: Optional auth token

        Returns:
            Tool execution result
        """
        instance = await self.get_user_instance(user_id, server_id)
        if not instance:
            return {"success": False, "error": f"Unknown server: {server_id}"}

        if instance.status != MCPServerStatus.RUNNING:
            return {"success": False, "error": f"Server not running: {server_id}"}

        try:
            client = await self._get_client()

            headers = {}
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"

            response = await client.post(
                f"{instance.endpoint_url}/rpc",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments,
                    },
                    "id": 1,
                },
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()

            # Update metrics
            instance.request_count += 1

            if "error" in result:
                instance.error_count += 1
                return {
                    "success": False,
                    "error": result["error"].get("message", "Unknown error"),
                }

            return {
                "success": True,
                "result": result.get("result"),
            }

        except Exception as e:
            instance.error_count += 1
            logger.error(f"[MCPRegistry V2] Tool execution failed: {e}")
            return {"success": False, "error": str(e)}

    def get_user_servers(self, user_id: str) -> List[MCPServerInstance]:
        """
        Get all server instances for a user.

        Args:
            user_id: User identifier

        Returns:
            List of instances
        """
        with self._lock:
            if user_id not in self._user_instances:
                return []
            return list(self._user_instances[user_id].values())

    async def health_check_all(self, user_id: str):
        """
        Run health checks on all user instances.

        Args:
            user_id: User identifier
        """
        instances = self.get_user_servers(user_id)

        for instance in instances:
            if instance.status == MCPServerStatus.RUNNING:
                await self._health_check(instance)

    async def _health_check(self, instance: MCPServerInstance):
        """Run health check on an instance."""
        try:
            client = await self._get_client()

            response = await client.get(
                f"{instance.endpoint_url}/health",
                timeout=5.0,
            )
            response.raise_for_status()

            instance.last_health_check = datetime.utcnow()

        except Exception as e:
            logger.warning(
                f"[MCPRegistry V2] Health check failed for {instance.config.server_id}: {e}"
            )

            if instance.config.auto_restart_on_failure:
                logger.info(f"[MCPRegistry V2] Auto-restarting {instance.config.server_id}")
                instance.status = MCPServerStatus.STOPPED
                await self._start_instance(instance)


# Global registry instance
_mcp_registry_v2: Optional[MCPRegistryV2] = None
_registry_lock = threading.Lock()


def get_mcp_registry_v2() -> MCPRegistryV2:
    """Get the global MCP registry V2 instance."""
    global _mcp_registry_v2

    if _mcp_registry_v2 is None:
        with _registry_lock:
            if _mcp_registry_v2 is None:
                _mcp_registry_v2 = MCPRegistryV2()

    return _mcp_registry_v2
