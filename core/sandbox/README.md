# Sterna Sandbox System

Secure sandbox for isolated execution of:
- **Code execution**: Python/Node/Shell run via the coding agent and the `/execute` API
- **MCP servers**: External connectors (GitHub, Notion, Slack, etc.) run as sandboxed child processes
- **Filesystem operations**: Safe read/write/patch/list primitives scoped to a per-user workspace

Isolation is enforced via gVisor (`runsc`) on the Docker/VPS deployment path. See
[Security & Isolation](#-security--isolation) below for exactly where that guarantee holds.

## 🎯 Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                         Sterna Chat                         │
└───────────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
┌───────────────────────────────────────────────────────────────┐
│                     Orchestrator Service                      │
│                (FastAPI + Code Execution)                     │
└───────────────────────────────┬───────────────────────────────┘
                                 │
                 ┌───────────────┼────────────────────┐
                 │                                     │
                 ▼               ▼                     ▼
        ┌────────────────┐ ┌──────────────┐  ┌──────────────────┐
        │  Code /        │ │ MCP Gateway  │  │  Filesystem /    │
        │  Coding Agent  │ │ (in-sandbox  │  │  Workspace ops   │
        │  Executor      │ │  child procs)│  │  (fs/*, ws/*)    │
        └────────┬────────┘ └──────┬───────┘  └────────┬─────────┘
                 │                 │                    │
                 └─────────────────┴────────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │   Egress Proxy (allow-list)   │
                    └──────────────────────────────┘
```

MCP servers no longer run as one container per connector. A single MCP Gateway
(`runtime/mcp-gateway.js`) runs inside the user's sandbox container and manages MCP
servers as child processes (`npx @package/mcp-server`), so all outbound traffic still
goes through the sandbox's own egress proxy. See `orchestrator/mcp_endpoints.py`.

## 📁 Structure

```
sandbox/
├── runtime/                        # Sandbox runtime images (Docker + gVisor)
│   ├── Dockerfile.sandbox-base     # Minimal Python execution image
│   ├── Dockerfile.sandbox-datascience # Full data-science stack (numpy, pandas, ML, viz)
│   ├── Dockerfile.sandbox-ide      # OpenVSCode-based IDE image
│   ├── Dockerfile.egress-proxy     # Egress allow-list proxy (mitmproxy)
│   ├── install-gvisor.sh           # gVisor installation script
│   ├── mcp-gateway.js              # In-sandbox MCP server process manager
│   ├── daemon.json                 # Docker daemon config registering the runsc runtime
│   └── whitelist.txt / allowed-domains.txt # Egress allow-lists
├── orchestrator/                   # Orchestration & code execution service (FastAPI)
│   ├── main.py                     # API entrypoint
│   ├── sandbox_executor.py         # Docker/gVisor container lifecycle
│   ├── mcp_endpoints.py            # Live MCP server API (child-process architecture)
│   ├── coding_agent_runner.py      # Runs opencode inside the sandbox
│   ├── auth.py                     # Fail-closed JWT auth
│   └── tests/                      # pytest suite
├── observability/                  # Shared OpenTelemetry setup
├── scripts/                        # Standalone helper scripts (coding agent runner CLI)
├── build-images.sh                 # Convenience wrapper around the compose build below
└── docker-compose.sandbox.yml      # Sandbox services (orchestrator, egress-proxy) +
                                     # build-only base images (sandbox-base, sandbox-datascience)
```

## 🔐 Security & Isolation

### Container isolation

- **gVisor (`runsc`)**: user-space kernel intercepting syscalls, registered in
  `runtime/daemon.json` and used by `sandbox_executor.py` for every sandbox container it
  creates (`runtime="runsc"`).
- **Non-root**: sandbox processes run as `sandboxuser` (UID 1000).
- **Read-only rootfs**: the root filesystem is mounted read-only.
- **Network isolation**: no network by default; egress only via the allow-listed proxy.

**Deployment scope — read this before trusting the claim above in a given environment.**
gVisor isolation is real and enforced on the **Docker/VPS deployment path**
(`docker-compose.sandbox.yml`, where `sandbox_executor.py` calls the Docker Engine
directly via `docker.from_env()`). It is **not** wired for the **Kubernetes**
deployment: the orchestrator's Kubernetes `Deployment` mounts no `docker.sock`, and this
codebase has no Kubernetes API client anywhere — `sandbox_executor.py`'s only
sandbox-creation path is a raw Docker Engine call. When Docker init fails (as it does in
the k8s pod), `sandbox_executor` is `None` and sandbox-dependent endpoints no-op rather
than actually isolating anything. The Kubernetes manifests deploy the orchestrator with
no working sandbox execution path.

### Resources

- **CPU**: 1 core max (0.25 guaranteed) by default, tunable via `SANDBOX_CPU_LIMIT`.
- **RAM**: 1GB max by default, tunable via `SANDBOX_MEMORY_LIMIT`.
- **PIDs**: capped to prevent fork bombs.
- **Disk**: `/workspace` limited by the sandbox volume.

### Mounts

- `/workspace`: read-write (user's project).
- `/app`: read-only (skill/script code).
- `/tmp`: tmpfs.
- `/run/secrets`: tmpfs (ephemeral tokens, when needed).

## 🚀 Installation

### 1. Install gVisor

```bash
cd sandbox/runtime
sudo ./install-gvisor.sh
```

### 2. Verify the installation

```bash
docker run --rm --runtime=runsc hello-world
```

### 3. Build the images

`docker-compose.sandbox.yml` only has `build:` blocks for `orchestrator` and
`egress-proxy` — the two long-running services `docker compose up` starts.
`sandbox-base` and `sandbox-datascience` are declared in the same file under
the `build-only` profile (never started by `up`) because `sandbox_executor.py`
spawns per-session containers from `sandbox-datascience:latest` by image name,
bypassing compose entirely; they still need to exist locally before the
orchestrator can create a sandbox. One command builds all four:

```bash
cd sandbox
./build-images.sh
# equivalent: docker compose -f docker-compose.sandbox.yml --profile build-only build
# equivalent, from core/: make sandbox-build
```

### 4. Start the sandbox services

```bash
cd sandbox
docker compose -f docker-compose.sandbox.yml up -d
```

## 📝 Usage

### Execute code

```bash
curl -X POST http://localhost:8003/execute \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "print(\"hello\")",
    "language": "python",
    "user_id": "user123",
    "conversation_id": "conv456",
    "timeout": 30
  }'
```

```json
{
  "output": "hello",
  "exit_code": 0,
  "execution_time": 0.5,
  "artifacts": []
}
```

### Filesystem operations

The orchestrator exposes scoped filesystem primitives under `/fs/*`
(`list`, `read`, `write`, `edit`, `delete`, `search`, `bash`, `mkdir`, `metadata`,
`rename`), each operating inside the caller's own `/workspace`. See
`orchestrator/main.py` and `orchestrator/file_tools.py` for the full contract.

### Coding agent

`/coding-agent/execute` runs opencode inside a sandbox container to autonomously
implement or plan a task against a cloned repository; `/coding-agent/progress` polls
status. See `orchestrator/coding_agent_runner.py`.

## 🔐 MCP Server Sandboxing (Connectors)

Model Context Protocol (MCP) servers with stdio transport run as child processes inside
the user's own sandbox container — not in separate per-connector containers.

### Why sandbox MCP servers?

**Problem**: stdio MCP servers previously ran directly in the Django container, causing:
- Insufficient multi-tenant isolation
- Shared CPU/RAM across users
- OAuth tokens visible in a shared memory space
- No network egress control

**Solution**: each MCP server process runs inside the requesting user's already-isolated
sandbox container, managed by the in-sandbox MCP Gateway (`runtime/mcp-gateway.js`):
- Isolation follows the sandbox container's own boundary (gVisor on the Docker/VPS path)
- Resource quotas apply at the sandbox-container level (CPU, memory, PIDs)
- OAuth tokens are injected as env vars for that sandbox only
- Outbound traffic goes through the sandbox's egress allow-list

### API

The orchestrator exposes MCP server management under `/mcp/*`
(see `orchestrator/mcp_endpoints.py`), backed by `SandboxExecutor`'s
`start_mcp_server()` / `stop_mcp_server()` / `call_mcp_tool()` methods in
`orchestrator/sandbox_executor.py`.

## 🎼 Observability

All services are instrumented with OpenTelemetry:

- **Distributed tracing**: track requests across services
- **Metrics**: execution counts, sandbox creations, artifact sizes
- **Structured logging**: JSON logs with trace IDs

```python
from observability.telemetry import setup_telemetry, instrument_fastapi

# In each service
setup_telemetry("orchestrator", use_otlp=True)
instrument_fastapi(app)
```

## 🛠️ Configuration

Key environment variables (see `orchestrator/auth.py` and `orchestrator/sandbox_executor.py`):

```bash
JWT_SECRET_KEY=                    # Required outside DEBUG mode (fails closed if unset)
JWT_ALGORITHM=HS256
DEBUG=False
SANDBOX_MEMORY_LIMIT=1g
SANDBOX_WORKSPACE_SIZE=1024M
```

## 🧪 Tests

```bash
cd orchestrator
pytest
```

Egress allow-list tests also live at the top of this directory:

```bash
python test_egress_whitelist.py
./test_egress_whitelist.sh
./test_whitelist_https.sh
```

## 📚 Further Reading

- `SECURITY_ARCHITECTURE.md` — defense-in-depth layers
- `SECURITY_ANALYSIS.md` — why root inside a sandbox container is dangerous even with
  other protections in place
- `GVISOR_SETUP.md` — gVisor installation details
- `CONTAINER_ARCHITECTURE.md` — container image layout
- `DATA_SCIENCE_GUIDE.md` — the data-science runtime image
- `orchestrator/opencode_harness.py` — how opencode runs inside the sandbox
  (invocation, permission profile, plan/build agent modes)
- `QUICKSTART.md` — local development quick start

## 🔗 Resources

- [gVisor Documentation](https://gvisor.dev/)
- [Docker Security](https://docs.docker.com/engine/security/)
- [OpenTelemetry](https://opentelemetry.io/)
