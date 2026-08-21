# MCP (Model Context Protocol) Implementation

This implementation lets LLMs with function calling use external tools via the MCP protocol.

## 🔒 Architecture: WebSocket Only

**This implementation uses ONLY the WebSocket transport** to guarantee multi-tenant isolation and security.

### Why WebSocket only?

**Multi-tenant security**:
- ❌ **stdio**: Local processes inside the Django container = risk of cross-user compromise
- ✅ **WebSocket**: Each user runs their own server = full isolation

### Advantages of WebSocket:

- **Full isolation**: Each user has their own MCP server on their own infrastructure
- **Secure secrets**: API tokens stay with the user
- **Scalable**: No shared resource limits
- **Flexible**: Local (`ws://`) or remote (`wss://`) servers

## Architecture

### 1. Django Models (`models.py`)

#### MCPServer
Configures the connection to an MCP server:
- **Transport**: WebSocket only (`ws://` or `wss://`)
- **Auth**: Flexible configuration via JSON
- **Status**: Connection and error tracking
- **Per user**: Each user configures their own servers

#### MCPTool
Cache of tools discovered from the servers:
- **name**, **description**, **input_schema** (JSON Schema)
- Automatic refresh (TTL: 1 hour)

#### MCPToolApproval
Manual approval workflow:
- **Status**: pending, approved, rejected
- **Scope**: once (single use), session (24h), permanent
- The user must approve every tool execution

#### MCPToolExecution
Full audit trail:
- Arguments, results, errors
- Execution duration
- Link to the approval

### 2. MCP Client (`client.py`)

Full implementation of the MCP protocol over WebSocket:

```python
# WebSocket connection
client = MCPWebSocketClient(url="ws://localhost:8080")
await client.connect()
await client.handshake()

# Discovery
tools = await client.list_tools()
resources = await client.list_resources()
prompts = await client.list_prompts()

# Execution
result = await client.call_tool("tool_name", {"arg": "value"})
```

Classes:
- **`MCPClientBase`**: Abstract interface
- **`MCPWebSocketClient`**: WebSocket implementation
- **`create_mcp_client(url, ...)`**: Factory function

### 3. Registry (`registry.py`)

Centralized management of MCP servers:

```python
registry = get_registry()

# Discovery
tools = await registry.discover_tools(server)

# All of a user's tools
all_tools = await registry.get_available_tools(user)

# Execution
result = await registry.call_tool(tool, arguments)
```

Features:
- **Cache**: 1h cache for discoveries
- **Health checks**: Server status verification
- **Persistent connections**: Pool of active clients

### 4. REST API (`views.py`, `serializers.py`)

Full set of endpoints:

#### MCP Servers
- `GET /api/mcp/servers/` - List servers
- `POST /api/mcp/servers/` - Create a server
- `POST /api/mcp/servers/{id}/test_connection/` - Test the connection
- `POST /api/mcp/servers/{id}/discover_tools/` - Discover tools

#### Tools
- `GET /api/mcp/tools/` - List available tools
- `POST /api/mcp/tools/{id}/call/` - Request execution (creates an approval)

#### Approvals
- `GET /api/mcp/approvals/` - List approvals
- `GET /api/mcp/approvals/pending/` - Pending approvals
- `POST /api/mcp/approvals/{id}/approve/` - Approve
- `POST /api/mcp/approvals/{id}/reject/` - Reject

#### Executions
- `GET /api/mcp/executions/` - Execution history
- `GET /api/mcp/executions/recent/` - Last 50 executions

### 5. Orchestration (`orchestrator.py`)

Orchestration loop for models with function calling:

```python
orchestrator = FunctionCallingOrchestrator(
    user=user,
    session_id=session_id,
    max_iterations=10
)

result = await orchestrator.orchestrate(
    llm_client=openrouter_client,
    model="anthropic/claude-3-sonnet",
    messages=conversation_messages,
    available_tools=mcp_tools
)
```

**Workflow:**
1. The LLM receives the available tools
2. The LLM requests a tool_call
3. The system requests user approval
4. If approved → execution → result reinjected into the conversation
5. Repeat until a final response (max 10 iterations)

