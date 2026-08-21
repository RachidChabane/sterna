"""The default (LangChain) streaming path.

Mixin over `LangChainStreamingAgent`. Streams `ChatOpenAI` chunks,
accumulates the tool calls they carry, runs those tools, feeds the
results back as `ToolMessage`s, and repeats until the model answers
without calling anything. On a 413 it hands off to
`ContextCompactionRetry` and replays the turn once.

Why a mixin rather than a collaborator: the generator's `return`
statements must terminate the *whole* stream. Moving any yielding block
behind an `async for` would turn each of them into "stop the helper and
fall through", leaking events after a cancellation. Only NON-yielding
work has been lifted out, into the sibling modules here.
"""

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

import openai
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from ...constants import (
    CODING_AGENT_TIMEOUT_SECONDS,
    TOOL_EXECUTION_TIMEOUT_SECONDS,
    TOOL_HEARTBEAT_INTERVAL_SECONDS,
)
from ...langchain_file_tools import CODING_AGENT_TOOL_NAMES
from ..cost_ledger import extract_billable_tool_costs
from ..sse_events import (
    EVENT_CONTENT,
    EVENT_ERROR,
    EVENT_DONE,
    EVENT_FILE_TOOL_EXECUTED,
    EVENT_FILE_TOOL_EXECUTING,
    EVENT_GENERATION_ID,
    EVENT_HEARTBEAT,
    EVENT_IMAGE,
    EVENT_REASONING,
    EVENT_WEB_SOURCES,
    FINISH_REASON_INVALID_TOOLS,
    FINISH_REASON_STOP,
    api_error_event,
    cancelled_event,
    cancelled_placeholder_executed_event,
    cancelled_tool_result,
    loading_tool_call_event,
    no_tool_support_error_event,
    reasoning_error_event,
    terminal_event,
    usage_update_event,
)
from ..thinking_parser import EVENT_ERROR as THINKING_EVENT_ERROR
from . import chunk_reader, request_context
from .quota_precheck import precheck_chat_quota
from .upstream_errors import is_request_too_large, is_request_too_large_message
from .tool_resolution import ToolResolver

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

# Window given to the user to hit stop once tool calls are announced.
TOOL_CANCEL_WINDOW_SECONDS = 1.0
# Truncation applied to tool-result diagnostics.
TOOL_RESULT_LOG_CHARS = 200


def _parse_tool_arguments(raw_args):
    """Coerce the `arguments` field of a tool call into a dict."""
    if isinstance(raw_args, str):
        return json.loads(raw_args) if raw_args.strip() else {}
    return raw_args


