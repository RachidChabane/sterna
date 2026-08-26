"""Tool orchestration for LLM interactions with MCP tools."""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List

from .exceptions import MCPError
from .models import MCPTool, MCPToolApproval, MCPToolExecution
from .registry import get_registry
from .utils import (
    format_tool_result_for_llm,
    mcp_tools_to_openai_functions,
    sanitize_tool_result,
)

if TYPE_CHECKING:
    from authentication.models import User

logger = logging.getLogger(__name__)


class ToolOrchestrator(ABC):
    """Abstract base class for tool orchestration strategies."""

    def __init__(
        self,
        user: "User",
        session_id: str,
        max_iterations: int = 10,
    ):
        """Initialize orchestrator.

        Args:
            user: User making the request
            session_id: Session ID for tracking
            max_iterations: Maximum number of tool call iterations
        """
        self.user = user
        self.session_id = session_id
        self.max_iterations = max_iterations
        self.registry = get_registry()

    @abstractmethod
    async def orchestrate(
        self,
        llm_client,
        model: str,
        messages: List[Dict[str, Any]],
        available_tools: List[MCPTool],
        **llm_kwargs,
    ) -> Dict[str, Any]:
        """Orchestrate LLM interaction with tools.

        Args:
            llm_client: LLM client instance
            model: Model ID to use
            messages: Initial messages
            available_tools: List of available MCP tools
            **llm_kwargs: Additional parameters for LLM

        Returns:
            Final response from LLM with metadata
        """
        pass


