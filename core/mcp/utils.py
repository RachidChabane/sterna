"""Utility functions for MCP integration."""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Type, Union

from .models import MCPTool
from .protocol import MCPToolDefinition

logger = logging.getLogger(__name__)


def sanitize_tool_name(name: str) -> str:
    """
    Sanitize a string for use in tool names.

    Anthropic requires tool names to match: ^[a-zA-Z0-9_-]{1,128}$

    Args:
        name: The string to sanitize (e.g., server name, tool name)

    Returns:
        Sanitized string with only alphanumeric, underscore, and hyphen chars
    """
    # Replace spaces with underscores
    sanitized = name.replace(" ", "_")
    # Remove any characters not in [a-zA-Z0-9_-]
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', sanitized)
    # Ensure it's not empty and not too long
    if not sanitized:
        sanitized = "unknown"
    return sanitized[:128]


def mcp_tool_to_openai_function(tool: MCPTool) -> Dict[str, Any]:
    """Convert an MCP tool to OpenAI function calling format.

    Args:
        tool: MCPTool instance

    Returns:
        Dictionary in OpenAI function calling format
    """
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def mcp_tools_to_openai_functions(tools: List[MCPTool]) -> List[Dict[str, Any]]:
    """Convert multiple MCP tools to OpenAI function calling format.

    Args:
        tools: List of MCPTool instances

    Returns:
        List of dictionaries in OpenAI function calling format
    """
    return [mcp_tool_to_openai_function(tool) for tool in tools]


def mcp_tool_definition_to_openai_function(
    tool_def: MCPToolDefinition,
) -> Dict[str, Any]:
    """Convert an MCP tool definition to OpenAI function calling format.

    Args:
        tool_def: MCPToolDefinition instance

    Returns:
        Dictionary in OpenAI function calling format
    """
    return {
        "type": "function",
        "function": {
            "name": tool_def.name,
            "description": tool_def.description,
            "parameters": tool_def.inputSchema,
        },
    }


def validate_tool_arguments(
    tool: MCPTool,
    arguments: Dict[str, Any],
) -> tuple[bool, str]:
    """Validate tool arguments against the input schema.

    This is a basic validation. For production use, consider using
    jsonschema library for full JSON Schema validation.

    Args:
        tool: MCPTool instance
        arguments: Arguments to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    schema = tool.input_schema

    # Check required properties
    required = schema.get("required", [])
    for prop in required:
        if prop not in arguments:
            return False, f"Missing required parameter: {prop}"

    # Check property types (basic validation)
    properties = schema.get("properties", {})
    for key, value in arguments.items():
        if key not in properties:
            # Unknown parameter
            continue

        prop_schema = properties[key]
        expected_type = prop_schema.get("type")

        if expected_type:
            # Basic type checking
            type_map: Dict[str, Union[Type[Any], Tuple[Type[Any], ...]]] = {
                "string": str,
                "number": (int, float),
                "integer": int,
                "boolean": bool,
                "array": list,
                "object": dict,
            }

            if expected_type in type_map:
                expected_python_type = type_map[expected_type]
                if not isinstance(value, expected_python_type):
                    return (
                        False,
                        f"Parameter '{key}' should be of type {expected_type}",
                    )

    return True, ""


def extract_tool_calls_from_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract tool calls from LLM response.

    Supports both OpenAI format and other provider formats.

    Args:
        response: LLM response dictionary

    Returns:
        List of tool call dictionaries with 'name' and 'arguments'
    """
    tool_calls = []

    # OpenAI format: response.choices[0].message.tool_calls
    if "choices" in response and response["choices"]:
        message = response["choices"][0].get("message", {})
        if "tool_calls" in message:
            for tool_call in message["tool_calls"]:
                if tool_call.get("type") == "function":
                    function = tool_call.get("function", {})
                    tool_calls.append({
                        "id": tool_call.get("id"),
                        "name": function.get("name"),
                        "arguments": function.get("arguments"),
                    })

    return tool_calls


