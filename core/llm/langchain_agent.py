"""
LangChain Agent for File Tools

This is the live, production streaming agent (LangChainStreamingAgent),
used directly by llm/views.py. It handles streaming chat with an
automatic tool calling loop, and integrates with the on-demand tool
discovery and optimized prompt systems (see ENABLE_TOOL_DISCOVERY and
ENABLE_OPTIMIZED_PROMPTS in llm/constants.py).
"""

# Logging convention: error/critical/exception calls use the
# structured form (event name + extra=). Info-level [LangChain]
# diagnostics retain f-strings pending follow-up cleanup.

# `asyncio` and `CatalogService` below are imported into this module on
# purpose even where this file no longer calls them: `llm.langchain_agent`
# is the published import path, and the test suite patches
# `llm.langchain_agent.asyncio.sleep` and
# `llm.langchain_agent.CatalogService.get_model_pricing` through it.
import asyncio
import logging
from typing import Dict, Any, List, Optional

# Applied at import time: preserves the OpenRouter generation ID that
# LangChain would otherwise drop from streaming chunks (needed for
# post-abort billing settlement).
from .agent import generation_id_patch  # noqa: F401

from .agent.chat_model_factory import build_extra_body, create_chat_model
from .agent.coding_agent_progress import CodingAgentProgressReporter
from .agent.content_sources import extract_brave_search_sources, extract_web_sources
from .agent.cost_ledger import (
    CostLedger,
    IMAGE_GEN_TOOL_NAMES,
    extract_billable_tool_costs,
)
from .agent.feature_flags import AgentFeatureFlags
from .agent.key_resolution import EndpointKeyResolver
from .agent.message_conversion import convert_messages
from .agent.prompt_assembly import build_agent_system_prompt
from .agent.sse_events import (
    add_display_names,
    format_tool_result_for_llm,
    post_tool_events,
)
from .agent.streaming.context_compaction_retry import ContextCompactionRetry
from .agent.streaming.direct_client import DirectClientStreamMixin
from .agent.streaming.langchain_path import LangChainStreamMixin
from .agent.thinking_parser import ThinkingContentParser
from .agent.tool_arguments import parse_json_string_values
from .agent.tool_naming import unsanitize_tool_name
from .agent.tool_registry import AgentToolRegistry
from .catalog_service import CatalogService
from .client import OpenRouterClient
from .constants import ENABLE_TOOL_DISCOVERY
from .langchain_file_tools import CODING_AGENT_TOOL_NAMES, FileToolsContext

# Names re-exported for callers that import them from this module
# (llm/views.py, usage_quota tests) or patch them here.
__all__ = [
    "CODING_AGENT_TOOL_NAMES",
    "CatalogService",
    "IMAGE_GEN_TOOL_NAMES",
    "LangChainStreamingAgent",
    "extract_billable_tool_costs",
]

logger = logging.getLogger(__name__)

# Backwards-compatible aliases for the names that moved into `llm.agent`.
# `llm.langchain_agent` is the published import path (llm/views.py,
# llm/__init__.py, usage_quota tests), so every name callers import from
# here keeps resolving here.
_parse_json_string_values = parse_json_string_values
_unsanitize_tool_name = unsanitize_tool_name


