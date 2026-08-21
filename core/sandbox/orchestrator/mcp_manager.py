"""
MCP Server Manager (DEPRECATED)

THIS MODULE IS DEPRECATED. MCP servers now run as child processes inside the
user's sandbox container, managed by the MCP Gateway (mcp-gateway.js).

See sandbox_executor.py for the new implementation:
- start_mcp_server()
- stop_mcp_server()
- call_mcp_tool()
- etc.

The new architecture is much more scalable:
- Old: 1 container per MCP server per user (doesn't scale)
- New: 1 sandbox container per user with MCP servers as child processes

This file is kept for reference only.

---

OLD DESCRIPTION:
Manages MCP server containers in sandboxed Docker environments:
- Starts MCP servers using the generic runner image
- Tracks running servers per user
- Proxies JSON-RPC communication to containers
- Handles container lifecycle and cleanup
"""

import docker
import time
import threading
import logging
import uuid
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# Configuration
MCP_RUNNER_IMAGE = "sterna-mcp-runner:latest"
MCP_CONTAINER_PREFIX = "mcp-server-"
DEFAULT_MEMORY_LIMIT = "256m"
DEFAULT_CPU_LIMIT = 0.5
INACTIVITY_TIMEOUT = 1800  # 30 minutes
CLEANUP_INTERVAL = 60  # Check every minute


@dataclass
class MCPServerInstance:
    """Represents a running MCP server container."""
    container_id: str
    container_name: str
    user_id: str
    server_id: str
    npm_package: str
    status: str  # 'starting', 'running', 'error', 'stopped'
    started_at: datetime
    last_used: datetime
    container_ip: Optional[str] = None  # IP address on sandbox network
    stdin_port: Optional[int] = None  # Port for stdio communication
    error_message: Optional[str] = None
    tools: List[Dict] = field(default_factory=list)


