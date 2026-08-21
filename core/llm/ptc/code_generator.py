"""
PTC Code Generator

Provides patterns and documentation to help the LLM generate
effective orchestration code for Programmatic Tool Calling.
"""

import logging
from typing import List, Dict, Any, Optional

from ..tool_catalog.models import ToolDefinition

logger = logging.getLogger(__name__)


class PTCCodeGenerator:
    """
    Generates documentation and patterns for PTC code generation.

    Helps the LLM understand:
    - Available tools and their signatures
    - Parallel execution patterns
    - Data aggregation patterns
    - Error handling patterns
    """

    # Pattern templates for common workflows
    PATTERNS = {
        "parallel_batch": '''
# Pattern: Parallel batch processing
async def process_batch(items, batch_size=10):
    """Process items in parallel batches."""
    results = []
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        batch_results = await asyncio.gather(*[
            process_single(item) for item in batch
        ])
        results.extend(batch_results)
    return results
''',

        "aggregate_filter": '''
# Pattern: Aggregate and filter results
async def aggregate_and_filter(data_sources):
    """Gather from multiple sources and filter."""
    # Parallel fetch
    all_results = await asyncio.gather(*[
        fetch_data(source) for source in data_sources
    ])

    # Flatten and filter
    combined = []
    for result in all_results:
        if result.get("success"):
            combined.extend(result.get("items", []))

    # Filter by criteria
    filtered = [item for item in combined if meets_criteria(item)]

    # Return summary
    return {
        "total_fetched": len(combined),
        "total_filtered": len(filtered),
        "top_results": filtered[:10]
    }
''',

        "search_and_process": '''
# Pattern: Search then process results
async def search_and_analyze(query):
    """Search for data and analyze results."""
    # Search
    search_result = await brave_web_search(query=query, count=10)
    data = json.loads(search_result)

    if not data.get("success"):
        return {"error": "Search failed"}

    # Process each result
    processed = []
    for item in data.get("results", []):
        summary = {
            "title": item.get("title"),
            "url": item.get("url"),
            "snippet": item.get("description", "")[:200]
        }
        processed.append(summary)

    # Return structured output
    print(json.dumps({
        "query": query,
        "count": len(processed),
        "results": processed
    }))
''',

        "multi_tool_workflow": '''
# Pattern: Multi-tool orchestration
async def complex_workflow():
    """Orchestrate multiple tools."""
    # Step 1: Get initial data
    initial = await tool_a(param="value")

    # Step 2: Process based on initial results
    ids = extract_ids(initial)

    # Step 3: Parallel fetch details
    details = await asyncio.gather(*[
        tool_b(id=id) for id in ids
    ])

    # Step 4: Aggregate
    summary = aggregate(details)

    # Return only final result
    print(json.dumps(summary))
''',

        "error_handling": '''
# Pattern: Error handling with retries
async def safe_tool_call(tool_func, max_retries=3, **kwargs):
    """Call tool with retry on failure."""
    for attempt in range(max_retries):
        try:
            result = await tool_func(**kwargs)
            return json.loads(result)
        except Exception as e:
            if attempt == max_retries - 1:
                return {"error": str(e), "success": False}
            await asyncio.sleep(1)  # Brief delay before retry
'''
    }

    @classmethod
    def get_available_tools_for_ptc(
        cls,
        tools: List[ToolDefinition]
    ) -> List[Dict[str, Any]]:
        """
        Get tools available for PTC with their signatures.

        Filters tools that have code_execution in allowed_callers.

        Args:
            tools: List of tool definitions

        Returns:
            List of tool info dicts for PTC
        """
        ptc_tools = []

        for tool in tools:
            # Check if tool can be called from code
            if tool.allowed_callers and "code_execution" in tool.allowed_callers:
                ptc_tools.append({
                    "id": tool.id,
                    "name": tool.id.replace(".", "_"),  # Python-safe name
                    "description": tool.description,
                    "signature": cls._generate_signature(tool),
                    "returns": "JSON string",
                    "is_async": True,
                    "is_idempotent": tool.is_idempotent,
                })

        return ptc_tools

    @classmethod
    def _generate_signature(cls, tool: ToolDefinition) -> str:
        """
        Generate Python function signature for a tool.

        Args:
            tool: Tool definition

        Returns:
            Signature string like "await tool_name(param1: str, param2: int = 10)"
        """
        params = []
        schema = tool.input_schema

        if not schema or "properties" not in schema:
            return f"await {tool.id}()"

        required = set(schema.get("required", []))

        for name, prop in schema.get("properties", {}).items():
            param_type = cls._json_type_to_python(prop.get("type", "any"))
            is_required = name in required

            if is_required:
                params.append(f"{name}: {param_type}")
            else:
                default = prop.get("default", "None")
                if isinstance(default, str):
                    default = f'"{default}"'
                params.append(f"{name}: {param_type} = {default}")

        return f"await {tool.id}({', '.join(params)})"

    @staticmethod
    def _json_type_to_python(json_type: str) -> str:
        """Convert JSON Schema type to Python type hint."""
        type_map = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "array": "List",
            "object": "Dict",
        }
        return type_map.get(json_type, "Any")

    @classmethod
    def generate_ptc_prompt(
        cls,
        tools: List[ToolDefinition],
        task_description: str
    ) -> str:
        """
        Generate a prompt to help the LLM write PTC code.

        Args:
            tools: Available tools
            task_description: What the code should accomplish

        Returns:
            Prompt string with tools and patterns
        """
        ptc_tools = cls.get_available_tools_for_ptc(tools)

        if not ptc_tools:
            return "No tools available for programmatic execution."

        lines = [
            "# Programmatic Tool Calling",
            "",
            "Write Python code to accomplish the following task:",
            f"**Task:** {task_description}",
            "",
            "## Available Tools",
            "",
        ]

        for tool in ptc_tools:
            lines.append(f"### {tool['name']}")
            lines.append("```python")
            lines.append(f"# {tool['description']}")
            lines.append(f"result = {tool['signature']}")
            lines.append(f"# Returns: {tool['returns']}")
            lines.append("```")
            lines.append("")

        lines.extend([
            "## Guidelines",
            "",
            "1. Use `await` for all tool calls (they are async)",
            "2. Parse JSON results with `json.loads(result)`",
            "3. Use `asyncio.gather()` for parallel execution",
            "4. Print final results with `print(json.dumps(output))`",
            "5. Handle errors gracefully",
            "6. Only print the final output (intermediate data stays in code)",
            "",
            "## Example Pattern",
            "",
            "```python",
            cls.PATTERNS["search_and_process"],
            "```",
        ])

        return "\n".join(lines)

    @classmethod
    def generate_tool_stubs(cls, tools: List[ToolDefinition]) -> str:
        """
        Generate Python stub functions for tools.

        Useful for IDE autocompletion and type checking.

        Args:
            tools: Tool definitions

        Returns:
            Python code with stub functions
        """
        lines = [
            '"""Auto-generated tool stubs for PTC."""',
            "",
            "from typing import Any, Dict, List, Optional",
            "import asyncio",
            "import json",
            "",
        ]

        ptc_tools = cls.get_available_tools_for_ptc(tools)

        for tool in ptc_tools:
            # Generate async stub function
            lines.append(f"async def {tool['name']}(")

            # Parse signature for parameters
            tool_def = next((t for t in tools if t.id == tool['id']), None)
            if tool_def and tool_def.input_schema:
                params = []
                schema = tool_def.input_schema
                required = set(schema.get("required", []))

                for name, prop in schema.get("properties", {}).items():
                    ptype = cls._json_type_to_python(prop.get("type", "any"))
                    if name in required:
                        params.append(f"    {name}: {ptype}")
                    else:
                        default = prop.get("default", "None")
                        if isinstance(default, str):
                            default = f'"{default}"'
                        params.append(f"    {name}: {ptype} = {default}")

                lines.append(",\n".join(params))

            lines.append(") -> str:")
            lines.append(f'    """{tool["description"]}"""')
            lines.append("    ...")
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def get_pattern(cls, pattern_name: str) -> Optional[str]:
        """
        Get a code pattern by name.

        Args:
            pattern_name: Pattern name

        Returns:
            Pattern code or None
        """
        return cls.PATTERNS.get(pattern_name)

    @classmethod
    def list_patterns(cls) -> List[str]:
        """Get list of available pattern names."""
        return list(cls.PATTERNS.keys())