class FunctionCallingOrchestrator(ToolOrchestrator):
    """Orchestrator for models with native function calling support."""

    async def orchestrate(
        self,
        llm_client,
        model: str,
        messages: List[Dict[str, Any]],
        available_tools: List[MCPTool],
        **llm_kwargs,
    ) -> Dict[str, Any]:
        """Orchestrate LLM interaction using function calling.

        This implements the main orchestration loop:
        1. Call LLM with available tools
        2. If LLM requests tool calls, request approval
        3. Execute approved tools
        4. Inject results back into conversation
        5. Repeat until LLM provides final answer or max iterations

        Args:
            llm_client: OpenRouter client instance
            model: Model ID to use
            messages: Initial conversation messages
            available_tools: List of available MCP tools
            **llm_kwargs: Additional parameters for LLM (temperature, etc.)

        Returns:
            Dictionary with:
                - content: Final response content
                - tool_executions: List of tool execution records
                - iterations: Number of iterations performed
                - cost: Total cost
                - usage: Total token usage
        """
        # Convert MCP tools to OpenAI function format
        tools_payload = mcp_tools_to_openai_functions(available_tools)

        # Create tool lookup map
        tool_map = {tool.name: tool for tool in available_tools}

        # Track state
        conversation_messages = messages.copy()
        all_tool_executions: List[MCPToolExecution] = []
        total_cost: float = 0
        total_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        for iteration in range(self.max_iterations):
            logger.info(
                f"Tool orchestration iteration {iteration + 1}/{self.max_iterations}"
            )

            # Call LLM with tools
            response = llm_client.complete(
                model=model,
                messages=conversation_messages,
                tools=tools_payload,
                tool_choice="auto",
                **llm_kwargs,
            )

            # Accumulate costs and usage
            total_cost += float(response.get("cost", 0))
            usage = response.get("usage", {})
            total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
            total_usage["total_tokens"] += usage.get("total_tokens", 0)

            # Check if LLM made tool calls
            tool_calls = response.get("tool_calls", [])

            if not tool_calls:
                # No tool calls - LLM provided final answer
                logger.info("LLM provided final answer without tool calls")
                return {
                    "content": response.get("content", ""),
                    "tool_executions": all_tool_executions,
                    "iterations": iteration + 1,
                    "cost": total_cost,
                    "usage": total_usage,
                    "model": response.get("model", model),
                }

            # Process tool calls
            logger.info(f"LLM requested {len(tool_calls)} tool call(s)")

            # Add assistant message with tool calls to conversation
            assistant_message = {
                "role": "assistant",
                "content": response.get("content") or "",
                "tool_calls": tool_calls,
            }
            conversation_messages.append(assistant_message)

            # Execute each tool call
            for tool_call in tool_calls:
                tool_call_id = tool_call.get("id")
                function = tool_call.get("function", {})
                tool_name = function.get("name")
                arguments_str = function.get("arguments", "{}")

                try:
                    arguments = json.loads(arguments_str)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON arguments for tool {tool_name}")
                    # Add error result to conversation
                    error_message = format_tool_result_for_llm(
                        tool_call_id,
                        tool_name,
                        {
                            "content": [
                                {"text": "Error: Invalid tool arguments format"}
                            ],
                            "is_error": True,
                        },
                    )
                    conversation_messages.append(error_message)
                    continue

                # Check if tool exists
                if tool_name not in tool_map:
                    logger.error(f"Tool {tool_name} not found in available tools")
                    error_message = format_tool_result_for_llm(
                        tool_call_id,
                        tool_name,
                        {
                            "content": [{"text": f"Error: Tool '{tool_name}' not found"}],
                            "is_error": True,
                        },
                    )
                    conversation_messages.append(error_message)
                    continue

                tool = tool_map[tool_name]

                # Request approval
                approval = await self._request_approval(tool, arguments)

                if approval.status != MCPToolApproval.ApprovalStatus.APPROVED:
                    # Tool was rejected
                    logger.info(f"Tool {tool_name} was rejected by user")
                    error_message = format_tool_result_for_llm(
                        tool_call_id,
                        tool_name,
                        {
                            "content": [
                                {
                                    "text": "Tool execution was rejected by user. Please continue without this tool."
                                }
                            ],
                            "is_error": True,
                        },
                    )
                    conversation_messages.append(error_message)
                    continue

                # Execute tool
                execution = await self._execute_tool(tool, arguments, approval)
                all_tool_executions.append(execution)

                # Format result for LLM
                if execution.status == MCPToolExecution.ExecutionStatus.SUCCESS:
                    # Sanitize result to prevent deeply nested structures
                    sanitized_result = sanitize_tool_result(execution.result)
                    result_message = format_tool_result_for_llm(
                        tool_call_id, tool_name, sanitized_result
                    )
                else:
                    # Tool execution failed
                    result_message = format_tool_result_for_llm(
                        tool_call_id,
                        tool_name,
                        {
                            "content": [
                                {"text": f"Error: {execution.error_message}"}
                            ],
                            "is_error": True,
                        },
                    )

                conversation_messages.append(result_message)

            # Continue to next iteration with tool results

        # Max iterations reached
        logger.warning(
            f"Max iterations ({self.max_iterations}) reached in tool orchestration"
        )
        return {
            "content": "Maximum tool iteration limit reached. Please simplify your request.",
            "tool_executions": all_tool_executions,
            "iterations": self.max_iterations,
            "cost": total_cost,
            "usage": total_usage,
            "model": model,
            "error": "max_iterations_reached",
        }

    async def _request_approval(
        self,
        tool: MCPTool,
        arguments: Dict[str, Any],
    ) -> MCPToolApproval:
        """Request approval for tool execution.

        This creates an approval request and waits for user decision.

        Args:
            tool: Tool to request approval for
            arguments: Tool arguments

        Returns:
            Approval instance with user decision
        """
        # Check for existing valid approval
        existing_approvals = MCPToolApproval.objects.filter(
            user=self.user,
            tool=tool,
            status=MCPToolApproval.ApprovalStatus.APPROVED,
        )

        for approval in existing_approvals:
            if approval.is_valid():
                # Check if arguments match (for permanent approvals)
                if approval.scope == MCPToolApproval.ApprovalScope.PERMANENT:
                    logger.info(
                        f"Using existing permanent approval for tool {tool.name}"
                    )
                    return approval
                elif (
                    approval.scope == MCPToolApproval.ApprovalScope.SESSION
                    and approval.session_id == self.session_id
                ):
                    logger.info(f"Using existing session approval for tool {tool.name}")
                    return approval

        # Create new approval request
        approval = MCPToolApproval.objects.create(
            user=self.user,
            tool=tool,
            session_id=self.session_id,
            proposed_arguments=arguments,
            status=MCPToolApproval.ApprovalStatus.PENDING,
        )

        # Wait for approval decision (with timeout)
        # In a real implementation, this would be handled via WebSocket/SSE
        # For now, we'll poll the database
        max_wait = 300  # 5 minutes
        poll_interval = 1  # 1 second

        for _ in range(max_wait // poll_interval):
            await asyncio.sleep(poll_interval)
            approval.refresh_from_db()

            if approval.status != MCPToolApproval.ApprovalStatus.PENDING:
                return approval

        # Timeout - auto-reject
        logger.warning(f"Approval timeout for tool {tool.name}")
        approval.reject()
        return approval

    async def _execute_tool(
        self,
        tool: MCPTool,
        arguments: Dict[str, Any],
        approval: MCPToolApproval,
    ) -> MCPToolExecution:
        """Execute a tool and record execution.

        Args:
            tool: Tool to execute
            arguments: Tool arguments
            approval: Approval record

        Returns:
            Tool execution record
        """
        # Create execution record
        execution = MCPToolExecution.objects.create(
            tool=tool,
            approval=approval,
            session_id=self.session_id,
            arguments=arguments,
            status=MCPToolExecution.ExecutionStatus.PENDING,
        )

        try:
            # Mark as running
            execution.mark_running()

            # Execute via registry
            result = await self.registry.call_tool(tool, arguments)

            # Mark as successful
            execution.mark_success(result)

            logger.info(f"Successfully executed tool {tool.name}")

        except MCPError as e:
            execution.mark_error(str(e))
            logger.error(f"Tool execution failed for {tool.name}: {str(e)}")

        except Exception as e:
            execution.mark_error(f"Unexpected error: {str(e)}")
            logger.error(f"Unexpected error executing tool {tool.name}: {str(e)}")

        return execution


# Factory function to create appropriate orchestrator
def create_orchestrator(
    model_id: str,
    user: "User",
    session_id: str,
    max_iterations: int = 10,
) -> ToolOrchestrator:
    """Create appropriate orchestrator for the model.

    Args:
        model_id: Model ID
        user: User making the request
        session_id: Session ID
        max_iterations: Maximum iterations

    Returns:
        Appropriate ToolOrchestrator instance
    """
    # For now, we only support function calling
    # In the future, we can check model capabilities and return ReActOrchestrator
    # if the model doesn't support function calling

    # TODO: Check model.supports_functions from catalog
    # For now, assume all models support it

    return FunctionCallingOrchestrator(
        user=user,
        session_id=session_id,
        max_iterations=max_iterations,
    )