class MCPServerManager:
    """Manages MCP server containers."""

    def __init__(self, docker_client: docker.DockerClient):
        self.docker = docker_client
        self.servers: Dict[str, MCPServerInstance] = {}  # container_id -> instance
        self.user_servers: Dict[str, List[str]] = {}  # user_id -> [container_ids]
        self.lock = threading.Lock()

        # Egress proxy configuration
        self.egress_proxy_url = "http://sterna-egress-proxy:8888"

        # Start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()

        # Cleanup orphaned containers on startup
        self._cleanup_orphaned_containers()

        logger.info("MCPServerManager initialized")

    def _cleanup_orphaned_containers(self):
        """Remove orphaned MCP containers from previous runs."""
        try:
            containers = self.docker.containers.list(
                all=True,
                filters={"name": MCP_CONTAINER_PREFIX}
            )

            if containers:
                logger.info(f"Found {len(containers)} orphaned MCP containers, cleaning up...")
                for container in containers:
                    try:
                        logger.info(f"Removing orphaned MCP container: {container.name}")
                        container.remove(force=True)
                    except Exception as e:
                        logger.warning(f"Failed to remove orphaned container {container.name}: {e}")
        except Exception as e:
            logger.error(f"Error during orphaned MCP containers cleanup: {e}")

    def _cleanup_loop(self):
        """Background thread to cleanup inactive MCP servers."""
        while True:
            try:
                time.sleep(CLEANUP_INTERVAL)
                self._cleanup_inactive_servers()
            except Exception as e:
                logger.error(f"Error in MCP cleanup loop: {e}")

    def _cleanup_inactive_servers(self):
        """Remove servers that have been inactive for too long."""
        now = datetime.utcnow()
        to_remove = []

        with self.lock:
            for container_id, instance in self.servers.items():
                if (now - instance.last_used).total_seconds() > INACTIVITY_TIMEOUT:
                    to_remove.append(container_id)

        for container_id in to_remove:
            logger.info(f"Cleaning up inactive MCP server: {container_id}")
            self.stop_server(container_id)

    def _generate_container_name(self, user_id: str, server_id: str) -> str:
        """Generate unique container name."""
        short_id = uuid.uuid4().hex[:8]
        # Sanitize user_id and server_id for container naming
        safe_user = user_id.replace("-", "")[:12]
        safe_server = server_id.replace("-", "")[:12]
        return f"{MCP_CONTAINER_PREFIX}{safe_user}-{safe_server}-{short_id}"

    def _build_egress_whitelist(self, allowed_domains: List[str], npm_package: str) -> List[str]:
        """Build the egress whitelist for the container."""
        # Base whitelist for npm and Python packages
        base_domains = [
            # NPM registry
            "registry.npmjs.org",
            "registry.yarnpkg.com",
            "*.npmjs.org",
            "*.cloudflare.com",  # CDN used by npm
            # Python package registries (for UV/pip)
            "pypi.org",
            "files.pythonhosted.org",
            "*.pypi.org",
            # UV installer/updates
            "astral.sh",
            "github.com",  # Many packages hosted here
            "raw.githubusercontent.com",
        ]

        # Add user-specified domains
        all_domains = base_domains + (allowed_domains or [])

        return list(set(all_domains))  # Deduplicate

    def start_server(
        self,
        user_id: str,
        server_id: str,
        npm_package: str,
        env_vars: Optional[Dict[str, str]] = None,
        allowed_domains: Optional[List[str]] = None,
    ) -> MCPServerInstance:
        """
        Start an MCP server in a sandboxed container.

        Args:
            user_id: Owner of the server
            server_id: Unique server identifier
            npm_package: NPM package to run (e.g., '@modelcontextprotocol/server-github')
            env_vars: Environment variables (API keys, tokens)
            allowed_domains: Domains to whitelist for network egress

        Returns:
            MCPServerInstance with container information
        """
        container_name = self._generate_container_name(user_id, server_id)

        # Build environment variables
        container_env = {
            "NODE_ENV": "production",
            "NO_COLOR": "1",
            # Proxy configuration for egress control
            "HTTP_PROXY": self.egress_proxy_url,
            "HTTPS_PROXY": self.egress_proxy_url,
            "http_proxy": self.egress_proxy_url,
            "https_proxy": self.egress_proxy_url,
            # SSL configuration for egress proxy (proxy does SSL interception)
            "NODE_TLS_REJECT_UNAUTHORIZED": "0",
            "npm_config_strict_ssl": "false",
        }

        # Add user-provided environment variables
        if env_vars:
            container_env.update(env_vars)

        # Build egress whitelist
        whitelist = self._build_egress_whitelist(allowed_domains or [], npm_package)
        container_env["EGRESS_WHITELIST"] = ",".join(whitelist)

        try:
            logger.info(f"Starting MCP server: {npm_package} for user {user_id}")

            # Check if image exists
            try:
                self.docker.images.get(MCP_RUNNER_IMAGE)
            except docker.errors.ImageNotFound:
                logger.error(f"MCP runner image not found: {MCP_RUNNER_IMAGE}")
                raise ValueError("MCP runner image not found. Please build it first.")

            # Create and start container
            container = self.docker.containers.run(
                image=MCP_RUNNER_IMAGE,
                command=[npm_package],  # Pass npm package as command
                name=container_name,
                environment=container_env,
                detach=True,
                stdin_open=True,  # Keep stdin open for JSON-RPC
                tty=False,
                network="sterna-sandbox-network",  # Use sandbox network with egress proxy
                mem_limit=DEFAULT_MEMORY_LIMIT,
                cpu_period=100000,
                cpu_quota=int(DEFAULT_CPU_LIMIT * 100000),
                # Security options
                security_opt=["no-new-privileges:true"],
                read_only=False,  # npx needs to write
                # Labels for identification
                labels={
                    "sterna.type": "mcp-server",
                    "sterna.user_id": user_id,
                    "sterna.server_id": server_id,
                    "sterna.npm_package": npm_package,
                },
            )

            # Create instance record
            now = datetime.utcnow()
            instance = MCPServerInstance(
                container_id=container.id,
                container_name=container_name,
                user_id=user_id,
                server_id=server_id,
                npm_package=npm_package,
                status="starting",
                started_at=now,
                last_used=now,
            )

            # Register in tracking
            with self.lock:
                self.servers[container.id] = instance
                if user_id not in self.user_servers:
                    self.user_servers[user_id] = []
                self.user_servers[user_id].append(container.id)

            # Wait for container to start and get IP
            time.sleep(3)

            # Check if container is running
            container.reload()
            if container.status == "running":
                # Get container IP address on the sandbox network
                networks = container.attrs.get('NetworkSettings', {}).get('Networks', {})
                sandbox_net = networks.get('sterna-sandbox-network', {})
                container_ip = sandbox_net.get('IPAddress')

                if container_ip:
                    instance.container_ip = container_ip
                    instance.status = "running"
                    logger.info(f"MCP server started successfully: {container_name} at {container_ip}")
                else:
                    # Try to wait a bit more for network
                    time.sleep(2)
                    container.reload()
                    networks = container.attrs.get('NetworkSettings', {}).get('Networks', {})
                    sandbox_net = networks.get('sterna-sandbox-network', {})
                    container_ip = sandbox_net.get('IPAddress')

                    if container_ip:
                        instance.container_ip = container_ip
                        instance.status = "running"
                        logger.info(f"MCP server started: {container_name} at {container_ip}")
                    else:
                        instance.status = "error"
                        instance.error_message = "Failed to get container IP address"
                        logger.error(f"MCP server started but no IP: {container_name}")
            else:
                logs = container.logs(tail=50).decode('utf-8', errors='replace')
                instance.status = "error"
                instance.error_message = f"Container exited: {logs}"
                logger.error(f"MCP server failed to start: {logs}")

            return instance

        except Exception as e:
            logger.error(f"Failed to start MCP server: {e}")
            # Try to cleanup
            try:
                container = self.docker.containers.get(container_name)
                container.remove(force=True)
            except Exception:
                pass
            raise

    def stop_server(self, container_id: str) -> bool:
        """
        Stop and remove an MCP server container.

        Args:
            container_id: Container ID to stop

        Returns:
            True if successfully stopped
        """
        try:
            with self.lock:
                instance = self.servers.get(container_id)
                if not instance:
                    logger.warning(f"MCP server not found: {container_id}")
                    return False

                # Remove from tracking
                del self.servers[container_id]
                if instance.user_id in self.user_servers:
                    self.user_servers[instance.user_id] = [
                        cid for cid in self.user_servers[instance.user_id]
                        if cid != container_id
                    ]

            # Stop and remove container
            try:
                container = self.docker.containers.get(container_id)
                container.remove(force=True)
                logger.info(f"MCP server stopped: {container_id}")
            except docker.errors.NotFound:
                logger.warning(f"Container already removed: {container_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to stop MCP server: {e}")
            return False

    def get_server(self, container_id: str) -> Optional[MCPServerInstance]:
        """Get server instance by container ID."""
        with self.lock:
            return self.servers.get(container_id)

    def list_user_servers(self, user_id: str) -> List[MCPServerInstance]:
        """List all running servers for a user."""
        with self.lock:
            container_ids = self.user_servers.get(user_id, [])
            return [self.servers[cid] for cid in container_ids if cid in self.servers]

    def send_rpc(
        self,
        container_id: str,
        method: str,
        params: Optional[Dict] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        Send a JSON-RPC request to an MCP server container.

        Uses HTTP to communicate with the container's HTTP wrapper.

        Args:
            container_id: Target container
            method: JSON-RPC method name
            params: Method parameters
            timeout: Request timeout in seconds

        Returns:
            JSON-RPC response
        """
        with self.lock:
            instance = self.servers.get(container_id)
            if not instance:
                raise ValueError(f"Server not found: {container_id}")
            instance.last_used = datetime.utcnow()
            container_ip = instance.container_ip

        if not container_ip:
            return {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "error": {
                    "code": -32000,
                    "message": "Container IP not available",
                },
            }

        try:
            # Build JSON-RPC request
            request = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": method,
                "params": params or {},
            }

            # Send HTTP request to the container's HTTP wrapper
            url = f"http://{container_ip}:3000/rpc"
            logger.debug(f"Sending RPC to {url}: {method}")

            response = requests.post(
                url,
                json=request,
                timeout=timeout,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code != 200:
                logger.error(f"RPC request failed with status {response.status_code}")
                return {
                    "jsonrpc": "2.0",
                    "id": request["id"],
                    "error": {
                        "code": -32000,
                        "message": f"HTTP error: {response.status_code}",
                    },
                }

            return response.json()

        except requests.exceptions.Timeout:
            logger.error(f"RPC request timed out: {container_id}")
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "error": {
                    "code": -32000,
                    "message": "Request timeout",
                },
            }
        except requests.exceptions.ConnectionError as e:
            logger.error(f"RPC connection error: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "error": {
                    "code": -32000,
                    "message": f"Connection error: {str(e)}",
                },
            }
        except Exception as e:
            logger.error(f"RPC error: {e}")
            raise

    def health_check(self, container_id: str) -> Dict[str, Any]:
        """
        Check health of an MCP server container.

        Returns:
            Health status with container info
        """
        with self.lock:
            instance = self.servers.get(container_id)
            if not instance:
                return {"healthy": False, "error": "Server not found"}

        try:
            container = self.docker.containers.get(container_id)
            container.reload()

            is_running = container.status == "running"

            if is_running:
                instance.status = "running"
                return {
                    "healthy": True,
                    "status": container.status,
                    "container_id": container_id,
                    "npm_package": instance.npm_package,
                    "uptime_seconds": (datetime.utcnow() - instance.started_at).total_seconds(),
                }
            else:
                # Get logs for debugging
                logs = container.logs(tail=20).decode('utf-8', errors='replace')
                instance.status = "error"
                instance.error_message = logs
                return {
                    "healthy": False,
                    "status": container.status,
                    "error": logs,
                }

        except docker.errors.NotFound:
            self.stop_server(container_id)
            return {"healthy": False, "error": "Container not found"}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    def discover_tools(self, container_id: str) -> List[Dict]:
        """
        Discover tools available from an MCP server.

        Sends tools/list JSON-RPC request to the server.

        Returns:
            List of tool definitions
        """
        try:
            # Send tools/list request
            response = self.send_rpc(container_id, "tools/list")

            if "error" in response:
                logger.error(f"Tools discovery error: {response['error']}")
                return []

            tools = response.get("result", {}).get("tools", [])

            # Update cached tools
            with self.lock:
                instance = self.servers.get(container_id)
                if instance:
                    instance.tools = tools

            return tools

        except Exception as e:
            logger.error(f"Failed to discover tools: {e}")
            return []

    def call_tool(
        self,
        container_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Call a tool on an MCP server.

        Args:
            container_id: Target server container
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        try:
            params = {"name": tool_name, "arguments": arguments}
            logger.info(f"[MCP] call_tool params: {params}")
            response = self.send_rpc(
                container_id,
                "tools/call",
                params,
            )

            if "error" in response:
                return {
                    "success": False,
                    "error": response["error"],
                }

            return {
                "success": True,
                "result": response.get("result"),
            }

        except Exception as e:
            logger.error(f"Tool call failed: {e}")
            return {
                "success": False,
                "error": {"code": -32000, "message": str(e)},
            }