def format_tool_result_for_llm(
    tool_call_id: str,
    tool_name: str,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """Format tool execution result for LLM context.

    Args:
        tool_call_id: ID of the tool call
        tool_name: Name of the tool
        result: Tool execution result

    Returns:
        Formatted message for LLM
    """
    # Extract content from MCP result format
    content = result.get("content", [])

    # Convert content to string
    if isinstance(content, list) and content:
        # MCP returns content as a list of content blocks
        content_str = "\n".join(
            block.get("text", json.dumps(block)) for block in content
        )
    else:
        content_str = json.dumps(content)

    # OpenAI tool result format
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": content_str,
    }


def chunk_large_result(result: str, max_size: int = 4000) -> List[str]:
    """Chunk a large result into smaller pieces.

    Args:
        result: Result string to chunk
        max_size: Maximum size of each chunk

    Returns:
        List of chunks
    """
    if len(result) <= max_size:
        return [result]

    chunks = []
    for i in range(0, len(result), max_size):
        chunk = result[i : i + max_size]
        chunks.append(chunk)

    return chunks


def sanitize_tool_result(result: Any, max_depth: int = 5) -> Any:
    """Sanitize tool result to prevent deeply nested structures.

    Args:
        result: Result to sanitize
        max_depth: Maximum allowed nesting depth

    Returns:
        Sanitized result
    """

    def _sanitize(obj: Any, depth: int) -> Any:
        if depth >= max_depth:
            return str(obj)

        if isinstance(obj, dict):
            return {k: _sanitize(v, depth + 1) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_sanitize(item, depth + 1) for item in obj]
        else:
            return obj

    return _sanitize(result, 0)


async def call_tool_via_orchestrator(tool: MCPTool, arguments: Dict) -> Dict[str, Any]:
    """Call an MCP tool on a sandboxed npm-based server via the orchestrator.

    Args:
        tool: MCPTool instance
        arguments: Tool arguments

    Returns:
        Tool execution result
    """
    import httpx
    from django.conf import settings

    server = tool.server
    orchestrator_url = getattr(settings, "ORCHESTRATOR_URL", "http://orchestrator:8003")

    # Build request payload with server config for on-demand container start
    payload = {
        "user_id": str(server.user_id),
        "server_id": str(server.id),
        "tool_name": tool.name,
        "arguments": arguments,
        # Include server config so orchestrator can start container on-demand
        "npm_package": server.npm_package,
        "env_vars": server.get_effective_env_vars(),
        "allowed_domains": server.allowed_domains or [],
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{orchestrator_url}/mcp/call-tool",
                json=payload,
            )

            if response.status_code != 200:
                error_detail = response.json().get("detail", "Unknown error")
                return {
                    "content": [{"text": f"Tool call failed: {error_detail}"}],
                    "is_error": True,
                }

            result = response.json()
            return {
                "content": result.get("result", {}).get("content", []),
                "is_error": result.get("result", {}).get("isError", False),
            }

    except Exception as e:
        logger.error(f"Orchestrator call failed for {tool.name}: {e}")
        return {
            "content": [{"text": f"Orchestrator error: {str(e)}"}],
            "is_error": True,
        }


_model_counter = 0