**Security:**
- Every execution requires approval
- Permanent approvals are supported for trusted tools
- Rate limiting: 10 tool calls max per conversation

### 6. OpenRouter Extension (`llm/client.py`)

The OpenRouter client was extended to support tools:

```python
response = client.complete(
    model="anthropic/claude-3-sonnet",
    messages=messages,
    tools=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a location",
            "parameters": {...}  # JSON Schema
        }
    }],
    tool_choice="auto"
)

# Response includes tool_calls if the model wants to call a tool
if response.get("tool_calls"):
    # Handle the tool_calls
    ...
```

### 7. Utilities (`utils.py`)

Helper functions:
- **`mcp_tool_to_openai_function()`**: Converts MCP → OpenAI format
- **`validate_tool_arguments()`**: JSON Schema validation
- **`extract_tool_calls_from_response()`**: Parses LLM responses
- **`format_tool_result_for_llm()`**: Formats results
- **`sanitize_tool_result()`**: Secures results (depth limit)

## Installation

### Dependencies

Added to `requirements.txt`:
```
websockets==14.1
```

### Migrations

```bash
docker-compose exec web python manage.py makemigrations mcp
docker-compose exec web python manage.py migrate mcp
```

## Configuration

### Example: WebSocket MCP Server

```json
POST /api/mcp/servers/
{
    "name": "My MCP server",
    "description": "Productivity tools",
    "transport_type": "websocket",
    "url": "ws://localhost:8080",
    "auth_config": {
        "api_key": "sk_xxx"
    },
    "is_active": true
}
```

**Note**: The user must run their own MCP server with WebSocket support:

```bash
# Example: launching an MCP server in WebSocket mode
npx -y @modelcontextprotocol/server-example --transport websocket --port 8080
```

## Usage

### 1. Configure an MCP server

Via the API or the Django admin interface:
- Admin → MCP → MCP servers → Add

### 2. Discover the tools

```bash
POST /api/mcp/servers/1/discover_tools/
{
    "force_refresh": false
}
```

### 3. In a conversation

When a model with `supports_functions=True` wants to use a tool:

1. It makes a tool_call
2. The system creates an `MCPToolApproval` (status=pending)
3. The user receives a notification
4. The user approves/rejects via the API
5. If approved → the tool executes → the result is sent back to the model

## Remaining work

### Backend
- ✅ Models, migrations
- ✅ MCP client (WebSocket only)
- ✅ Registry
- ✅ REST API
- ✅ Orchestration
- ⏳ Integration with `ConsigliereChatHandler`
- ⏳ Real-time notifications (WebSocket/SSE for approvals)
- ⏳ Full test coverage

### Frontend
- ⏳ MCP server management UI
- ⏳ Tool approval UI
- ⏳ Display tool calls in chat
- ⏳ Zustand store
- ⏳ TypeScript API client

## Security

✅ **Implemented**:
- Parameter validation (JSON Schema)
- Per-user isolation
- Full audit trail
- Manual approval workflow

⏳ **To add**:
- Per-endpoint rate limiting
- Advanced result sanitization
- Configurable timeouts
- Per-user quotas

## Extensible architecture

The code is designed to easily support:

### ReAct (for models without function calling)

```python
class ReActOrchestrator(ToolOrchestrator):
    """For pure-text models without function calling."""

    async def orchestrate(...):
        # Parse <TOOL name="..." args="...">
        # Execute
        # Reinject <RESULT>...</RESULT>
        ...
```

### Other protocols

The `MCPClientBase` interface can be extended to support other similar protocols.

## Tests

```bash
# Unit tests
docker-compose exec web pytest mcp/tests/test_client.py
docker-compose exec web pytest mcp/tests/test_registry.py

# Integration tests
docker-compose exec web pytest mcp/tests/test_api.py

# e2e tests
docker-compose exec web pytest mcp/tests/test_orchestration.py
```

## Monitoring

Tables to watch:
- **`mcp_mcptoolexecution`**: Failures, durations, patterns
- **`mcp_mcptoolapproval`**: Approval rate, timeouts
- **`mcp_mcpserver`**: Server health

## Resources

- [MCP Specification](https://modelcontextprotocol.io/docs/concepts/architecture)
- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)
- [Anthropic Tool Use](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)
