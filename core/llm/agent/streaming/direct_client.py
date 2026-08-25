"""The Direct Client streaming path.

Mixin over `LangChainStreamingAgent`, used when the turn needs OpenRouter
response fields LangChain does not surface -- `reasoning_details` and
generated images. It reimplements the agent loop against
`OpenRouterClient`: stream, parse tool calls, execute them, feed the
results back, repeat until the model stops calling tools.

Why a mixin rather than a collaborator: the generator's `return`
statements must terminate the *whole* stream. Moving any yielding block
behind an `async for` would turn each of them into "stop the helper and
fall through", leaking events after a cancellation.
"""

import asyncio
import json
import logging
import queue
import threading
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

import openai

from ...constants import (
    CODING_AGENT_TIMEOUT_SECONDS,
    MAX_EXTENDED_SEARCHES_PER_MESSAGE,
    TOOL_EXECUTION_TIMEOUT_SECONDS,
    TOOL_HEARTBEAT_INTERVAL_SECONDS,
)
from ...error_messages import error_payload
from ...agent_tool_handlers import CODING_AGENT_TOOL_NAMES
from ..cost_ledger import extract_billable_tool_costs
from ..sse_events import (
    EVENT_CONTEXT_TRIMMED,
    EVENT_DONE,
    EVENT_ERROR,
    EVENT_FILE_TOOL_EXECUTED,
    EVENT_FILE_TOOL_EXECUTING,
    EVENT_HEARTBEAT,
    EVENT_WEB_SOURCES,
    FINISH_REASON_STOP,
    FINISH_REASON_TOOL_CALLS,
    api_error_event,
    cancelled_event,
    cancelled_placeholder_executed_event,
    context_too_large_event,
    no_tool_support_error_event,
    usage_update_event,
)
from .quota_precheck import precheck_chat_quota
from .upstream_errors import is_request_too_large

# Child of the configured "llm" logger (see sterna/logging.py APP_LOGGERS).
logger = logging.getLogger(__name__)

# Extended Search = the Brave Search tools, distinct from OpenRouter's
# native ":online" web search.
EXTENDED_SEARCH_TOOL_NAMES = frozenset({'brave_web_search', 'brave_news_search'})

# How many oldest history messages we are willing to strip on a 413.
MAX_CONTEXT_TRIM_RETRIES = 2
# Poll interval on the chunk queue fed by the streaming worker thread.
CHUNK_QUEUE_POLL_SECONDS = 0.1
CHUNK_QUEUE_IDLE_SLEEP_SECONDS = 0.01
TRIMMED_MESSAGE_PREVIEW_CHARS = 80

DETAIL_CONTEXT_TOO_LARGE_AFTER_TRIM = (
    "The conversation context is too large for the API. "
    "Please try starting a new conversation or deleting some earlier messages."
)


def _tools_param(tools) -> Optional[List[Dict[str, Any]]]:
    """The bound tools in OpenAI function-calling schema, or None."""
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.args_schema.schema() if hasattr(tool.args_schema, 'schema') else {},
            },
        }
        for tool in tools
    ]


def _start_stream_thread(stream_factory):
    """Run `OpenRouterClient.complete_stream` (a SYNC generator) off-loop.

    Returns `(chunk_queue, done_event, error_container)`; the caller drains
    the queue while staying responsive to cancellation.
    """
    chunk_queue = queue.Queue()
    done_event = threading.Event()
    error_container = [None]

    def stream_in_thread():
        try:
            for chunk in stream_factory():
                chunk_queue.put(chunk)
        except Exception as e:
            error_container[0] = e
        finally:
            done_event.set()

    threading.Thread(target=stream_in_thread, daemon=True).start()
    return chunk_queue, done_event, error_container


def _parse_tool_arguments(tool_args_str):
    """Coerce the `arguments` field of a tool call into a dict."""
    if isinstance(tool_args_str, str):
        return json.loads(tool_args_str) if tool_args_str.strip() else {}
    return tool_args_str