class LangChainStreamingAgent(LangChainStreamMixin, DirectClientStreamMixin):
    """
    Streaming agent that handles tool calls automatically.

    Manages the complete tool calling loop:
    1. LLM generates response (may include tool calls)
    2. Tools are executed automatically
    3. Results are fed back to LLM
    4. Loop continues until LLM stops calling tools

    The two streaming entry points live in `llm.agent.streaming` as mixins
    (`astream_chat` and `_astream_with_direct_client`); this class owns
    construction and delegates the rest to the collaborators built here.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: Optional[str] = None,
        provider_slug: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        enable_file_tools: bool = False,
        enable_brave_search: bool = False,
        enable_google_maps: bool = False,
        enable_image_generation: bool = False,
        enable_video_generation: bool = False,
        enable_reasoning: bool = False,
        enable_mcp_tools: bool = False,
        enable_voice_mode: bool = False,
        enable_sparks: bool = False,
        enable_knowledge_base: bool = False,
        mcp_tools: Optional[List] = None,  # Pre-loaded MCP tools
        custom_prompt: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        reasoning_max_tokens: Optional[int] = None,
        output_modalities: Optional[List[str]] = None,
        model_name: Optional[str] = None,
        # V2 parameters for tool discovery
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        # User info for system prompt
        user_first_name: Optional[str] = None,
        user_last_name: Optional[str] = None,
        user_email: Optional[str] = None,
        # Spark auto-fix
        spark_fix_request: Optional[Dict[str, str]] = None,
        # Spark ignite
        spark_ignite_request: Optional[Dict[str, str]] = None,
        # Forced tool choice (from @mention)
        forced_tool_name: Optional[str] = None,
        # Media tool parameters (from @generate_image [params] or @generate_video [params])
        media_tool_params: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        """
        Initialize the agent.

        Args:
            model: OpenRouter model ID
            api_key: API key (OpenRouter, or a provider key when
                base_url/provider_slug route directly to a provider)
            base_url: OpenAI-compatible endpoint base URL. Defaults to
                OpenRouter. Set to a provider base URL (with matching
                provider_slug) for provider-scoped BYOK direct routing.
            provider_slug: BYOK provider slug when routing directly
                (e.g. 'anthropic'); None when going through OpenRouter.
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            enable_file_tools: Whether to enable file manipulation tools
            enable_brave_search: Whether to enable Brave Search tools (web, images, videos, news, places)
            enable_reasoning: Whether extended reasoning is enabled
            enable_mcp_tools: Whether to enable MCP (Model Context Protocol) tools
            mcp_tools: Pre-loaded list of MCPTool objects (optional, loaded from registry if not provided)
            custom_prompt: Optional custom system prompt
            reasoning_effort: Reasoning effort level for effort-based models ("high", "medium", "low")
            reasoning_max_tokens: Max tokens for reasoning (token-limited models, 1024-32000)
            output_modalities: List of output modalities the model supports (e.g., ["text", "image"])
            model_name: Optional display name for the model
            user_id: User ID for V2 tool discovery (optional)
            conversation_id: Conversation ID for V2 tool discovery (optional)
            chat_id: Chat ID for V2 tool discovery (optional)
            spark_fix_request: Spark auto-fix request data (spark_id, spark_title, error)
            **kwargs: Additional parameters to pass to the LLM
        """
        self.model = model
        self.model_name = model_name

        # Provider-scoped BYOK routing (V1: chat completions only).
        # base_url defaults to OpenRouter; when the resolver picked a
        # direct provider endpoint, provider_slug is set and the native
        # model name (prefix + ':variant' suffix stripped) is sent upstream.
        from llm.provider_registry import (
            OPENROUTER_BASE_URL,
            is_openrouter_url,
            native_model_name,
        )
        self.base_url = base_url or OPENROUTER_BASE_URL
        self.provider_slug = provider_slug
        self.is_openrouter = is_openrouter_url(self.base_url)
        self.request_model = native_model_name(model) if provider_slug else model

        self.enable_file_tools = enable_file_tools
        self.enable_brave_search = enable_brave_search
        self.enable_google_maps = enable_google_maps
        self.enable_image_generation = enable_image_generation
        self.enable_video_generation = enable_video_generation
        self.enable_reasoning = enable_reasoning
        self.enable_mcp_tools = enable_mcp_tools
        self.enable_voice_mode = enable_voice_mode
        self.enable_sparks = enable_sparks
        self.enable_knowledge_base = enable_knowledge_base
        self.mcp_tools = mcp_tools  # Pre-loaded MCPTool objects

        # Immutable snapshot of the switches. The individual `enable_*`
        # attributes above stay for callers that read them.
        self._flags = AgentFeatureFlags(
            file_tools=enable_file_tools,
            brave_search=enable_brave_search,
            google_maps=enable_google_maps,
            image_generation=enable_image_generation,
            video_generation=enable_video_generation,
            reasoning=enable_reasoning,
            mcp_tools=enable_mcp_tools,
            voice_mode=enable_voice_mode,
            sparks=enable_sparks,
            knowledge_base=enable_knowledge_base,
        )

        self.output_modalities = output_modalities or ["text"]
        self.supports_image_output = "image" in self.output_modalities

        # User info for system prompt
        self.user_first_name = user_first_name
        self.user_last_name = user_last_name
        self.user_email = user_email

        # Spark auto-fix request
        self.spark_fix_request = spark_fix_request
        # Spark ignite request
        self.spark_ignite_request = spark_ignite_request

        # Forced tool choice - when user explicitly @mentions a tool like @plan_implementation
        self.forced_tool_name = forced_tool_name

        # Media tool parameter overrides (e.g., model, ratio, res, dur, quality)
        self.media_tool_params = media_tool_params

        # Reasoning/answer splitter for models that emit <think> tags.
        self._thinking_parser = ThinkingContentParser(enable_reasoning=enable_reasoning)

        # Cancellation flag for stopping execution (e.g., when user clicks stop button)
        self.is_cancelled = False

        # Cost accounting collaborator. `_user_id` is read lazily (it is
        # assigned further down this constructor and reassignable after).
        self._cost_ledger = CostLedger(
            resolve_user_id=lambda: self._user_id,
            model_id=model,
        )

        # Streams coding-agent steps while a long tool call is in flight.
        self._coding_agent_progress = CodingAgentProgressReporter(
            resolve_file_tools_context=lambda: self.file_tools_context,
        )

        # Summarize-and-replay recovery for a 413 "context too large".
        self._context_compaction = ContextCompactionRetry(
            model_id=model,
            resolve_summarizer_endpoint=self._resolve_summarizer_endpoint,
        )

        # Abort-settlement bookkeeping (read by the view's disconnect
        # handler): all OpenRouter generation ids seen this stream, and
        # whether the final aggregate UsageLog row was already recorded.
        self.all_generation_ids: List[str] = []
        self.final_usage_recorded = False

        # Store file tools context for request cancellation
        self.file_tools_context: Optional[FileToolsContext] = None

        # Counter for Extended Search tool calls in current message (per-instance isolation)
        # Each agent instance is isolated to a specific message in a specific chat
        # Note: This tracks Brave Search tools, NOT OpenRouter native Web Search (:online)
        self._extended_search_count = 0

        # OpenRouter-specific request extras (reasoning object, output
        # modalities, caller kwargs) — see chat_model_factory.
        extra_body = build_extra_body(
            model=model,
            is_openrouter=self.is_openrouter,
            provider_slug=self.provider_slug,
            enable_reasoning=enable_reasoning,
            max_tokens=max_tokens,
            reasoning_effort=reasoning_effort,
            reasoning_max_tokens=reasoning_max_tokens,
            supports_image_output=self.supports_image_output,
            output_modalities=self.output_modalities,
            extra_kwargs=kwargs,
        )

        self.llm = create_chat_model(
            request_model=self.request_model,
            api_key=api_key,
            base_url=self.base_url,
            is_openrouter=self.is_openrouter,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body,
        )

        # Store API details for direct HTTP streaming when needed (for reasoning support)
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reasoning_config = extra_body.get("reasoning") if extra_body else None

        # Endpoints/keys for the agent's non-chat calls (coding agent,
        # compaction summarizer) — a BYOK chat key does not fit either.
        self._key_resolver = EndpointKeyResolver(
            resolve_user_id=lambda: self._user_id,
            api_key=api_key,
            base_url=self.base_url,
            is_openrouter=self.is_openrouter,
            provider_slug=self.provider_slug,
        )

        # Create OpenRouterClient for direct streaming (bypasses LangChain limitations with reasoning)
        # Always create it in case reasoning is enabled later.
        # Pass the resolved endpoint through so provider-scoped BYOK chats
        # keep hitting the provider directly (with the native model name).
        self.direct_client = OpenRouterClient(
            api_key=api_key,
            base_url=self.base_url,
            model_id=model,
        )
        if enable_reasoning:
            logger.info("[LangChain] Created OpenRouterClient for direct reasoning support")

        logger.info(f"[LangChain] Created ChatOpenAI with extra_body: {extra_body if extra_body else 'None'}")

        # Store user_id for usage tracking (independent of tool discovery)
        # This ensures usage is logged even when only basic features like web search are enabled
        self._user_id = user_id

        # V2 Tool Discovery initialization
        self.discovery_context = None
        self.discovery_service = None

        # V2 PTC initialization
        self.ptc_enabled = False
        self.ptc_available_tools = []
        self.ptc_context = None

        if ENABLE_TOOL_DISCOVERY and user_id and conversation_id and self._flags.has_tool_features:
            try:
                # Lazy import to avoid circular imports
                from .tool_discovery import get_discovery_service

                self.discovery_service = get_discovery_service()
                self.discovery_context = self.discovery_service.get_or_create_context(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    chat_id=chat_id,
                    enabled_features=self._flags.discovery_feature_names(),
                )
                logger.info(f"[LangChain] V2 Tool Discovery enabled for user {user_id}")

                # Pre-load preconfigured server tools from DB (sync context)
                # This ensures GitHub, Notion, etc. tools are available for discovery
                try:
                    from .tool_catalog.registry import get_tool_catalog
                    catalog = get_tool_catalog()
                    catalog._ensure_user_tools_loaded(user_id)
                except Exception as e:
                    logger.warning(f"[LangChain] Failed to preload preconfigured tools: {e}")
            except Exception as e:
                logger.warning(f"[LangChain] V2 Tool Discovery init failed: {e}, falling back to V1")

        self.system_prompt = build_agent_system_prompt(
            custom_prompt=custom_prompt,
            flags=self._flags,
            discovery_context=self.discovery_context,
            model_name=self.model_name,
            user_first_name=self.user_first_name,
            user_last_name=self.user_last_name,
            user_email=self.user_email,
            spark_fix_request=self.spark_fix_request,
            spark_ignite_request=self.spark_ignite_request,
            forced_tool_name=self.forced_tool_name,
            media_tool_params=self.media_tool_params,
        )

        # Tool set for this turn (V2 on-demand discovery, or V1 all-upfront).
        self._tool_registry = AgentToolRegistry(
            flags=self._flags,
            discovery_service=self.discovery_service,
            discovery_context=self.discovery_context,
        )
        self._tool_registry.load_initial_tools()
        self.ptc_enabled = self._tool_registry.ptc_enabled

        if enable_mcp_tools and self.mcp_tools:
            self._tool_registry.register_mcp_tools(self.mcp_tools, user_id)

        # Bind tools to LLM if any
        if self.tools:
            self.llm_with_tools = self.llm.bind_tools(self.tools)
        else:
            self.llm_with_tools = self.llm

    # --- Tool set (owned by the AgentToolRegistry collaborator) ---
    #
    # Exposed as properties rather than plain attributes so both mutation
    # (`self.tools.append(...)`) and rebinding (`self.tools = self.tools +
    # [ptc_tool]`) keep the registry and the agent looking at the same
    # objects.

    @property
    def tools(self) -> List[Any]:
        return self._tool_registry.tools

    @tools.setter
    def tools(self, value: List[Any]) -> None:
        self._tool_registry.tools = value

    @property
    def _tool_display_names(self) -> Dict[str, str]:
        return self._tool_registry.display_names

    @property
    def _tool_server_icons(self) -> Dict[str, Dict[str, Any]]:
        return self._tool_registry.server_icons

    @property
    def _mcp_tools_cache(self) -> Dict[str, Any]:
        return self._tool_registry.mcp_tools_cache

    # --- Cost accounting (delegated to the CostLedger collaborator) ---

    @property
    def final_usage_recorded(self) -> bool:
        """Whether the aggregate usage row was written for this stream.

        Read by the view's disconnect handler to decide whether an abort
        settlement task is still needed.
        """
        return self._cost_ledger.final_usage_recorded

    @final_usage_recorded.setter
    def final_usage_recorded(self, value: bool) -> None:
        self._cost_ledger.final_usage_recorded = value

    async def _resolve_billing_origin(self) -> str:
        return await self._cost_ledger.resolve_billing_origin()

    # Model used for 413 context-compaction summarization.
    SUMMARIZER_MODEL = "openai/gpt-4o-mini"

    async def _openrouter_key_for_tools(self) -> str:
        return await self._key_resolver.openrouter_key_for_tools()

    async def _resolve_summarizer_endpoint(self) -> tuple:
        return await self._key_resolver.summarizer_endpoint(self.SUMMARIZER_MODEL)

    async def _calculate_costs(self, prompt_tokens, completion_tokens, tool_cost=0.0):
        return await self._cost_ledger.calculate_costs(
            prompt_tokens, completion_tokens, tool_cost
        )

    async def _record_chat_aggregate_usage(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        total_tool_cost: float,
        image_gen_cost_in_bundle: float = 0.0,
    ) -> float:
        return await self._cost_ledger.record_chat_aggregate_usage(
            prompt_tokens,
            completion_tokens,
            total_tool_cost,
            image_gen_cost_in_bundle,
        )

    def cancel(self):
        """
        Cancel ongoing execution.
        This is called when the client disconnects (e.g., user clicks stop button).
        Cancels both LLM streaming and in-flight file tool HTTP requests.
        """
        logger.warning("[LangChain] Agent cancellation requested")
        self.is_cancelled = True

        # Cancel any in-flight file tool requests immediately
        if self.file_tools_context:
            try:
                # Run cancel_all_requests in the current event loop if possible
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule cancellation as a task in the running loop
                    asyncio.create_task(self.file_tools_context.cancel_all_requests())
                else:
                    # If no loop is running, run it synchronously
                    loop.run_until_complete(self.file_tools_context.cancel_all_requests())
            except Exception:
                logger.error("langchain.cancel_file_tools_failed", exc_info=True)

    # --- Coding-agent progress (delegated to CodingAgentProgressReporter) ---

    async def _poll_coding_agent_progress(self, last_step_count: int) -> tuple:
        """Poll the orchestrator for new coding-agent steps."""
        return await self._coding_agent_progress.poll(last_step_count)

    def _build_coding_agent_completed_event(self, result: dict, progress: dict, duration_ms: int) -> dict:
        """Build a coding_agent_completed SSE event from tool result and progress data."""
        return CodingAgentProgressReporter.build_completed_event(result, progress, duration_ms)

    def _enrich_coding_agent_result(self, result: dict, progress: dict, duration_ms: int) -> dict:
        """Enrich a coding agent tool result with coding_agent_data for frontend display."""
        return CodingAgentProgressReporter.enrich_result(result, progress, duration_ms)

    async def _get_final_coding_agent_data(self, last_step_count: int, last_progress: dict) -> tuple:
        """Final coding-agent data after tool completion (progress or stored result)."""
        return await self._coding_agent_progress.final_data(last_step_count, last_progress)

    def _add_display_names(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Attach display names / MCP server icons for the UI."""
        return add_display_names(
            tool_calls, self._tool_display_names, self._tool_server_icons
        )

    def _emit_post_tool_events(self, tool_results: list) -> list:
        """Extra SSE events implied by tool results (e.g. preview_started)."""
        return post_tool_events(tool_results)

    def add_discovered_tools(self, tool_ids: List[str]):
        """
        Add newly discovered tools to the agent.
        Called after search_available_tools returns results.
        """
        if self._tool_registry.add_discovered(tool_ids):
            self.llm_with_tools = self.llm.bind_tools(self.tools)

    def _preload_tools_from_history(self, messages: List[Dict[str, Any]]):
        """
        Pre-load MCP tools that were discovered in previous turns of this conversation.

        Args:
            messages: Conversation history (kept for interface compatibility)
        """
        if self._tool_registry.preload_from_context():
            self.llm_with_tools = self.llm.bind_tools(self.tools)

    def _create_mcp_catalog_tool(self, tool_id: str, entry):
        """LangChain tool wrapper for a catalog-based MCP tool."""
        return self._tool_registry.create_mcp_catalog_tool(tool_id, entry)

    def _format_tool_result_for_llm(self, tool_name: str, result: any) -> str:
        """Condense a tool result for the model (the UI gets the full payload)."""
        return format_tool_result_for_llm(tool_name, result)

    # --- Reasoning extraction (delegated to ThinkingContentParser) ---

    @property
    def accumulated_buffer(self) -> str:
        return self._thinking_parser.accumulated_buffer

    @accumulated_buffer.setter
    def accumulated_buffer(self, value: str) -> None:
        self._thinking_parser.accumulated_buffer = value

    @property
    def in_think_block(self) -> bool:
        return self._thinking_parser.in_think_block

    @in_think_block.setter
    def in_think_block(self, value: bool) -> None:
        self._thinking_parser.in_think_block = value

    def _process_content_with_thinking(self, content: str):
        """Split a content chunk into ('content'|'reasoning'|'error', text) pairs."""
        return self._thinking_parser.process(content)

    def _flush_buffer(self):
        """Flush remaining buffer content at end of stream."""
        return self._thinking_parser.flush()

    async def _extract_web_sources(self, content: str):
        """Extract web sources from markdown links in content."""
        return await extract_web_sources(content)

    def _extract_brave_search_sources(self, tool_results: List[Dict]) -> List[Dict[str, str]]:
        """Extract web sources from Brave Search tool results."""
        return extract_brave_search_sources(tool_results)

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List:
        """Convert API messages to LangChain message objects."""
        return convert_messages(messages)
