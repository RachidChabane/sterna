"""
Programmatic Tool Calling (PTC) Module

Enables LLM to orchestrate tools through code execution.
Based on Anthropic's Programmatic Tool Calling pattern.

Key benefits:
- Intermediate results don't pollute LLM context
- Parallel tool execution possible
- Complex workflows in single inference pass
- 37% token reduction on complex tasks
"""

from .engine import (
    PTCEngine,
    PTCExecutionResult,
    PTCToolBinding,
)
from .code_generator import (
    PTCCodeGenerator,
)
from .tool import (
    PTCToolContext,
    create_ptc_tool,
    set_ptc_context,
    get_ptc_context,
    is_complex_programming_task,
    PTC_EXAMPLE_TASKS,
)

__all__ = [
    "PTCEngine",
    "PTCExecutionResult",
    "PTCToolBinding",
    "PTCCodeGenerator",
    "PTCToolContext",
    "create_ptc_tool",
    "set_ptc_context",
    "get_ptc_context",
    "is_complex_programming_task",
    "PTC_EXAMPLE_TASKS",
]
