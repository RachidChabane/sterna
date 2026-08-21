"""
Coding Agent CLI Output Parser

Parses the stream-json output format from Coding Agent CLI.
Each line is a JSON object representing an event in the execution.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ClaudeStep:
    """A single step in Coding Agent execution."""
    type: str  # 'thinking', 'text', 'tool_use', 'tool_result', 'error'
    tool: Optional[str] = None
    content: Optional[str] = None
    input: Optional[Dict[str, Any]] = None
    output: Optional[str] = None


@dataclass
class ClaudeExecutionResult:
    """Parsed result from Coding Agent CLI execution."""
    success: bool
    summary: Optional[str] = None
    steps: List[ClaudeStep] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    files_created: List[str] = field(default_factory=list)
    files_deleted: List[str] = field(default_factory=list)
    error: Optional[str] = None
    total_tokens: int = 0
    duration_ms: int = 0
    total_cost_usd: float = 0.0  # Cost from OpenRouter API calls


class ClaudeOutputParser:
    """
    Parser for Coding Agent CLI stream-json output.

    The CLI outputs newline-delimited JSON objects (NDJSON).
    Each object has a 'type' field indicating the event type.
    """

    # Tool names that modify files
    FILE_WRITE_TOOLS = {'Write', 'write_file', 'create_file'}
    FILE_EDIT_TOOLS = {'Edit', 'edit_file', 'str_replace_editor'}
    FILE_DELETE_TOOLS = {'Delete', 'delete_file', 'rm'}
    FILE_READ_TOOLS = {'Read', 'read_file', 'cat'}

    def __init__(self):
        self.steps: List[ClaudeStep] = []
        self.files_modified: set = set()
        self.files_created: set = set()
        self.files_deleted: set = set()
        self.files_read: set = set()  # Track files that existed before
        self.error: Optional[str] = None
        self.summary: Optional[str] = None
        self.total_tokens: int = 0
        self.total_cost_usd: float = 0.0  # Cost from OpenRouter API
        self.last_assistant_message: str = ""
        # Track sub-agent Task results — these contain the actual analysis
        # that the main agent may summarize away
        self._sub_agent_results: List[str] = []

    def parse_line(self, line: str) -> Optional[ClaudeStep]:
        """Parse a single line of stream-json output."""
        line = line.strip()
        if not line:
            return None

        try:
            event = json.loads(line)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON line: {e}")
            return None

        return self._process_event(event)

    def _process_event(self, event: Dict[str, Any]) -> Optional[ClaudeStep]:
        """Process a parsed JSON event."""
        event_type = event.get('type', '')

        # Handle different event types based on Coding Agent CLI stream-json output format
        # The CLI outputs nested structures: {"type": "assistant", "message": {"content": [...]}}

        if event_type == 'system':
            # System messages (startup, init, etc.)
            # Format: {"type": "system", "subtype": "init", "cwd": "...", "tools": [...], ...}
            subtype = event.get('subtype', '')
            return ClaudeStep(type='system', content=f"System: {subtype}")

        elif event_type == 'assistant':
            # Assistant response with nested message structure
            # Format: {"type": "assistant", "message": {"content": [{"type": "text", "text": "..."}, ...]}}
            # Sub-agent messages have parent_tool_use_id set; main agent messages don't
            is_sub_agent = bool(event.get('parent_tool_use_id'))
            message = event.get('message', {})
            if isinstance(message, dict):
                content_blocks = message.get('content', [])
                if isinstance(content_blocks, list):
                    # Process each content block
                    steps_created = []
                    for block in content_blocks:
                        if isinstance(block, dict):
                            block_type = block.get('type', '')

                            if block_type == 'text':
                                # Text content — only track main agent messages for summary
                                text = block.get('text', '')
                                if text and not is_sub_agent:
                                    self.last_assistant_message = text
                                    steps_created.append(ClaudeStep(type='text', content=text))

                            elif block_type == 'tool_use':
                                # Tool call embedded in assistant message
                                tool_name = block.get('name', '')
                                tool_input = block.get('input', {})
                                step = ClaudeStep(
                                    type='tool_call',
                                    tool=tool_name,
                                    content=f"Using {tool_name}",
                                    input=tool_input
                                )
                                # Track file operations
                                self._track_file_operation(tool_name, tool_input)
                                steps_created.append(step)

                    # Return first step, add rest to self.steps directly
                    if steps_created:
                        for extra_step in steps_created[1:]:
                            self.steps.append(extra_step)
                        return steps_created[0]
            return None

        elif event_type == 'user':
            # User message (initial task or tool results)
            # Format: {"type": "user", "message": {"content": [{"type": "tool_result", ...}]}}
            is_sub_agent = bool(event.get('parent_tool_use_id'))
            message = event.get('message', {})
            if isinstance(message, dict):
                content_blocks = message.get('content', [])
                if isinstance(content_blocks, list):
                    for block in content_blocks:
                        if isinstance(block, dict):
                            block_type = block.get('type', '')
                            if block_type == 'tool_result':
                                content = block.get('content', '')
                                is_error = block.get('is_error', False)

                                # Capture sub-agent Task results returned to the main agent.
                                # These contain the actual analysis that the main agent may
                                # summarize away. We preserve them for the summary fallback.
                                if not is_sub_agent and not is_error and content:
                                    text_content = self._extract_text_from_tool_result(content)
                                    if text_content and len(text_content) > 200:
                                        self._sub_agent_results.append(text_content)

                                return ClaudeStep(
                                    type='tool_result',
                                    content=str(content) if content else None,
                                    output=str(content) if content else None
                                )
            # Check for tool_use_result shorthand
            tool_result = event.get('tool_use_result')
            if tool_result:
                return ClaudeStep(type='tool_result', output=str(tool_result))
            return None

        elif event_type == 'tool_use':
            # Direct tool invocation (legacy format)
            tool_name = event.get('name', event.get('tool', ''))
            tool_input = event.get('input', {})

            step = ClaudeStep(
                type='tool_call',
                tool=tool_name,
                content=f"Using {tool_name}",
                input=tool_input
            )

            # Track file operations
            self._track_file_operation(tool_name, tool_input)
            return step

        elif event_type == 'tool_result':
            # Tool result (legacy format)
            content = event.get('content', event.get('output', ''))
            tool_name = event.get('name', event.get('tool', ''))

            return ClaudeStep(
                type='tool_result',
                tool=tool_name,
                output=str(content)
            )

        elif event_type == 'error':
            # Error event
            self.error = event.get('message', event.get('error', 'Unknown error'))
            return ClaudeStep(type='error', content=self.error)

        elif event_type == 'result':
            # Final result event
            # Format: {"type": "result", "subtype": "success", "result": "...", "usage": {...}, "total_cost_usd": 0.05}
            self.summary = event.get('result', event.get('summary', ''))

            # Extract cost from OpenRouter API calls
            self.total_cost_usd = event.get('total_cost_usd', 0.0)

            # Extract token usage
            usage = event.get('usage', {})
            if usage:
                self.total_tokens = (
                    usage.get('input_tokens', 0) +
                    usage.get('output_tokens', 0)
                )

            # Also check modelUsage for detailed breakdown
            model_usage = event.get('modelUsage', {})
            if model_usage:
                for model_info in model_usage.values():
                    if isinstance(model_info, dict):
                        self.total_tokens = max(
                            self.total_tokens,
                            model_info.get('inputTokens', 0) + model_info.get('outputTokens', 0)
                        )

            return ClaudeStep(type='result', content=self.summary)

        elif event_type == 'thinking':
            # Extended thinking/reasoning
            return ClaudeStep(type='thinking', content=event.get('content', ''))

        elif event_type in ('content_block_start', 'content_block_delta', 'content_block_stop'):
            # Streaming content blocks - extract text
            if 'content_block' in event:
                block = event['content_block']
                if block.get('type') == 'text':
                    return ClaudeStep(type='text', content=block.get('text', ''))
                elif block.get('type') == 'tool_use':
                    tool_name = block.get('name', '')
                    tool_input = block.get('input', {})
                    self._track_file_operation(tool_name, tool_input)
                    return ClaudeStep(
                        type='tool_call',
                        tool=tool_name,
                        input=tool_input
                    )
            elif 'delta' in event:
                delta = event['delta']
                if delta.get('type') == 'text_delta':
                    return ClaudeStep(type='text', content=delta.get('text', ''))
            return None

        elif event_type == 'message_start':
            # Message metadata
            if 'usage' in event.get('message', {}):
                usage = event['message']['usage']
                self.total_tokens += usage.get('input_tokens', 0)
            return None

        elif event_type == 'message_delta':
            # Message completion metadata
            if 'usage' in event:
                self.total_tokens += event['usage'].get('output_tokens', 0)
            return None

        else:
            # Unknown event type - log and skip
            logger.debug(f"Unknown event type: {event_type}")
            return None

    @staticmethod
    def _extract_text_from_tool_result(content) -> str:
        """Extract text from a tool_result content field.

        Content can be a string or a list of content blocks like:
        [{"type": "text", "text": "..."}]
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get('type') == 'text':
                    texts.append(item.get('text', ''))
            return '\n'.join(texts)
        return str(content)

    def _track_file_operation(self, tool_name: str, tool_input: Dict[str, Any]):
        """Track file operations to determine what was created/modified."""
        # Get file path from various possible input formats
        file_path = (
            tool_input.get('path') or
            tool_input.get('file_path') or
            tool_input.get('filename') or
            tool_input.get('file') or
            ''
        )

        if not file_path:
            return

        # Normalize path (remove leading ./)
        if file_path.startswith('./'):
            file_path = file_path[2:]

        if tool_name in self.FILE_WRITE_TOOLS:
            # Write creates new files or overwrites
            if file_path in self.files_read:
                self.files_modified.add(file_path)
            else:
                self.files_created.add(file_path)

        elif tool_name in self.FILE_EDIT_TOOLS:
            # Edit always modifies existing files
            self.files_modified.add(file_path)
            # Remove from created if it was just created
            self.files_created.discard(file_path)

        elif tool_name in self.FILE_DELETE_TOOLS:
            self.files_deleted.add(file_path)
            self.files_created.discard(file_path)
            self.files_modified.discard(file_path)

        elif tool_name in self.FILE_READ_TOOLS:
            # Track that this file existed before
            self.files_read.add(file_path)

    def parse_output(self, output: str) -> ClaudeExecutionResult:
        """Parse the complete output from Coding Agent CLI."""
        for line in output.split('\n'):
            step = self.parse_line(line)
            if step:
                self.steps.append(step)

        return self.get_result()

    def get_result(self) -> ClaudeExecutionResult:
        """Get the final parsed result."""
        # Determine success - no error and we have some output
        success = self.error is None and len(self.steps) > 0

        # Build summary with priority:
        # 1. Explicit result from CLI (non-empty)
        # 2. Sub-agent results + main agent text (when main agent summarized away detail)
        # 3. Last assistant message as fallback
        summary = self.summary  # From the 'result' event

        if not summary and self._sub_agent_results:
            # The main agent received detailed sub-agent output but the CLI result
            # field was empty (e.g. session ended after a failed tool call).
            # Use sub-agent results as the primary content, with the main agent's
            # commentary appended.
            parts = list(self._sub_agent_results)
            if self.last_assistant_message:
                parts.append(self.last_assistant_message)
            summary = '\n\n'.join(parts)
        elif not summary:
            summary = self.last_assistant_message
        # Don't truncate summary - full output modal should show everything

        return ClaudeExecutionResult(
            success=success,
            summary=summary,
            steps=self.steps,
            files_modified=list(self.files_modified),
            files_created=list(self.files_created),
            files_deleted=list(self.files_deleted),
            error=self.error,
            total_tokens=self.total_tokens,
            total_cost_usd=self.total_cost_usd,
        )


def parse_claude_output(output: str) -> ClaudeExecutionResult:
    """Convenience function to parse Coding Agent CLI output."""
    parser = ClaudeOutputParser()
    return parser.parse_output(output)