def _create_pydantic_model_from_schema(name: str, schema: Dict[str, Any]):
    """Create a Pydantic model dynamically from a JSON schema.

    This allows LangChain to properly validate and pass arguments to MCP tools.
    Handles nested objects and arrays with proper type information.
    """
    global _model_counter
    from pydantic import Field, create_model
    from typing import Any, List as TypingList, Optional as TypingOptional

    def get_python_type(prop_schema: Dict[str, Any], prop_name: str) -> tuple:
        """Recursively determine Python type from JSON schema, returns (type, description)."""
        global _model_counter
        prop_type = prop_schema.get("type", "string")
        description = prop_schema.get("description", "")

        if prop_type == "string":
            return str, description
        elif prop_type == "integer":
            return int, description
        elif prop_type == "number":
            return float, description
        elif prop_type == "boolean":
            return bool, description
        elif prop_type == "array":
            items_schema = prop_schema.get("items", {})
            items_type = items_schema.get("type", "string")

            if items_type == "object":
                # Create a nested model for object items
                items_properties = items_schema.get("properties", {})
                items_required = set(items_schema.get("required", []))

                if items_properties:
                    # Build description that shows the expected object structure
                    obj_desc = _build_object_description(items_properties, items_required)
                    full_desc = f"{description}. Each item should be a JSON object with: {obj_desc}" if description else f"Array of JSON objects with: {obj_desc}"

                    # Create nested Pydantic model for items
                    _model_counter += 1
                    nested_model_name = f"{name}_{prop_name}_Item_{_model_counter}"
                    nested_model = _create_nested_model(nested_model_name, items_schema)
                    # nested_model is a dynamically-built Pydantic model class
                    # (its exact type is only known at runtime), so it cannot
                    # be a statically valid type argument for List[...].
                    return TypingList[nested_model], full_desc  # type: ignore[valid-type]
                else:
                    return TypingList[Dict[str, Any]], description
            elif items_type == "string":
                return TypingList[str], description
            elif items_type == "integer":
                return TypingList[int], description
            elif items_type == "number":
                return TypingList[float], description
            else:
                return TypingList[Any], description
        elif prop_type == "object":
            obj_properties = prop_schema.get("properties", {})
            if obj_properties:
                obj_required = set(prop_schema.get("required", []))
                obj_desc = _build_object_description(obj_properties, obj_required)
                full_desc = f"{description}. Object with: {obj_desc}" if description else f"Object with: {obj_desc}"
                return Dict[str, Any], full_desc
            return Dict[str, Any], description
        else:
            return Any, description

    def _build_object_description(properties: Dict, required: set) -> str:
        """Build a description of an object's expected structure."""
        parts = []
        for pname, pschema in properties.items():
            ptype = pschema.get("type", "string")
            req_marker = "(required)" if pname in required else "(optional)"
            if ptype == "array":
                items_type = pschema.get("items", {}).get("type", "any")
                parts.append(f'"{pname}": array of {items_type}s {req_marker}')
            else:
                parts.append(f'"{pname}": {ptype} {req_marker}')
        return "{" + ", ".join(parts) + "}"

    def _create_nested_model(model_name: str, obj_schema: Dict) -> type:
        """Create a Pydantic model for a nested object."""
        nested_properties = obj_schema.get("properties", {})
        nested_required = set(obj_schema.get("required", []))
        nested_fields = {}

        for nprop_name, nprop_schema in nested_properties.items():
            nprop_type = nprop_schema.get("type", "string")
            ndesc = nprop_schema.get("description", "")

            # Truncate description to reduce token usage
            if ndesc and len(ndesc) > 100:
                ndesc = ndesc[:100].rsplit(' ', 1)[0] + '...'

            py_type: Any
            if nprop_type == "string":
                py_type = str
            elif nprop_type == "integer":
                py_type = int
            elif nprop_type == "number":
                py_type = float
            elif nprop_type == "boolean":
                py_type = bool
            elif nprop_type == "array":
                py_type = TypingList[Any]
            elif nprop_type == "object":
                py_type = Dict[str, Any]
            else:
                py_type = Any

            if nprop_name in nested_required:
                nested_fields[nprop_name] = (py_type, Field(description=ndesc))
            else:
                nested_fields[nprop_name] = (TypingOptional[py_type], Field(default=None, description=ndesc))

        # mypy's overload matching for **dict unpacking against create_model's
        # keyword-only overloads is a known limitation independent of the
        # value type (reproduces even with Dict[str, Any]); field_definitions
        # is genuinely dynamic (schema-driven), so it can't be passed as
        # literal keyword arguments instead.
        return create_model(model_name, **nested_fields)  # type: ignore[call-overload]

    # Build field definitions for the main model
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    field_definitions = {}
    for prop_name, prop_schema in properties.items():
        python_type, description = get_python_type(prop_schema, prop_name)

        # Truncate description to reduce token usage
        if description and len(description) > 100:
            description = description[:100].rsplit(' ', 1)[0] + '...'

        # Create field with default if not required
        if prop_name in required:
            field_definitions[prop_name] = (python_type, Field(description=description))
        else:
            field_definitions[prop_name] = (TypingOptional[python_type], Field(default=None, description=description))

    # Create the model dynamically (see the type: ignore note in
    # _create_nested_model above re: **dict unpacking vs. overloads).
    return create_model(name, **field_definitions)  # type: ignore[call-overload]


