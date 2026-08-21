"""
Token Optimization Package for Code Sessions

This package provides utilities to reduce token consumption in the coding agent:
- Conversation summarization (older jobs → summaries)
- Tool result compression (smart truncation of tool outputs)
- Smart context truncation (AST-based file content reduction)
- Smart history pruning (deduplicate reads, collapse read+edit sequences)
- explore_codebase tool (scout agent called by main model when needed)
"""

from .constants import (
    ENABLE_TOKEN_OPTIMIZATION,
    ENABLE_CONVERSATION_SUMMARIZATION,
    ENABLE_TOOL_COMPRESSION,
    ENABLE_SMART_TRUNCATION,
    ENABLE_TWO_PHASE,
    ENABLE_SCOUT_TOOL,
    SCOUT_MODEL_ID,
)
from .history_pruner import prune_conversation_history

__all__ = [
    "ENABLE_TOKEN_OPTIMIZATION",
    "ENABLE_CONVERSATION_SUMMARIZATION",
    "ENABLE_TOOL_COMPRESSION",
    "ENABLE_SMART_TRUNCATION",
    "ENABLE_TWO_PHASE",
    "ENABLE_SCOUT_TOOL",
    "SCOUT_MODEL_ID",
    "prune_conversation_history",
]