class LangChainStreamMixin:
    """Implements `astream_chat` for the agent."""

    async def astream_chat(
        self,
        messages: List[Dict[str, Any]],
        user_id: str,
        conversation_id: str,
        chat_id: str,
        auth_token: str,
        model_metadata: Optional[Dict[str, Any]] = None,
        uploaded_files: Optional[List[Dict[str, str]]] = None,
        _compaction_retry: bool = False,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream chat responses with automatic tool calling.

        Args:
            messages: List of chat messages
            user_id: User ID for file tools
            conversation_id: Conversation ID for sandbox isolation
            chat_id: Chat ID for sandbox isolation
            auth_token: JWT token for orchestrator auth
            model_metadata: Optional metadata about the model (for file tracking)
            uploaded_files: Optional list of uploaded files [{filename, content_base64}]

        Yields:
            SSE-formatted events (content, tool_calls, done)
        """
        # Pre-load tools from conversation history so tools used in
        # previous turns are available without re-searching.
        if self.discovery_context and messages:
            self._preload_tools_from_history(messages)

        execution_id = await request_context.install(
            self,
            user_id=user_id,
            conversation_id=conversation_id,
            chat_id=chat_id,
            auth_token=auth_token,
            model_metadata=model_metadata,
            uploaded_files=uploaded_files,
        )

        # Pre-check chat quota BEFORE any upstream call (mirror of
        # `_astream_with_direct_client`'s pre-check). That path runs its
        # own, so only run this one when we will NOT route there.
        if user_id and not (self.enable_reasoning or self.supports_image_output):
            denial = await precheck_chat_quota(
                user_id=user_id,
                model_id=self.model,
                messages=messages,
            )
            if denial:
                yield denial
                return

        def replay(compacted_messages):
            """Re-run this turn once, on a summarized message list."""
            return self.astream_chat(
                messages=compacted_messages,
                user_id=user_id,
                conversation_id=conversation_id,
                chat_id=chat_id,
                auth_token=auth_token,
                model_metadata=model_metadata,
                uploaded_files=uploaded_files,
                _compaction_retry=True,
            )

        try:
                # CRITICAL: Use direct client when reasoning or image generation is enabled
                # LangChain doesn't expose OpenRouter's custom response fields (reasoning_details, images)
                if self.enable_reasoning or self.supports_image_output:
                    reason = "reasoning support" if self.enable_reasoning else "image generation support"
                    logger.info(f"[LangChain] 🔄 Routing to direct client for {reason}")
                    async for event in self._astream_with_direct_client(
                        messages=messages,
                        user_id=user_id,
                        conversation_id=conversation_id,
                        chat_id=chat_id,
                        auth_token=auth_token,
                        model_metadata=model_metadata,
                        uploaded_files=uploaded_files
                    ):
                        yield event
                    return

                lc_messages = self._convert_messages(messages)
                if self.system_prompt:
                    lc_messages.insert(0, SystemMessage(content=self.system_prompt))

                tool_resolver = ToolResolver(self._tool_registry, self.discovery_context)

                iteration = 0

                # Accumulate tokens across all iterations
                total_prompt_tokens = 0
                total_completion_tokens = 0
                total_tokens = 0
                total_tool_cost = 0.0  # e.g. image generation
                # Subset of total_tool_cost already billed per-image by
                # image_tools._record_billing (OpenRouter image gen) — must be
                # subtracted from the aggregate bill (mirrors the Direct
                # Client path's dedup).
                image_gen_cost_in_bundle = 0.0
                last_generation_id = None  # Latest OpenRouter generation ID across iterations
                all_generation_ids = []  # ALL generation IDs, for comprehensive billing
                # Expose generation ids + settlement state on the agent so the
                # view's disconnect handler can enqueue a server-side abort
                # settlement (llm.tasks.settle_aborted_generations).
                self.all_generation_ids = all_generation_ids
                self.final_usage_recorded = False

                while True:
                    # Check cancellation at start of each iteration
                    if self.is_cancelled:
                        logger.warning(f"[LangChain] Agent cancelled at iteration {iteration}")

                        if self.file_tools_context:
                            await self.file_tools_context.cancel_all_requests()

                        yield cancelled_event(self.model)
                        return

                    iteration += 1
                    logger.info(f"[LangChain] Starting iteration {iteration}")

                    # Reset buffer for each iteration
                    self.accumulated_buffer = ""
                    self.in_think_block = False

                    # Stream LLM response
                    accumulated_content = ""
                    accumulated_reasoning = ""
                    accumulated_images = []
                    tool_calls_dict = {}  # keyed by index to avoid duplicates
                    usage_metadata = None  # Collected from chunks (last one, usually)
                    file_tool_event_sent = False
                    chunk_count = 0
                    last_yield_chunk = 0  # When we last yielded something
                    iteration_generation_id = None

                    # Force tool_choice on first iteration if user explicitly @mentioned a tool
                    active_llm = self.llm_with_tools
                    if self.forced_tool_name and iteration == 1 and self.tools:
                        logger.info(f"[LangChain] Forcing tool_choice={self.forced_tool_name} on iteration 1")
                        active_llm = self.llm.bind_tools(
                            self.tools,
                            tool_choice={"type": "function", "function": {"name": self.forced_tool_name}}
                        )

                    stream_source = active_llm.astream(lc_messages)

                    # Unreachable in practice (an `enable_reasoning` turn is
                    # routed to the direct client above); kept verbatim from
                    # the pre-split implementation.
                    if self.enable_reasoning and hasattr(self.llm_with_tools, 'client'):
                        try:
                            # Access the internal async client from ChatOpenAI
                            openai_client = self.llm_with_tools.client
                            if hasattr(openai_client, 'chat') and hasattr(openai_client.chat, 'completions'):
                                logger.info("[LangChain] 🔍 Found underlying OpenAI client, will try to access raw stream")
                        except Exception as e:
                            logger.warning(f"[LangChain] Could not access underlying OpenAI client: {e}")

                    async for chunk in stream_source:
                        chunk_count += 1

                        # Capture OpenRouter generation ID from response_metadata
                        # (preserved by our monkey-patch of _convert_chunk_to_generation_chunk)
                        if not iteration_generation_id:
                            gen_id = chunk_reader.read_generation_id(chunk)
                            if gen_id:
                                iteration_generation_id = gen_id
                                last_generation_id = gen_id
                                if gen_id not in all_generation_ids:
                                    all_generation_ids.append(gen_id)
                                # Emit generation_id event so frontend has it immediately
                                yield {
                                    "event": EVENT_GENERATION_ID,
                                    "data": {"generation_id": gen_id}
                                }

                        # Check for cancellation during streaming (every chunk)
                        if self.is_cancelled:
                            logger.warning("[LangChain] Agent cancelled during LLM streaming")

                            if self.file_tools_context:
                                await self.file_tools_context.cancel_all_requests()

                            if file_tool_event_sent:
                                yield cancelled_placeholder_executed_event()
                            yield cancelled_event(self.model)
                            return

                        # Native OpenRouter reasoning takes priority over
                        # <think> tags. `reasoning_chunk` is deliberately
                        # sticky across details, as it was inline.
                        reasoning_chunk = None

                        if self.enable_reasoning and chunk_count == 1:
                            chunk_reader.log_first_chunk_structure(chunk)

                        reasoning_details = chunk_reader.read_reasoning_details(chunk, chunk_count)

                        if reasoning_details and isinstance(reasoning_details, list):
                            for detail in reasoning_details:
                                detail_text = chunk_reader.read_reasoning_detail_text(detail)
                                if detail_text is not None:
                                    reasoning_chunk = detail_text

                                if reasoning_chunk:
                                    # A tool call inside reasoning is invalid.
                                    if chunk_reader.is_tool_call_in_reasoning(reasoning_chunk):
                                        yield reasoning_error_event()
                                        return

                                    accumulated_reasoning += reasoning_chunk
                                    yield {
                                        "event": EVENT_REASONING,
                                        "data": {"content": reasoning_chunk}
                                    }
                                    last_yield_chunk = chunk_count

                        # Handle image generation for models that support it
                        if self.supports_image_output:
                            if chunk_count == 1:
                                chunk_reader.log_first_image_chunk_structure(chunk)

                            images = chunk_reader.read_images(chunk)
                            if images:
                                logger.info(f"[ImageGen] Found {len(images)} images in chunk")
                                for img in images:
                                    if img and img not in accumulated_images:
                                        accumulated_images.append(img)
                                        yield {"event": EVENT_IMAGE, "data": {"image": img}}
                                        last_yield_chunk = chunk_count

                        # Handle content streaming with reasoning extraction
                        if chunk.content:
                            # With native reasoning the content is already
                            # separated; otherwise fall back to <think> tags.
                            if self.enable_reasoning and not reasoning_chunk:
                                for event_type, event_content in self._process_content_with_thinking(chunk.content):
                                    if event_type == THINKING_EVENT_ERROR:
                                        # Critical error detected - stop.
                                        yield reasoning_error_event()
                                        return
                                    elif event_type == EVENT_REASONING:
                                        accumulated_reasoning += event_content
                                        yield {
                                            "event": EVENT_REASONING,
                                            "data": {"content": event_content}
                                        }
                                        last_yield_chunk = chunk_count
                                    else:  # content
                                        accumulated_content += event_content
                                        yield {
                                            "event": EVENT_CONTENT,
                                            "data": {"content": event_content}
                                        }
                                        last_yield_chunk = chunk_count
                            else:
                                accumulated_content += chunk.content
                                yield {
                                    "event": EVENT_CONTENT,
                                    "data": {"content": chunk.content}
                                }
                                last_yield_chunk = chunk_count

                        # Collect usage metadata if present (usually in last chunk)
                        if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                            usage_metadata = chunk.usage_metadata
                            logger.info(f"[LangChain] Usage metadata received: {usage_metadata}")

                            if self.enable_reasoning or self.supports_image_output:
                                chunk_reader.log_final_chunk_structure(chunk)

                        # Collect tool calls - OpenRouter streams them as
                        # tool_call_chunks that must be accumulated by index.
                        if hasattr(chunk, 'tool_call_chunks') and chunk.tool_call_chunks:
                            # Show the spinner on the FIRST tool call chunk
                            if not file_tool_event_sent and self.enable_file_tools:
                                logger.info("[LangChain] 🔧 First tool call chunk detected - sending file_tool_executing event immediately")
                                yield loading_tool_call_event()
                                file_tool_event_sent = True
                                last_yield_chunk = chunk_count

                            chunk_reader.accumulate_tool_call_chunks(chunk, tool_calls_dict)

                        # Fallback for providers that send complete calls
                        elif hasattr(chunk, 'tool_calls') and chunk.tool_calls:
                            chunk_reader.accumulate_complete_tool_calls(chunk, tool_calls_dict)

                        # Heartbeat so client disconnects are detected quickly
                        if chunk_count - last_yield_chunk >= chunk_reader.HEARTBEAT_CHUNK_INTERVAL:
                            logger.debug(f"[LangChain] Sending heartbeat after {chunk_count - last_yield_chunk} chunks without yielding")
                            yield {"event": EVENT_HEARTBEAT, "data": {}}
                            last_yield_chunk = chunk_count

                    # Flush remaining buffer content
                    for event_type, event_content in self._flush_buffer():
                        if event_type == EVENT_REASONING:
                            accumulated_reasoning += event_content
                            yield {
                                "event": EVENT_REASONING,
                                "data": {"content": event_content}
                            }
                        else:  # content
                            accumulated_content += event_content
                            yield {
                                "event": EVENT_CONTENT,
                                "data": {"content": event_content}
                            }

                    tool_calls_data = chunk_reader.build_tool_calls_data(tool_calls_dict)

                    # Accumulate tokens from this iteration (regardless of tool calls)
                    if usage_metadata:
                        iteration_prompt_tokens = usage_metadata.get("input_tokens", 0)
                        iteration_completion_tokens = usage_metadata.get("output_tokens", 0)
                        iteration_total_tokens = usage_metadata.get("total_tokens", 0)

                        total_prompt_tokens += iteration_prompt_tokens
                        total_completion_tokens += iteration_completion_tokens
                        total_tokens += iteration_total_tokens

                        logger.info(f"[LangChain] Iteration {iteration} tokens - Input: {iteration_prompt_tokens}, Output: {iteration_completion_tokens}, Total: {iteration_total_tokens}")
                        logger.info(f"[LangChain] Accumulated tokens - Input: {total_prompt_tokens}, Output: {total_completion_tokens}, Total: {total_tokens}")

                        # Emit usage_update so frontend has partial data if user stops
                        p_cost, c_cost, t_cost = await self._calculate_costs(
                            total_prompt_tokens, total_completion_tokens, total_tool_cost
                        )
                        yield usage_update_event(
                            prompt_tokens=total_prompt_tokens,
                            completion_tokens=total_completion_tokens,
                            total_tokens=total_tokens,
                            cost=t_cost,
                            prompt_cost=p_cost,
                            completion_cost=c_cost,
                            generation_id=last_generation_id,
                            generation_ids=all_generation_ids,
                        )
                    else:
                        logger.warning(f"[LangChain] No usage metadata received in iteration {iteration}")

                    # Determine finish reason
                    if tool_calls_data:
                        # (the pre-split code assigned FINISH_REASON_TOOL_CALLS
                        # to `finish_reason` here; the branch always `continue`s
                        # and the next iteration resets it, so nothing read it)
                        logger.info(f"[LangChain] Tool calls detected: {len(tool_calls_data)}")

                        # Filter out invalid tool calls
                        valid_tool_calls = [{
                            "name": tc["function"]["name"],
                            "args": json.loads(tc["function"]["arguments"]),
                            "id": tc["id"]
                        } for tc in tool_calls_data if tc["function"]["name"] and tc["function"]["name"].strip()]

                        # If all tool calls are invalid, stop the loop
                        if not valid_tool_calls:
                            logger.warning("[LangChain] All tool calls invalid, stopping iteration")
                            yield terminal_event(self.model, FINISH_REASON_INVALID_TOOLS)
                            return

                        # Add assistant message with tool calls to conversation history
                        lc_messages.append(AIMessage(
                            content=accumulated_content,
                            tool_calls=valid_tool_calls
                        ))

                        # Always send this, even if a placeholder was sent
                        # during streaming: the frontend updates it in place.
                        enriched_tool_calls = self._add_display_names(tool_calls_data)
                        if file_tool_event_sent:
                            logger.info(f"[LangChain] Sending file_tool_executing UPDATE with {len(tool_calls_data)} tools (replacing placeholder)")
                        else:
                            logger.info(f"[LangChain] Sending file_tool_executing event with {len(tool_calls_data)} tools (non-streaming)")
                        yield {
                            "event": EVENT_FILE_TOOL_EXECUTING,
                            "data": {"tool_calls": enriched_tool_calls}
                        }

                        # Give the user a window to click stop
                        await asyncio.sleep(TOOL_CANCEL_WINDOW_SECONDS)

                        if self.is_cancelled:
                            logger.warning("[LangChain] Agent cancelled before tool execution started")

                            if self.file_tools_context:
                                await self.file_tools_context.cancel_all_requests()

                            yield cancelled_event(self.model)
                            return

                        # Execute tools and add results
                        tool_results = []
                        for tc in tool_calls_data:
                            # Check cancellation before each tool execution
                            if self.is_cancelled:
                                logger.warning("[LangChain] Agent cancelled before tool execution - sending partial results")

                                if self.file_tools_context:
                                    await self.file_tools_context.cancel_all_requests()

                                # Update the UI from "Executing..." to cancelled
                                if tool_results or tool_calls_data:
                                    for remaining_tc in tool_calls_data[len(tool_results):]:
                                        tool_results.append(cancelled_tool_result(remaining_tc))

                                    yield {
                                        "event": EVENT_FILE_TOOL_EXECUTED,
                                        "data": {
                                            "tool_calls": self._add_display_names(tool_calls_data),
                                            "results": tool_results
                                        }
                                    }

                                yield cancelled_event(self.model)
                                return

                            tool_name = tc["function"]["name"]
                            tool_args = _parse_tool_arguments(tc["function"]["arguments"])
                            tool_id = tc["id"]

                            # Skip tools with empty names
                            if not tool_name or not tool_name.strip():
                                logger.warning(f"[LangChain] Skipping tool with empty name: {tc}")
                                continue

                            logger.info(f"[LangChain] Executing tool: {tool_name} with args: {tool_args}")

                            resolved = await tool_resolver.resolve(tool_name, tool_args)
                            if resolved.tools_changed:
                                self.llm_with_tools = self.llm.bind_tools(self.tools)
                            tool_name = resolved.name
                            tool_func = resolved.tool
                            mcp_direct_result = resolved.direct_result

                            # Handle direct MCP result (from adapter)
                            if mcp_direct_result is not None:
                                result = json.dumps(mcp_direct_result) if isinstance(mcp_direct_result, dict) else str(mcp_direct_result)
                                parsed_result = mcp_direct_result if isinstance(mcp_direct_result, dict) else {"result": mcp_direct_result}
                                tool_success = parsed_result.get("success", True) if isinstance(parsed_result, dict) else True

                                if not tool_success:
                                    logger.warning(f"[LangChain] MCP tool {tool_name} reported failure: {parsed_result.get('error', 'Unknown error')}")

                                tool_results.append({
                                    "tool_call": tc,
                                    "result": parsed_result,
                                    "success": tool_success
                                })

                                lc_messages.append(ToolMessage(
                                    content=result,
                                    tool_call_id=tool_id
                                ))
                            elif tool_func:
                                try:
                                    tool_timeout = CODING_AGENT_TIMEOUT_SECONDS if tool_name in CODING_AGENT_TOOL_NAMES else TOOL_EXECUTION_TIMEOUT_SECONDS

                                    # Heartbeats keep the SSE connection alive
                                    # through long tools (coding agent, video).
                                    is_coding_tool = tool_name in CODING_AGENT_TOOL_NAMES
                                    tool_task = asyncio.create_task(tool_func.ainvoke(tool_args))
                                    tool_start_time = time.time()
                                    tool_heartbeat_count = 0
                                    last_step_count = 0
                                    last_progress = None

                                    while not tool_task.done():
                                        tool_elapsed = time.time() - tool_start_time
                                        if tool_elapsed >= tool_timeout:
                                            tool_task.cancel()
                                            try:
                                                await tool_task
                                            except asyncio.CancelledError:
                                                pass
                                            raise asyncio.TimeoutError(f"Tool execution timed out after {tool_timeout}s")

                                        tool_heartbeat_count += 1
                                        logger.info(f"[LangChain] Tool {tool_name} still running ({tool_elapsed:.0f}s), heartbeat #{tool_heartbeat_count}")

                                        if is_coding_tool:
                                            step_events, last_step_count, last_progress = await self._poll_coding_agent_progress(last_step_count)
                                            for evt in step_events:
                                                yield evt

                                        yield {
                                            "event": EVENT_HEARTBEAT,
                                            "data": {"tool": tool_name, "elapsed_seconds": int(tool_elapsed)}
                                        }

                                        done, _ = await asyncio.wait(
                                            {tool_task},
                                            timeout=TOOL_HEARTBEAT_INTERVAL_SECONDS
                                        )
                                        if done:
                                            break

                                    result = await tool_task
                                    tool_duration_ms = int((time.time() - tool_start_time) * 1000)
                                    logger.info(f"[LangChain] Tool {tool_name} completed after {tool_duration_ms / 1000:.1f}s ({tool_heartbeat_count} heartbeats)")
                                    logger.info(f"[LangChain] Tool {tool_name} returned: {result[:TOOL_RESULT_LOG_CHARS] if isinstance(result, str) else str(result)[:TOOL_RESULT_LOG_CHARS]}")

                                    # Some tools return JSON, others plain text
                                    if isinstance(result, str):
                                        try:
                                            parsed_result = json.loads(result)
                                        except json.JSONDecodeError:
                                            # e.g. knowledge_base, brave_search
                                            parsed_result = {"content": result, "success": True}
                                    else:
                                        parsed_result = result

                                    # Coding agent tools: final data from the
                                    # progress endpoint or the stored fallback.
                                    if is_coding_tool and isinstance(parsed_result, dict):
                                        final_events, progress_data = await self._get_final_coding_agent_data(last_step_count, last_progress)
                                        for evt in final_events:
                                            yield evt
                                        yield self._build_coding_agent_completed_event(parsed_result, progress_data, tool_duration_ms)
                                        self._enrich_coding_agent_result(parsed_result, progress_data, tool_duration_ms)

                                    tool_success = parsed_result.get("success", True) if isinstance(parsed_result, dict) else True

                                    if not tool_success:
                                        logger.warning(f"[LangChain] Tool {tool_name} reported failure: {parsed_result.get('error', 'Unknown error')}")

                                    tool_results.append({
                                        "tool_call": tc,
                                        "result": parsed_result,
                                        "success": tool_success
                                    })

                                    lc_messages.append(ToolMessage(
                                        content=result,
                                        tool_call_id=tool_id
                                    ))

                                    # search_available_tools grows the tool set
                                    if tool_name == "search_available_tools" and isinstance(parsed_result, dict):
                                        tools_list = parsed_result.get("tools", [])
                                        if tools_list:
                                            discovered_ids = [t.get("function_name") for t in tools_list if t.get("function_name")]
                                            self.add_discovered_tools(discovered_ids)
                                            self._tool_registry.remember_search_result_metadata(tools_list)

                                    # Allow stopping between tools if the user
                                    # cancelled during execution.
                                    if self.is_cancelled:
                                        logger.warning(f"[LangChain] Agent cancelled after executing {tool_name} - sending partial results")

                                        if self.file_tools_context:
                                            await self.file_tools_context.cancel_all_requests()

                                        for remaining_tc in tool_calls_data[len(tool_results):]:
                                            tool_results.append(cancelled_tool_result(remaining_tc))

                                        yield {
                                            "event": EVENT_FILE_TOOL_EXECUTED,
                                            "data": {
                                                "tool_calls": self._add_display_names(tool_calls_data),
                                                "results": tool_results
                                            }
                                        }

                                        yield cancelled_event(self.model)
                                        return
                                except asyncio.TimeoutError:
                                    actual_timeout = CODING_AGENT_TIMEOUT_SECONDS if tool_name in CODING_AGENT_TOOL_NAMES else TOOL_EXECUTION_TIMEOUT_SECONDS
                                    logger.error(
                                        "langchain.tool_execution_timeout",
                                        extra={"tool_name": tool_name, "timeout_seconds": actual_timeout},
                                    )
                                    error_result = {
                                        "success": False,
                                        "error": f"Tool execution timed out after {actual_timeout // 60} minutes.",
                                        "timeout": True
                                    }
                                    tool_results.append({
                                        "tool_call": tc,
                                        "result": error_result,
                                        "success": False
                                    })
                                    lc_messages.append(ToolMessage(
                                        content=json.dumps(error_result),
                                        tool_call_id=tool_id
                                    ))
                                except asyncio.CancelledError:
                                    logger.warning(f"[LangChain] Tool {tool_name} was cancelled")
                                    raise  # Re-raise to propagate cancellation
                                except Exception as e:
                                    logger.error(
                                        "langchain.tool_execution_failed",
                                        extra={"tool_name": tool_name},
                                        exc_info=True,
                                    )
                                    error_result = {"success": False, "error": str(e)}
                                    tool_results.append({
                                        "tool_call": tc,
                                        "result": error_result,
                                        "success": False
                                    })

                                    lc_messages.append(ToolMessage(
                                        content=json.dumps(error_result),
                                        tool_call_id=tool_id
                                    ))
                            else:
                                logger.error(
                                    "langchain.tool_not_found",
                                    extra={"tool_name": tool_name},
                                )
                                # CRITICAL: a ToolMessage is required even for
                                # unknown tools, or Anthropic returns 400
                                # (tool_use without tool_result).
                                error_result = {
                                    "success": False,
                                    "error": f"Tool '{tool_name}' not found. Use search_available_tools to discover available tools and their correct function names."
                                }
                                tool_results.append({
                                    "tool_call": tc,
                                    "result": error_result,
                                    "success": False
                                })
                                lc_messages.append(ToolMessage(
                                    content=json.dumps(error_result),
                                    tool_call_id=tool_id
                                ))

                        # Notify frontend that tools were executed
                        yield {
                            "event": EVENT_FILE_TOOL_EXECUTED,
                            "data": {
                                "tool_calls": self._add_display_names(tool_calls_data),
                                "results": tool_results
                            }
                        }

                        # Emit additional events (e.g. preview_started)
                        for evt in self._emit_post_tool_events(tool_results):
                            yield evt

                        # Accumulate tool costs via the shared classifier — see
                        # `extract_billable_tool_costs` for the dedup rules.
                        # OpenRouter image-gen cost is tracked in
                        # `image_gen_cost_in_bundle` and subtracted from the
                        # aggregate OPENROUTER/CHAT bill below: the per-image
                        # UsageLog row is already written by
                        # image_tools._record_billing, so folding it into the
                        # aggregate would bill the same dollars twice.
                        batch_tool_cost, batch_image_gen_cost = extract_billable_tool_costs(tool_results)
                        total_tool_cost += batch_tool_cost
                        image_gen_cost_in_bundle += batch_image_gen_cost
                        if batch_tool_cost:
                            logger.info(f"[LangChain] Total tool cost: ${total_tool_cost:.6f} (image-gen already billed per-image: ${image_gen_cost_in_bundle:.6f})")

                        if self.enable_brave_search:
                            brave_sources = self._extract_brave_search_sources(tool_results)
                            if brave_sources:
                                yield {"event": EVENT_WEB_SOURCES, "data": {"sources": brave_sources}}

                        # Continue loop to get LLM's response to tool results
                        continue

                    else:
                        # No tool calls - this is the final response
                        logger.info("[LangChain] Final response received, ending loop")

                        yield await self._settle_and_build_done_event(
                            prompt_tokens=total_prompt_tokens,
                            completion_tokens=total_completion_tokens,
                            total_tokens=total_tokens,
                            total_tool_cost=total_tool_cost,
                            image_gen_cost_in_bundle=image_gen_cost_in_bundle,
                            last_generation_id=last_generation_id,
                            all_generation_ids=all_generation_ids,
                            accumulated_reasoning=accumulated_reasoning,
                            accumulated_images=accumulated_images,
                        )
                        return

        except openai.NotFoundError as e:
            # Handle models that don't support tool use
            error_message = str(e)
            if "No endpoints found that support tool use" in error_message:
                logger.warning(f"[LangChain] Model {self.model} does not support tool use")
                yield no_tool_support_error_event(self.model)
            else:
                logger.error("langchain.openai_not_found", exc_info=True)
                yield api_error_event(error_message)

        except openai.APIError as e:
            error_str = str(e)

            if is_request_too_large(e):
                async for event in self._context_compaction.after_api_error(
                    messages,
                    _compaction_retry,
                    replay,
                ):
                    yield event
            else:
                # Handle other OpenAI API errors gracefully
                logger.error("langchain.openai_api_error", exc_info=True)
                yield api_error_event(error_str)

        except Exception as e:
            error_str = str(e)

            # Some wrappers do not raise openai.APIError for a 413
            if is_request_too_large_message(error_str):
                async for event in self._context_compaction.after_generic_error(
                    messages,
                    _compaction_retry,
                    replay,
                ):
                    yield event
            else:
                # Catch-all for unexpected errors
                logger.error("langchain.unexpected_stream_error", exc_info=True)
                yield {
                    "event": EVENT_ERROR,
                    "data": {
                        "error": "Stream error",
                        "detail": error_str
                    }
                }

        finally:
            request_context.clear(self, execution_id)

    async def _settle_and_build_done_event(
        self,
        *,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        total_tool_cost: float,
        image_gen_cost_in_bundle: float,
        last_generation_id,
        all_generation_ids,
        accumulated_reasoning: str,
        accumulated_images: list,
    ) -> Dict[str, Any]:
        """Bill the turn and build its terminal `done` event.

        The displayed total includes ALL tool cost so the frontend figure
        matches the events already streamed; the BILLED amount excludes
        image-gen dollars already charged per image (see
        `CostLedger.record_chat_aggregate_usage`).
        """
        prompt_cost, completion_cost, total_cost = await self._calculate_costs(
            prompt_tokens, completion_tokens, total_tool_cost
        )
        logger.info(f"[LangChain] Costs calculated - Prompt: ${prompt_cost:.6f}, Completion: ${completion_cost:.6f}, Tool: ${total_tool_cost:.6f}, Total: ${total_cost:.6f}")

        await self._record_chat_aggregate_usage(
            prompt_tokens,
            completion_tokens,
            total_tool_cost,
            image_gen_cost_in_bundle,
        )

        done_data = {
            "model": self.model,
            "finish_reason": FINISH_REASON_STOP,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            "cost": total_cost,
            "prompt_cost": prompt_cost,
            "completion_cost": completion_cost,
            "tool_cost": total_tool_cost,  # e.g. coding agent, image generation
            "generation_id": last_generation_id,
            "generation_ids": all_generation_ids,  # for comprehensive billing
        }

        if accumulated_reasoning:
            done_data["reasoning_content"] = accumulated_reasoning

        if accumulated_images:
            done_data["images"] = accumulated_images
            logger.info(f"[ImageGen] Sending {len(accumulated_images)} images in done event")

        return {"event": EVENT_DONE, "data": done_data}