class DirectClientStreamMixin:
    """Implements `_astream_with_direct_client` for the agent."""

    async def _astream_with_direct_client(
        self,
        messages: List[Dict[str, Any]],
        user_id: str,
        conversation_id: str,
        chat_id: str,
        auth_token: str,
        model_metadata: Optional[Dict[str, Any]] = None,
        uploaded_files: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream with OpenRouterClient directly to support reasoning_details.
        This bypasses LangChain which doesn't expose reasoning_details from OpenRouter.

        Implements the full agent loop manually:
        1. Send message to OpenRouter
        2. Parse tool calls from response (with reasoning support!)
        3. Execute tools
        4. Continue until no more tool calls
        """
        logger.info("[LangChain] 🚀 Using direct OpenRouterClient for reasoning support")

        # Pre-load tools from conversation history
        if self.discovery_context and messages:
            self._preload_tools_from_history(messages)

        # Build conversation history for OpenRouter
        openrouter_messages = []
        if self.system_prompt:
            openrouter_messages.append({"role": "system", "content": self.system_prompt})
        openrouter_messages.extend(messages)

        # Count how many history messages (non-system) we have for context trimming
        history_start_idx = 1 if self.system_prompt else 0  # Skip system prompt
        context_trim_count = 0  # How many old messages we've stripped so far

        # Pre-check quota before making expensive API calls.
        # Uses self._user_id which is always set for authenticated users.
        if self._user_id:
            denial = await precheck_chat_quota(
                user_id=self._user_id,
                model_id=self.model,
                messages=openrouter_messages,
            )
            if denial:
                yield denial
                return

        # Retry loop: on 413, strip oldest history messages and retry
        while True:
          try:
            # Reset agent loop state for each context-trim attempt
            accumulated_input_tokens = 0
            accumulated_output_tokens = 0
            accumulated_tool_cost = 0.0
            # Image-gen tools write their own per-image UsageLog row
            # (service=IMAGE_GENERATION) — we accumulate the image-gen
            # cost separately and subtract it from accumulated_tool_cost
            # before writing the aggregate row, so the same dollars are
            # not recorded twice.
            image_gen_cost_in_bundle = 0.0
            last_generation_id = None  # Track latest OpenRouter generation ID across iterations
            all_generation_ids = []  # Track ALL generation IDs for comprehensive billing
            # Expose generation ids on the agent for the view's disconnect
            # handler (server-side abort settlement). Completed iterations
            # are billed inline by client._log_usage with
            # request_id=generation_id, so the settlement task skips them.
            self.all_generation_ids = all_generation_ids
            iteration = 0

            while True:
                iteration += 1
                logger.info(f"[LangChain] Starting iteration {iteration}")

                if self.is_cancelled:
                    logger.warning("[LangChain] Agent cancelled")
                    yield cancelled_event(self.model)
                    return

                # Stream from OpenRouter
                accumulated_content = []
                accumulated_reasoning = []
                tool_calls = []
                usage_data = None
                finish_reason = None
                file_tool_event_sent = False

                tools_param = _tools_param(self.tools)

                # complete_stream is a sync generator and we are in async
                # context: run it in a worker thread and drain its queue.
                chunk_queue, done_event, error_container = _start_stream_thread(
                    lambda: self.direct_client.complete_stream(
                        model=self.model,
                        messages=openrouter_messages,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        tools=tools_param,
                        tool_choice=(
                            {"type": "function", "function": {"name": self.forced_tool_name}}
                            if self.forced_tool_name and iteration == 1 and tools_param
                            else ("auto" if tools_param else None)
                        ),
                        enable_reasoning=self.enable_reasoning,
                        enable_file_tools=self.enable_file_tools,
                        reasoning_max_tokens=self.reasoning_config.get("max_tokens") if self.reasoning_config else None,
                        reasoning_effort=self.reasoning_config.get("effort") if self.reasoning_config else None,
                        output_modalities=self.output_modalities if self.supports_image_output else None,
                    )
                )

                # Process chunks from queue
                while not done_event.is_set() or not chunk_queue.empty():
                    try:
                        # Get chunk with timeout to stay responsive
                        chunk = chunk_queue.get(timeout=CHUNK_QUEUE_POLL_SECONDS)
                    except queue.Empty:
                        # No chunk yet, yield control and check cancellation
                        await asyncio.sleep(CHUNK_QUEUE_IDLE_SLEEP_SECONDS)

                        if error_container[0]:
                            raise error_container[0]

                        continue

                    if self.is_cancelled:
                        logger.warning("[LangChain] Agent cancelled during streaming")

                        if self.file_tools_context:
                            await self.file_tools_context.cancel_all_requests()

                        if file_tool_event_sent:
                            yield cancelled_placeholder_executed_event()

                        yield cancelled_event(self.model)
                        return

                    event = chunk.get("event")
                    data = chunk.get("data", {})

                    if event == "reasoning":
                        # Forward reasoning events - THIS IS THE KEY FIX!
                        reasoning_content = data.get("content", "")
                        accumulated_reasoning.append(reasoning_content)
                        logger.info(f"[LangChain] 💭 Reasoning chunk: {reasoning_content[:100]}...")
                        yield chunk

                    elif event == "content":
                        content = data.get("content", "")
                        accumulated_content.append(content)
                        logger.info(f"[LangChain] 📝 Content chunk: {content[:100]}...")
                        yield chunk

                    elif event == "image":
                        image_data = data.get("image", "")
                        logger.info(f"[LangChain] 🖼️ Image received: {image_data[:50]}...")
                        yield chunk

                    elif event == EVENT_DONE:
                        usage_data = data.get("usage")
                        finish_reason = data.get("finish_reason")
                        tool_calls = data.get("tool_calls", [])
                        iteration_generation_id = data.get("generation_id")

                        # May already have it from the generation_id event
                        if iteration_generation_id:
                            last_generation_id = iteration_generation_id
                            if iteration_generation_id not in all_generation_ids:
                                all_generation_ids.append(iteration_generation_id)

                        logger.info(f"[LangChain] 💰 Done event - usage_data: {usage_data}, finish_reason: {finish_reason}")

                        if usage_data:
                            accumulated_input_tokens += usage_data.get("prompt_tokens", 0)
                            accumulated_output_tokens += usage_data.get("completion_tokens", 0)
                            logger.info(f"[LangChain] 💰 Accumulated tokens - input: {accumulated_input_tokens}, output: {accumulated_output_tokens}")

                            # Emit usage_update so frontend has partial data if user stops
                            p_cost, c_cost, t_cost = await self._calculate_costs(
                                accumulated_input_tokens, accumulated_output_tokens, accumulated_tool_cost
                            )
                            yield usage_update_event(
                                prompt_tokens=accumulated_input_tokens,
                                completion_tokens=accumulated_output_tokens,
                                total_tokens=accumulated_input_tokens + accumulated_output_tokens,
                                cost=t_cost,
                                prompt_cost=p_cost,
                                completion_cost=c_cost,
                                generation_id=last_generation_id,
                                generation_ids=all_generation_ids,
                            )

                    elif event == "generation_id":
                        # Forwarded from client.py on the first SSE chunk,
                        # before any content.
                        iteration_gen_id = data.get("generation_id")
                        if iteration_gen_id:
                            last_generation_id = iteration_gen_id
                            if iteration_gen_id not in all_generation_ids:
                                all_generation_ids.append(iteration_gen_id)
                        yield chunk

                    elif event == EVENT_ERROR:
                        yield chunk
                        return

                # Check if we have tool calls to execute
                if not tool_calls or finish_reason != FINISH_REASON_TOOL_CALLS:
                    logger.info(f"[LangChain] No tool calls, ending loop. Finish reason: {finish_reason}")
                    logger.info(f"[LangChain] 💰 Final accumulated tokens - input: {accumulated_input_tokens}, output: {accumulated_output_tokens}")

                    prompt_cost, completion_cost, total_cost = await self._calculate_costs(
                        accumulated_input_tokens, accumulated_output_tokens, accumulated_tool_cost
                    )
                    logger.info(f"[LangChain] 💰 Calculated costs - Prompt: ${prompt_cost:.6f}, Completion: ${completion_cost:.6f}, Tool: ${accumulated_tool_cost:.6f}, Total: ${total_cost:.6f}")

                    # Deduct the surviving tool cost — see
                    # CostLedger.record_direct_client_tool_cost for the
                    # image-gen dedup rationale.
                    await self._cost_ledger.record_direct_client_tool_cost(
                        accumulated_tool_cost,
                        image_gen_cost_in_bundle,
                        session_id=chat_id or conversation_id or "",
                    )

                    yield {
                        "event": EVENT_DONE,
                        "data": {
                            "model": self.model,
                            "finish_reason": finish_reason or FINISH_REASON_STOP,
                            "usage": {
                                "prompt_tokens": accumulated_input_tokens,
                                "completion_tokens": accumulated_output_tokens,
                                "total_tokens": accumulated_input_tokens + accumulated_output_tokens
                            },
                            "cost": total_cost,
                            "prompt_cost": prompt_cost,
                            "completion_cost": completion_cost,
                            "tool_cost": accumulated_tool_cost,  # e.g. coding agent, image generation
                            "generation_id": last_generation_id,
                            "generation_ids": all_generation_ids,  # for comprehensive billing
                        }
                    }
                    return

                # We have tool calls - execute them
                logger.info(f"[LangChain] Tool calls detected: {len(tool_calls)}")

                file_tool_event_sent = True
                yield {
                    "event": EVENT_FILE_TOOL_EXECUTING,
                    "data": {"tool_calls": self._add_display_names(tool_calls)}
                }

                tool_results = []
                for tool_call in tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool_args_str = tool_call["function"]["arguments"]

                    try:
                        tool_args = _parse_tool_arguments(tool_args_str)

                        logger.info(f"[LangChain] Executing tool: {tool_name} with args: {tool_args}")

                        # Extended Search limit (per-instance, per-message)
                        if tool_name in EXTENDED_SEARCH_TOOL_NAMES:
                            if self._extended_search_count >= MAX_EXTENDED_SEARCHES_PER_MESSAGE:
                                logger.warning(
                                    f"[LangChain] Extended Search limit reached ({MAX_EXTENDED_SEARCHES_PER_MESSAGE} searches per message). "
                                    f"Blocking additional {tool_name} call."
                                )
                                tool_results.append({
                                    "tool_call": tool_call,
                                    "result": {
                                        "success": False,
                                        "error": f"Extended Search limit reached. Maximum {MAX_EXTENDED_SEARCHES_PER_MESSAGE} searches allowed per message. Please use the results already provided.",
                                        "results": [],
                                        "result_count": 0
                                    },
                                    "success": False
                                })
                                continue

                            # Increment counter before executing
                            self._extended_search_count += 1
                            logger.info(f"[LangChain] Extended Search count: {self._extended_search_count}/{MAX_EXTENDED_SEARCHES_PER_MESSAGE}")

                        tool = next((t for t in self.tools if t.name == tool_name), None)
                        if not tool:
                            result = {"success": False, "error": f"Tool {tool_name} not found"}
                        else:
                            # Execute with a timeout, and heartbeats so the SSE
                            # connection survives long-running tools.
                            try:
                                tool_timeout = CODING_AGENT_TIMEOUT_SECONDS if tool_name in CODING_AGENT_TOOL_NAMES else TOOL_EXECUTION_TIMEOUT_SECONDS

                                is_coding_tool = tool_name in CODING_AGENT_TOOL_NAMES
                                tool_task = asyncio.create_task(tool.ainvoke(tool_args))
                                start_time = time.time()
                                heartbeat_count = 0
                                last_step_count = 0
                                last_progress = None

                                while not tool_task.done():
                                    elapsed = time.time() - start_time
                                    if elapsed >= tool_timeout:
                                        tool_task.cancel()
                                        try:
                                            await tool_task
                                        except asyncio.CancelledError:
                                            pass
                                        raise asyncio.TimeoutError(f"Tool execution timed out after {tool_timeout}s")

                                    heartbeat_count += 1
                                    logger.info(f"[LangChain] Tool {tool_name} still running ({elapsed:.0f}s), heartbeat #{heartbeat_count}")

                                    if is_coding_tool:
                                        step_events, last_step_count, last_progress = await self._poll_coding_agent_progress(last_step_count)
                                        for evt in step_events:
                                            yield evt

                                    yield {
                                        "event": EVENT_HEARTBEAT,
                                        "data": {"tool": tool_name, "elapsed_seconds": int(elapsed)}
                                    }

                                    try:
                                        done, _ = await asyncio.wait(
                                            {tool_task},
                                            timeout=TOOL_HEARTBEAT_INTERVAL_SECONDS
                                        )
                                        if done:
                                            break  # Task completed
                                    except asyncio.CancelledError:
                                        logger.warning(f"[LangChain] Tool {tool_name} wait cancelled, cancelling tool task")
                                        tool_task.cancel()
                                        raise

                                result = await tool_task
                                duration_ms = int((time.time() - start_time) * 1000)

                                logger.info(f"[LangChain] Tool {tool_name} completed after {duration_ms / 1000:.1f}s ({heartbeat_count} heartbeats sent)")

                            except asyncio.TimeoutError:
                                actual_timeout = CODING_AGENT_TIMEOUT_SECONDS if tool_name in CODING_AGENT_TOOL_NAMES else TOOL_EXECUTION_TIMEOUT_SECONDS
                                logger.error(
                                    "langchain.tool_execution_timeout",
                                    extra={
                                        "tool_name": tool_name,
                                        "timeout_seconds": actual_timeout,
                                    },
                                )
                                result = {
                                    "success": False,
                                    "error": f"Tool execution timed out after {actual_timeout // 60} minutes. Please try again with a simpler query.",
                                    "timeout": True
                                }
                            except asyncio.CancelledError:
                                logger.warning(f"[LangChain] Tool {tool_name} execution was cancelled")
                                result = {
                                    "success": False,
                                    "error": "Tool execution was cancelled",
                                    "cancelled": True
                                }
                                raise  # Re-raise to propagate cancellation

                            # Parse JSON result if it's a string
                            if isinstance(result, str):
                                try:
                                    result = json.loads(result)
                                except json.JSONDecodeError:
                                    result = {"success": True, "result": result}

                            # Coding agent tools: final data from the progress
                            # endpoint, or the stored-result fallback.
                            if is_coding_tool and isinstance(result, dict):
                                final_events, progress_data = await self._get_final_coding_agent_data(last_step_count, last_progress)
                                for evt in final_events:
                                    yield evt
                                yield self._build_coding_agent_completed_event(result, progress_data, duration_ms)
                                self._enrich_coding_agent_result(result, progress_data, duration_ms)

                        tool_results.append({
                            "tool_call": tool_call,
                            "result": result,
                            "success": result.get("success", True) if isinstance(result, dict) else True
                        })

                        logger.info(f"[LangChain] Tool {tool_name} returned: {result}")

                        # search_available_tools grows the bound tool set
                        if tool_name == "search_available_tools" and isinstance(result, dict):
                            tools_list = result.get("tools", [])
                            if tools_list:
                                discovered_ids = [t.get("function_name") for t in tools_list if t.get("function_name")]
                                self.add_discovered_tools(discovered_ids)
                                self._tool_registry.remember_search_result_metadata(tools_list)

                    except Exception as e:
                        logger.error(
                            "langchain.tool_failed",
                            extra={"tool_name": tool_name},
                            exc_info=True,
                        )
                        tool_results.append({
                            "tool_call": tool_call,
                            "result": {"success": False, "error": str(e)},
                            "success": False
                        })

                yield {
                    "event": EVENT_FILE_TOOL_EXECUTED,
                    "data": {
                        "tool_calls": self._add_display_names(tool_calls),
                        "results": tool_results
                    }
                }

                # Emit additional events (e.g. preview_started)
                for evt in self._emit_post_tool_events(tool_results):
                    yield evt

                # Accumulate tool costs via the shared classifier — see
                # `extract_billable_tool_costs` for the dedup rules.
                # image-gen dollars are tracked separately so the aggregate
                # deduct before the done event doesn't re-bill the per-image
                # UsageLog row written by image_tools._record_billing.
                batch_tool_cost, batch_image_gen_cost = extract_billable_tool_costs(tool_results)
                accumulated_tool_cost += batch_tool_cost
                image_gen_cost_in_bundle += batch_image_gen_cost
                if batch_tool_cost:
                    logger.info(f"[LangChain] Total tool cost: ${accumulated_tool_cost:.6f} (image-gen already billed per-image: ${image_gen_cost_in_bundle:.6f})")

                if self.enable_brave_search:
                    brave_sources = self._extract_brave_search_sources(tool_results)
                    if brave_sources:
                        yield {"event": EVENT_WEB_SOURCES, "data": {"sources": brave_sources}}

                # Add assistant message with tool calls to conversation.
                # IMPORTANT: when tool_calls are present and content is empty,
                # omit content — Amazon Bedrock/Nova rejects empty content
                # strings alongside tool_calls.
                assistant_msg = {
                    "role": "assistant",
                    "tool_calls": tool_calls
                }
                if accumulated_content:
                    assistant_msg["content"] = "".join(accumulated_content)
                openrouter_messages.append(assistant_msg)

                # Add tool results as tool messages
                for result_data in tool_results:
                    tool_call = result_data["tool_call"]
                    openrouter_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": self._format_tool_result_for_llm(
                            tool_call["function"]["name"], result_data["result"]
                        ),
                    })

                # Continue to next iteration

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
            is_413_error = is_request_too_large(e)

            if is_413_error and context_trim_count < MAX_CONTEXT_TRIM_RETRIES:
                # Strip the oldest non-system message and retry
                context_trim_count += 1
                num_history = len(openrouter_messages) - history_start_idx
                if num_history > 1:
                    removed = openrouter_messages.pop(history_start_idx)
                    removed_preview = str(removed.get("content", ""))[:TRIMMED_MESSAGE_PREVIEW_CHARS]
                    logger.warning(
                        f"[LangChain] 413 Context Too Large - trimming oldest message "
                        f"(attempt {context_trim_count}/{MAX_CONTEXT_TRIM_RETRIES}, "
                        f"{num_history - 1} messages remaining): {removed_preview}..."
                    )
                    yield {
                        "event": EVENT_CONTEXT_TRIMMED,
                        "data": {
                            "trimmed_count": context_trim_count,
                            "remaining_messages": len(openrouter_messages) - history_start_idx,
                        }
                    }
                    continue  # Retry with trimmed messages
                # Only the latest message is left: cannot trim further.

            if is_413_error:
                logger.warning(f"[LangChain] 413 Request Entity Too Large - giving up after {context_trim_count} trim(s)")
                yield context_too_large_event(DETAIL_CONTEXT_TOO_LARGE_AFTER_TRIM)
            else:
                logger.error("langchain.openai_api_error", exc_info=True)
                # error_payload attaches a machine code + specific message
                # for user-actionable errors (missing/invalid key, credits).
                yield {
                    "event": EVENT_ERROR,
                    "data": {"detail": error_str, **error_payload(e)}
                }

          except Exception as e:
            logger.error("langchain.stream_error", exc_info=True)
            yield {
                "event": EVENT_ERROR,
                "data": {"detail": str(e), **error_payload(e)}
            }

          # No exception, or a non-retryable one: leave the retry loop.
          break
