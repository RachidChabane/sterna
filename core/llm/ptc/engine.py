"""
PTC Engine

Programmatic Tool Calling engine that allows LLM to orchestrate
tools through code execution.

Implements Anthropic's PTC pattern where:
- LLM generates Python code that calls tools
- Tools execute in sandbox, results stay in execution context
- Only final output returns to LLM context
- Enables parallel execution and complex orchestration
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, Awaitable
import httpx

logger = logging.getLogger(__name__)


@dataclass
class PTCToolBinding:
    """
    Binding for a tool in the PTC execution context.

    Represents a tool that can be called from generated code.
    """
    tool_id: str
    name: str  # Function name in generated code
    description: str
    executor: Callable[..., Awaitable[Any]]  # Async function to execute
    is_idempotent: bool = False  # Safe for retry
    can_parallel: bool = True  # Safe for parallel execution
    timeout_seconds: int = 30


@dataclass
class PTCToolCall:
    """Record of a tool call during PTC execution."""
    tool_id: str
    arguments: Dict[str, Any]
    timestamp: float
    duration_ms: float = 0
    success: bool = False
    error: Optional[str] = None
    result_size: int = 0


@dataclass
class PTCExecutionResult:
    """Result of a PTC code execution."""
    stdout: str
    stderr: str
    success: bool
    exit_code: int
    tools_called: List[PTCToolCall] = field(default_factory=list)
    execution_time_ms: float = 0
    total_tool_time_ms: float = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "tools_called": len(self.tools_called),
            "execution_time_ms": self.execution_time_ms,
            "total_tool_time_ms": self.total_tool_time_ms,
        }


class PTCEngine:
    """
    Programmatic Tool Calling Engine.

    Allows the LLM to generate Python code that orchestrates multiple tools.
    Intermediate results stay in the code execution context, only final
    output returns to the LLM's context.

    Benefits:
    - Reduces context pollution from intermediate results
    - Enables parallel tool execution
    - Complex workflows in single inference pass
    - 37% token reduction on complex research tasks
    """

    def __init__(
        self,
        orchestrator_url: str = "http://orchestrator:8003",
        default_timeout: int = 300
    ):
        """
        Initialize the PTC engine.

        Args:
            orchestrator_url: URL of the sandbox orchestrator service
            default_timeout: Default timeout for code execution
        """
        self.orchestrator_url = orchestrator_url
        self.default_timeout = default_timeout
        self._tool_bindings: Dict[str, PTCToolBinding] = {}
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=60.0)
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def register_tool(self, binding: PTCToolBinding):
        """
        Register a tool for PTC execution.

        Args:
            binding: Tool binding with executor function
        """
        self._tool_bindings[binding.tool_id] = binding
        logger.info(f"[PTC] Registered tool: {binding.tool_id}")

    def unregister_tool(self, tool_id: str):
        """Unregister a tool."""
        if tool_id in self._tool_bindings:
            del self._tool_bindings[tool_id]

    def get_registered_tools(self) -> List[PTCToolBinding]:
        """Get all registered tools."""
        return list(self._tool_bindings.values())

    async def execute_code(
        self,
        code: str,
        context: Dict[str, Any],
        timeout_seconds: Optional[int] = None
    ) -> PTCExecutionResult:
        """
        Execute LLM-generated code with tool access.

        The code can call registered tools via:
        - result = await tool_name(arg1=value1, arg2=value2)
        - results = await asyncio.gather(*[tool_name(...) for item in items])

        Args:
            code: Python code to execute
            context: Execution context (user_id, conversation_id, etc.)
            timeout_seconds: Execution timeout

        Returns:
            PTCExecutionResult with stdout, stderr, and tool call records
        """
        timeout = timeout_seconds or self.default_timeout
        start_time = time.time()
        tools_called: List[PTCToolCall] = []

        # Create tool wrappers that track calls
        tool_wrappers = {}
        for tool_id, binding in self._tool_bindings.items():
            tool_wrappers[binding.name] = self._create_tool_wrapper(
                binding, tools_called, context
            )

        # Build execution environment
        # Note: In production, this would execute in the sandbox
        # For now, we prepare the code for sandbox execution
        execution_code = self._prepare_code_for_sandbox(code, tool_wrappers.keys())

        try:
            # Execute via orchestrator sandbox
            result = await self._execute_in_sandbox(
                code=execution_code,
                context=context,
                timeout=timeout,
                tools_called=tools_called
            )

            execution_time = (time.time() - start_time) * 1000
            total_tool_time = sum(tc.duration_ms for tc in tools_called)

            return PTCExecutionResult(
                stdout=result.get("output", ""),
                stderr=result.get("error", ""),
                success=result.get("exit_code", 1) == 0,
                exit_code=result.get("exit_code", 1),
                tools_called=tools_called,
                execution_time_ms=execution_time,
                total_tool_time_ms=total_tool_time,
            )

        except asyncio.TimeoutError:
            logger.error(f"[PTC] Execution timeout after {timeout}s")
            return PTCExecutionResult(
                stdout="",
                stderr=f"Execution timed out after {timeout} seconds",
                success=False,
                exit_code=-1,
                tools_called=tools_called,
                execution_time_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"[PTC] Execution failed: {e}")
            return PTCExecutionResult(
                stdout="",
                stderr=str(e),
                success=False,
                exit_code=-1,
                tools_called=tools_called,
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    def _create_tool_wrapper(
        self,
        binding: PTCToolBinding,
        tools_called: List[PTCToolCall],
        context: Dict[str, Any]
    ) -> Callable:
        """
        Create an async wrapper for a tool that tracks calls.

        Args:
            binding: Tool binding
            tools_called: List to record calls
            context: Execution context

        Returns:
            Async wrapper function
        """
        async def wrapper(**kwargs) -> Any:
            call_start = time.time()
            call_record = PTCToolCall(
                tool_id=binding.tool_id,
                arguments=kwargs,
                timestamp=call_start,
            )
            tools_called.append(call_record)

            try:
                # Execute the tool
                result = await asyncio.wait_for(
                    binding.executor(**kwargs, _context=context),
                    timeout=binding.timeout_seconds
                )

                call_record.duration_ms = (time.time() - call_start) * 1000
                call_record.success = True
                call_record.result_size = len(str(result))

                return result

            except asyncio.TimeoutError:
                call_record.duration_ms = (time.time() - call_start) * 1000
                call_record.success = False
                call_record.error = f"Tool timeout after {binding.timeout_seconds}s"
                raise

            except Exception as e:
                call_record.duration_ms = (time.time() - call_start) * 1000
                call_record.success = False
                call_record.error = str(e)
                raise

        return wrapper

    def _prepare_code_for_sandbox(
        self,
        code: str,
        tool_names: List[str]
    ) -> str:
        """
        Prepare code for sandbox execution.

        Wraps the code with necessary imports and tool stubs.

        Args:
            code: Original code
            tool_names: Names of available tools

        Returns:
            Prepared code string
        """
        # Note: In production, tools are injected by the sandbox
        # This prepares the code structure
        header = """