def _format_mcp_tool_result(tool_name: str, result: Dict[str, Any]) -> str:
    """Format MCP tool result in a standardized, readable format.

    Produces clean output that displays well in the frontend UI.

    Args:
        tool_name: Name of the tool that was executed
        result: Raw result from MCP tool execution

    Returns:
        Formatted JSON string for display
    """
    content = result.get("content", [])
    is_error = result.get("is_error", False)

    # Extract text content from MCP format
    if isinstance(content, list) and content:
        # MCP returns content as a list of content blocks
        text_parts = []
        for block in content:
            if isinstance(block, dict):
                text_parts.append(block.get("text", ""))
            elif isinstance(block, str):
                text_parts.append(block)
        raw_content = "\n".join(filter(None, text_parts))
    elif isinstance(content, str):
        raw_content = content
    else:
        raw_content = json.dumps(content, indent=2)

    # Try to parse as JSON for better formatting
    parsed_data = None
    if raw_content:
        try:
            parsed_data = json.loads(raw_content)
        except (json.JSONDecodeError, TypeError):
            pass

    if is_error:
        # Error format
        output = {
            "status": "error",
            "tool": tool_name,
            "error": parsed_data if parsed_data else raw_content,
        }
    else:
        # Success format - use parsed data if available for clean structure
        if parsed_data is not None:
            # If it's a list/dict, include directly (not as string)
            output = {
                "status": "success",
                "tool": tool_name,
                "data": parsed_data,
            }
        else:
            # Plain text result
            output = {
                "status": "success",
                "tool": tool_name,
                "message": raw_content if raw_content else "Operation completed successfully",
            }

    # Return properly formatted JSON (indent for readability)
    return json.dumps(output, indent=2, ensure_ascii=False)


