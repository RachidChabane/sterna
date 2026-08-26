"""
Agent Orchestrator

Coordinates the two-phase Scout/Editor architecture for efficient code modifications.
Uses a cheap model for exploration and the user's selected model for editing.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .compressor import compress_tool_result
from .constants import (
    EDITOR_MAX_ITERATIONS,
    EDITOR_MODEL_OVERRIDE,
    EDITOR_SYSTEM_PROMPT_TEMPLATE,
    EDITOR_TOOLS,
    ENABLE_CONVERSATION_SUMMARIZATION,
    ENABLE_SMART_TRUNCATION,
    ENABLE_TOKEN_OPTIMIZATION,
    ENABLE_TOOL_COMPRESSION,
    ENABLE_TWO_PHASE,
    FORCE_FULL_CONTEXT,
    MAX_FULL_HISTORY_JOBS,
    MAX_SNIPPET_CHARS,
    MAX_SNIPPETS_FOR_EDITOR,
    SCOUT_MODEL_ID,
)
from .scout import ScoutAgent, ScoutReport
from .summarizer import summarize_conversation_history

logger = logging.getLogger(__name__)


@dataclass
class EditorResult:
    """Result from the editor phase."""
    success: bool = True
    tokens: int = 0
    cost: float = 0.0
    iterations: int = 0
    files_modified: List[str] = field(default_factory=list)
    pr_ready: bool = False
    pr_title: Optional[str] = None
    pr_body: Optional[str] = None
    error: Optional[str] = None


@dataclass
class OrchestratorResult:
    """Combined result from scout + editor phases."""
    scout_report: Optional[ScoutReport] = None
    editor_result: Optional[EditorResult] = None
    total_tokens: int = 0
    total_cost: float = 0.0
    optimization_metrics: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None


class AgentOrchestrator:
    """
    Coordinates two-phase code modification workflow.

    Phase 1 (Scout): Cheap model explores codebase, finds relevant files
    Phase 2 (Editor): Expensive model makes targeted edits using scout findings
    """

    def __init__(
        self,
        job: Any,  # CodeJob instance
        auth_token: str,
        github_token: Optional[str] = None,
        on_step: Optional[Callable[[str, Optional[str], Any], None]] = None,
    ):
        """
        Initialize orchestrator.

        Args:
            job: CodeJob instance with task details
            auth_token: JWT auth token for tool execution
            github_token: Optional GitHub OAuth token
            on_step: Callback for step events (step_type, content, data)
        """
        self.job = job
        self.auth_token = auth_token
        self.github_token = github_token
        self.on_step = on_step
        self._client = None

    @property
    def client(self):
        """Lazy-load the OpenRouter client."""
        if self._client is None:
            from llm.client import OpenRouterClient
            self._client = OpenRouterClient(user=self.job.session.user, request_source='orchestrator')
        return self._client

    def execute(self) -> OrchestratorResult:
        """
        Execute the two-phase workflow.

        Returns:
            OrchestratorResult with combined metrics
        """
        # Check if optimization is disabled
        if FORCE_FULL_CONTEXT or not ENABLE_TOKEN_OPTIMIZATION:
            logger.info("Token optimization disabled, using legacy execution")
            return self._execute_legacy()

        if not ENABLE_TWO_PHASE:
            logger.info("Two-phase disabled, using single-phase with optimizations")
            return self._execute_single_phase_optimized()

        logger.info(f"[Orchestrator] Starting two-phase execution for job {self.job.id}")
        logger.info(f"[Orchestrator] Config: summarization={ENABLE_CONVERSATION_SUMMARIZATION}, "
                   f"compression={ENABLE_TOOL_COMPRESSION}, truncation={ENABLE_SMART_TRUNCATION}")
        logger.info(f"[Orchestrator] Scout model: {SCOUT_MODEL_ID}, Editor model: {self.job.session.model_id}")

        result = OrchestratorResult()
        metrics: Dict[str, Any] = {
            "two_phase_enabled": True,
            "conversation_summarization": ENABLE_CONVERSATION_SUMMARIZATION,
            "tool_compression": ENABLE_TOOL_COMPRESSION,
            "smart_truncation": ENABLE_SMART_TRUNCATION,
        }

        try:
            # Phase 1: Scout (exploration with cheap model)
            # No UI emissions here - let the ThinkingIndicator do its job
            logger.info("[Orchestrator] === PHASE 1: SCOUT ===")

            scout = ScoutAgent(user=self.job.session.user)
            scout_report = scout.explore(
                task=self.job.prompt,
                workspace_path=self._get_workspace_path(),
                auth_token=self.auth_token,
                user_id=str(self.job.session.user_id),
                session_id=str(self.job.session.id),
                on_step=None,  # Don't emit status updates to UI
            )

            result.scout_report = scout_report
            metrics["scout_tokens"] = scout_report.exploration_tokens
            metrics["scout_cost"] = scout_report.exploration_cost
            metrics["scout_iterations"] = scout_report.iterations
            metrics["files_found"] = len(scout_report.files_to_modify)

            logger.info(f"[Orchestrator] Scout completed: {scout_report.iterations} iterations, "
                       f"{scout_report.exploration_tokens} tokens, ${scout_report.exploration_cost:.4f}")
            logger.info(f"[Orchestrator] Scout found {len(scout_report.files_to_modify)} files to modify, "
                       f"{len(scout_report.files_to_create)} files to create")
            if scout_report.files_to_modify:
                logger.info(f"[Orchestrator] Files to modify: {[f.path for f in scout_report.files_to_modify]}")
            if scout_report.approach:
                logger.info(f"[Orchestrator] Scout approach: {scout_report.approach[:200]}...")

            if not scout_report.success:
                logger.warning(f"[Orchestrator] Scout failed: {scout_report.error}")
                # Fall back to single-phase - no status message needed
                return self._execute_single_phase_optimized()

            # Phase 2: Editor (implementation with user's selected model)
            logger.info("[Orchestrator] === PHASE 2: EDITOR ===")
            logger.info(f"[Orchestrator] Using model: {self.job.session.model_id}")

            editor_result = self._run_editor(scout_report)

            logger.info(f"[Orchestrator] Editor completed: {editor_result.iterations} iterations, "
                       f"{editor_result.tokens} tokens, ${editor_result.cost:.4f}")
            logger.info(f"[Orchestrator] Editor modified {len(editor_result.files_modified)} files: "
                       f"{editor_result.files_modified}")
            result.editor_result = editor_result
            metrics["editor_tokens"] = editor_result.tokens
            metrics["editor_cost"] = editor_result.cost
            metrics["editor_iterations"] = editor_result.iterations

            # Calculate totals
            result.total_tokens = (
                scout_report.exploration_tokens + editor_result.tokens
            )
            result.total_cost = (
                scout_report.exploration_cost + editor_result.cost
            )

            # Calculate savings estimate
            # Rough estimate: without optimization, would use ~3x more tokens
            estimated_unoptimized = result.total_tokens * 2.5
            metrics["estimated_savings_tokens"] = int(
                estimated_unoptimized - result.total_tokens
            )
            metrics["estimated_savings_pct"] = (
                1 - (result.total_tokens / estimated_unoptimized)
            ) if estimated_unoptimized > 0 else 0

            result.optimization_metrics = metrics
            result.success = editor_result.success

            logger.info("[Orchestrator] === EXECUTION COMPLETE ===")
            logger.info(f"[Orchestrator] Total tokens: {result.total_tokens} "
                       f"(Scout: {scout_report.exploration_tokens}, Editor: {editor_result.tokens})")
            logger.info(f"[Orchestrator] Total cost: ${result.total_cost:.4f} "
                       f"(Scout: ${scout_report.exploration_cost:.4f}, Editor: ${editor_result.cost:.4f})")
            logger.info(f"[Orchestrator] Estimated savings: {metrics.get('estimated_savings_pct', 0):.1%} "
                       f"({metrics.get('estimated_savings_tokens', 0)} tokens)")
            logger.info(f"[Orchestrator] Success: {result.success}")

            return result

        except Exception as e:
            logger.exception(f"Orchestrator execution failed: {e}")
            result.success = False
            result.error = str(e)
            result.optimization_metrics = metrics
            return result

    def _execute_legacy(self) -> OrchestratorResult:
        """Execute without optimizations (legacy mode)."""
        # This delegates to the original run_agent_loop logic
        # Implemented by returning a result that signals to use legacy path
        return OrchestratorResult(
            success=False,
            error="LEGACY_MODE",
            optimization_metrics={"legacy_mode": True},
        )

    def _execute_single_phase_optimized(self) -> OrchestratorResult:
        """Execute single-phase but with optimizations (compression, summarization)."""
        logger.info("Executing single-phase with optimizations")

        result = OrchestratorResult()
        metrics: Dict[str, Any] = {
            "two_phase_enabled": False,
            "conversation_summarization": ENABLE_CONVERSATION_SUMMARIZATION,
            "tool_compression": ENABLE_TOOL_COMPRESSION,
        }

        # Build optimized context
        messages = self._build_optimized_messages()

        # Get all tools
        tools = self._get_editor_tools()

        # Run agent loop
        editor_result = self._run_agent_loop(
            messages=messages,
            tools=tools,
            max_iterations=EDITOR_MAX_ITERATIONS,
        )

        result.editor_result = editor_result
        result.total_tokens = editor_result.tokens
        result.total_cost = editor_result.cost
        result.success = editor_result.success
        result.optimization_metrics = metrics

        return result

    def _run_editor(self, scout_report: ScoutReport) -> EditorResult:
        """
        Run the editor phase using scout findings.

        Args:
            scout_report: Findings from scout phase

        Returns:
            EditorResult with modification details
        """
        # Build editor context from scout report
        messages = self._build_editor_messages(scout_report)

        # Get editor tools
        tools = self._get_editor_tools()

        # Run agent loop
        return self._run_agent_loop(
            messages=messages,
            tools=tools,
            max_iterations=EDITOR_MAX_ITERATIONS,
        )

    def _build_editor_messages(self, scout_report: ScoutReport) -> List[Dict[str, Any]]:
        """Build messages for editor using scout findings."""
        # Format files to modify
        files_to_modify_str = ""
        for f in scout_report.files_to_modify:
            lines_info = f" (lines {f.relevant_lines})" if f.relevant_lines else ""
            files_to_modify_str += f"- {f.path}{lines_info}: {f.reason}\n"

        if scout_report.files_to_create:
            files_to_modify_str += "\nFiles to create:\n"
            for fc in scout_report.files_to_create:
                files_to_modify_str += f"- {fc.path}: {fc.purpose}\n"

        # Format snippets
        snippets_str = ""
        for s in scout_report.snippets[:MAX_SNIPPETS_FOR_EDITOR]:
            snippets_str += f"\n### {s.path} (lines {s.lines}):\n```\n{s.content[:MAX_SNIPPET_CHARS]}\n```\n"

        # Build system prompt
        system_prompt = EDITOR_SYSTEM_PROMPT_TEMPLATE.format(
            files_to_modify=files_to_modify_str or "No specific files identified",
            approach=scout_report.approach or "Implement the requested changes",
            snippets=snippets_str or "No specific snippets extracted",
        )

        # Add repository context
        system_prompt = self._add_repo_context(system_prompt)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self.job.prompt},
        ]

        return messages

    def _build_optimized_messages(self) -> List[Dict[str, Any]]:
        """Build messages with optimizations but without scout phase."""
        from code_sessions.tasks import _build_coding_system_prompt

        messages = [
            {"role": "system", "content": _build_coding_system_prompt(self.job)},
        ]

        # Add summarized conversation history
        if ENABLE_CONVERSATION_SUMMARIZATION:
            previous_jobs = self._get_previous_jobs()
            if previous_jobs:
                history = summarize_conversation_history(
                    jobs=previous_jobs,
                    max_full_jobs=MAX_FULL_HISTORY_JOBS,
                )

                if history.get("summary"):
                    messages.append({
                        "role": "system",
                        "content": f"## Previous Work\n{history['summary']}",
                    })

                # Add recent jobs in full
                for prev_job in history.get("recent_jobs", []):
                    messages.append({
                        "role": "user",
                        "content": prev_job.prompt,
                    })
                    # Add response if available
                    if prev_job.steps:
                        response = self._extract_response_from_steps(prev_job.steps)
                        if response:
                            messages.append({
                                "role": "assistant",
                                "content": response,
                            })

        # Add current user message
        messages.append({
            "role": "user",
            "content": self.job.prompt,
        })

        return messages

    def _run_agent_loop(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_iterations: int,
    ) -> EditorResult:
        """
        Run the agent loop with tool execution.

        Args:
            messages: Initial messages
            tools: Available tools
            max_iterations: Maximum iterations

        Returns:
            EditorResult
        """
        from llm.file_tools_integration import handle_file_tool_calls

        result = EditorResult()
        model_id = EDITOR_MODEL_OVERRIDE or self.job.session.model_id
        iteration = 0

        try:
            while iteration < max_iterations:
                iteration += 1
                logger.debug(f"Editor iteration {iteration}/{max_iterations}")

                # Call LLM
                llm_result = self.client.complete(
                    model=model_id,
                    messages=messages,
                    max_tokens=8000,
                    tools=tools,
                    tool_choice="auto",
                )

                # Track usage
                usage = llm_result.get("usage", {})
                result.tokens += usage.get("prompt_tokens", 0)
                result.tokens += usage.get("completion_tokens", 0)
                result.cost += float(llm_result.get("cost", 0) or 0)

                content = llm_result.get("content", "")
                tool_calls = llm_result.get("tool_calls", [])

                # Emit text content
                if content:
                    self._emit_step("text", content, {"iteration": iteration})

                # Check if done (no tool calls)
                if not tool_calls:
                    logger.info(f"Editor completed in {iteration} iterations")
                    break

                # Emit tool executing events
                for tc in tool_calls:
                    tool_name = tc.get("function", {}).get("name", "")
                    args = {}
                    try:
                        args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                    except json.JSONDecodeError:
                        pass

                    self._emit_step("tool_executing", None, {
                        "tool_call_id": tc.get("id"),
                        "tool_name": tool_name,
                        "arguments": args,
                    })

                # Execute tools
                tool_results = handle_file_tool_calls(
                    tool_calls=tool_calls,
                    user_id=str(self.job.session.user_id),
                    conversation_id=str(self.job.session.id),
                    chat_id=str(self.job.id),
                    sync_mode=True,
                    auth_token=self.auth_token,
                    github_token=self.github_token,
                )

                # Process results
                for i, tool_result in enumerate(tool_results):
                    tc = tool_calls[i]
                    tool_name = tc.get("function", {}).get("name", "")
                    args = {}
                    try:
                        args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                    except json.JSONDecodeError:
                        pass

                    raw_content = tool_result.get("content", "")

                    # Track file modifications
                    if tool_name in ("write_file", "edit_file"):
                        path = args.get("path", "")
                        if path and path not in result.files_modified:
                            result.files_modified.append(path)

                    # Check for PR preparation
                    if tool_name == "prepare_pull_request":
                        result.pr_ready = True
                        try:
                            pr_data = json.loads(raw_content)
                            if pr_data.get("success"):
                                result.pr_title = args.get("title")
                                result.pr_body = args.get("summary")
                        except json.JSONDecodeError:
                            pass

                    # Emit tool executed event
                    self._emit_step("tool_executed", None, {
                        "tool_call_id": tc.get("id"),
                        "tool_name": tool_name,
                        "result": raw_content[:2000],  # Truncate for UI
                        "success": "error" not in raw_content.lower(),
                    })

                    # Compress for context if enabled
                    if ENABLE_TOOL_COMPRESSION:
                        compressed = compress_tool_result(tool_name, raw_content, args)
                        tool_result["content"] = compressed

                # Add to messages
                messages.append({
                    "role": "assistant",
                    "content": content or "",
                    "tool_calls": tool_calls,
                })

                for tool_result in tool_results:
                    messages.append(tool_result)

            result.iterations = iteration
            result.success = True

        except Exception as e:
            logger.exception(f"Editor loop failed: {e}")
            result.success = False
            result.error = str(e)
            result.iterations = iteration

        return result

    def _get_editor_tools(self) -> List[Dict[str, Any]]:
        """Get tools available to editor."""
        from sandbox.orchestrator.file_tools import FILE_TOOLS
        from sandbox.orchestrator.mcp_tools import get_github_mcp_tools

        tools = []
        for tool in FILE_TOOLS:
            tool_name = tool.get("function", {}).get("name", "")
            if tool_name in EDITOR_TOOLS:
                tools.append(tool)

        # Add GitHub tools if connected
        if self.job.session.github_repo_full_name:
            tools.extend(get_github_mcp_tools())

        return tools

    def _get_workspace_path(self) -> str:
        """Get workspace path for this job."""
        return f"/workspace/chat-{self.job.session.id}/repo"

    def _get_previous_jobs(self) -> List[Any]:
        """Get previous jobs in this session."""
        from code_sessions.models import CodeJob

        return list(
            CodeJob.objects.filter(
                session=self.job.session,
                status__in=["completed", "failed"],
            )
            .exclude(id=self.job.id)
            .order_by("created_at")
        )

    def _add_repo_context(self, prompt: str) -> str:
        """Add repository context to system prompt."""
        if self.job.session.github_repo_full_name:
            repo_info = f"\n\n## Repository\n- Name: {self.job.session.github_repo_full_name}"
            if self.job.session.github_branch:
                repo_info += f"\n- Branch: {self.job.session.github_branch}"
            return prompt + repo_info
        return prompt

    def _extract_response_from_steps(self, steps: List[Dict]) -> str:
        """Extract text response from job steps."""
        texts = []
        for step in steps:
            if step.get("type") == "text" and step.get("content"):
                texts.append(step["content"])
        return "\n\n".join(texts[:2])  # Limit to first 2 text blocks

    def _emit_step(self, step_type: str, content: Optional[str], data: Optional[Dict] = None):
        """Emit a step event."""
        if self.on_step:
            self.on_step(step_type, content, data or {})


def create_orchestrator(
    job: Any,
    auth_token: str,
    github_token: Optional[str] = None,
    on_step: Optional[Callable] = None,
) -> AgentOrchestrator:
    """Create a new orchestrator instance."""
    return AgentOrchestrator(
        job=job,
        auth_token=auth_token,
        github_token=github_token,
        on_step=on_step,
    )