import asyncio
import json
from typing import Any, Dict, List

# Tool functions are injected by the execution environment
# Available tools: {tools}

async def main():
    # User code begins here
""".format(tools=", ".join(tool_names))

        # Indent user code
        indented_code = "\n".join("    " + line for line in code.split("\n"))

        footer = """

# Run the main function
if __name__ == "__main__":
    asyncio.run(main())
"""

        return header + indented_code + footer

    async def _execute_in_sandbox(
        self,
        code: str,
        context: Dict[str, Any],
        timeout: int,
        tools_called: List[PTCToolCall]
    ) -> Dict[str, Any]:
        """
        Execute code in the sandbox environment.

        Args:
            code: Prepared code
            context: Execution context
            timeout: Timeout in seconds
            tools_called: List to record tool calls

        Returns:
            Execution result from sandbox
        """
        client = await self._get_client()

        # Prepare request for orchestrator
        request_data = {
            "code": code,
            "language": "python",
            "timeout": timeout,
            "user_id": context.get("user_id"),
            "conversation_id": context.get("conversation_id"),
            "chat_id": context.get("chat_id"),
            "sync_mode": True,
            "ptc_mode": True,  # Enable PTC tool injection
            "available_tools": list(self._tool_bindings.keys()),
        }

        try:
            response = await client.post(
                f"{self.orchestrator_url}/execute",
                json=request_data,
                headers={
                    "Authorization": f"Bearer {context.get('auth_token', '')}",
                }
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"[PTC] Sandbox HTTP error: {e.response.status_code}")
            return {
                "output": "",
                "error": f"Sandbox error: {e.response.text}",
                "exit_code": -1
            }

        except httpx.RequestError as e:
            logger.error(f"[PTC] Sandbox request error: {e}")
            return {
                "output": "",
                "error": f"Failed to connect to sandbox: {e}",
                "exit_code": -1
            }

    def generate_tool_documentation(self) -> str:
        """
        Generate documentation for available tools in PTC context.

        Returns:
            Markdown documentation string
        """
        lines = ["# Available Tools for Programmatic Execution\n"]

        for tool_id, binding in self._tool_bindings.items():
            lines.append(f"## {binding.name}")
            lines.append(f"**ID:** `{tool_id}`")
            lines.append(f"**Description:** {binding.description}")
            lines.append(f"**Idempotent:** {'Yes' if binding.is_idempotent else 'No'}")
            lines.append(f"**Parallel Safe:** {'Yes' if binding.can_parallel else 'No'}")
            lines.append(f"**Timeout:** {binding.timeout_seconds}s")
            lines.append("")

        return "\n".join(lines)
