"""Coercion of raw LLM-supplied tool arguments into Python values.

Single responsibility: repair the shapes models emit for structured tool
arguments before they reach a tool implementation. No I/O, no agent
state.
"""

import json
from typing import Any, Dict


def parse_json_string_values(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively parse JSON string values in tool arguments.

    LLMs sometimes pass nested objects as JSON strings instead of actual objects.
    This function detects and parses those strings.

    Example:
        {"parent": '{"page_id": "123"}'}  ->  {"parent": {"page_id": "123"}}
    """
    if not isinstance(args, dict):
        return args

    parsed = {}
    for key, value in args.items():
        if isinstance(value, str):
            # Try to parse as JSON if it looks like an object or array
            stripped = value.strip()
            if (stripped.startswith('{') and stripped.endswith('}')) or \
               (stripped.startswith('[') and stripped.endswith(']')):
                try:
                    parsed[key] = json.loads(value)
                except json.JSONDecodeError:
                    parsed[key] = value
            else:
                parsed[key] = value
        elif isinstance(value, dict):
            parsed[key] = parse_json_string_values(value)
        elif isinstance(value, list):
            parsed[key] = [
                parse_json_string_values(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            parsed[key] = value

    return parsed