def mcp_tools_to_langchain_tools(
    tools: List[MCPTool],
    user_id: Optional[str] = None,
) -> List[Any]:
    """Convert MCP tools to LangChain StructuredTool format.

    Creates LangChain tools that route calls to MCP servers via the registry.

    Args:
        tools: List of MCPTool instances
        user_id: User ID for authorization (optional)

    Returns:
        List of LangChain StructuredTool instances
    """
    from langchain_core.tools import StructuredTool

    langchain_tools = []

    for mcp_tool in tools:
        # Create a wrapper function for this tool
        def create_tool_func(tool: MCPTool):
            """Create a closure that captures the tool reference."""
            async def tool_func(**kwargs) -> str:
                """Execute the MCP tool via the appropriate channel."""

                # Unwrap if LangChain wrapped args in 'kwargs' key (shouldn't happen with proper schema)
                if 'kwargs' in kwargs and len(kwargs) == 1 and isinstance(kwargs['kwargs'], dict):
                    kwargs = kwargs['kwargs']
                    logger.debug(f"Unwrapped kwargs for {tool.name}: {kwargs}")

                # Fix for when model passes JSON strings instead of objects in arrays
                for key, value in kwargs.items():
                    if isinstance(value, list):
                        fixed_list = []
                        for item in value:
                            if isinstance(item, str):
                                try:
                                    fixed_list.append(json.loads(item))
                                except json.JSONDecodeError:
                                    fixed_list.append(item)
                            else:
                                fixed_list.append(item)
                        kwargs[key] = fixed_list

                # Convert Pydantic model instances to dicts for JSON serialization
                from pydantic import BaseModel
                def to_serializable(obj):
                    if isinstance(obj, BaseModel):
                        return obj.model_dump()
                    elif isinstance(obj, dict):
                        return {k: to_serializable(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [to_serializable(item) for item in obj]
                    else:
                        return obj

                kwargs = to_serializable(kwargs)
                logger.debug(f"Serialized kwargs for {tool.name}: {kwargs}")

                try:
                    # Check if this is an npm-based sandboxed server
                    server = tool.server
                    if server.npm_package:
                        # Use orchestrator for npm-based sandboxed servers
                        result = await call_tool_via_orchestrator(tool, kwargs)
                    else:
                        # Use V1 registry for OAuth/command-based servers
                        from mcp.registry import get_registry
                        registry = get_registry()
                        result = await registry.call_tool(tool, kwargs)

                    # Format the result using standardized output
                    return _format_mcp_tool_result(tool.name, result)

                except Exception as e:
                    logger.error(f"MCP tool {tool.name} execution failed: {e}")
                    return json.dumps({
                        "status": "error",
                        "tool": tool.name,
                        "error": str(e),
                    }, indent=2)

            # Sync wrapper for LangChain (it handles async internally)
            def sync_wrapper(**kwargs) -> str:
                """Sync wrapper that runs the async function."""
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If we're already in an async context, create a task
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(
                                asyncio.run,
                                tool_func(**kwargs)
                            )
                            return future.result(timeout=60)
                    else:
                        return loop.run_until_complete(tool_func(**kwargs))
                except RuntimeError:
                    # No event loop, create one
                    return asyncio.run(tool_func(**kwargs))

            return sync_wrapper

        # Build the args schema from the input_schema
        # Create a proper Pydantic model for LangChain
        server_prefix = sanitize_tool_name(mcp_tool.server.name).lower()
        tool_name_sanitized = sanitize_tool_name(mcp_tool.name)
        full_name = f"mcp_{server_prefix}_{tool_name_sanitized}"

        # Create dynamic Pydantic model from MCP input schema
        input_schema = mcp_tool.input_schema or {"type": "object", "properties": {}}
        try:
            # Create a valid Python class name (remove hyphens for Python identifier)
            model_name = f"MCPArgs_{server_prefix}_{tool_name_sanitized}".replace("-", "_")
            args_schema = _create_pydantic_model_from_schema(model_name, input_schema)
        except Exception as e:
            logger.warning(f"[MCP] Failed to create schema for {full_name}: {e}, using fallback")
            args_schema = None

        # Truncate description to reduce token usage (full description available via get_tool_details)
        desc = mcp_tool.description or mcp_tool.name
        # Strip markdown headers and truncate
        desc = re.sub(r'^#+\s*\w+\s*\n', '', desc.strip())
        desc = re.sub(r'\n+', ' ', desc)[:200]
        if len(mcp_tool.description or '') > 200:
            desc = desc.rsplit(' ', 1)[0] + '...'

        # Create the LangChain StructuredTool
        langchain_tool = StructuredTool.from_function(
            func=create_tool_func(mcp_tool),
            name=full_name,
            description=f"[MCP: {mcp_tool.server.name}] {desc}",
            args_schema=args_schema,
        )

        langchain_tools.append(langchain_tool)
        logger.info(f"[MCP] Created LangChain tool: {full_name}")

    logger.info(f"[MCP] Converted {len(langchain_tools)} MCP tools to LangChain format")
    return langchain_tools
