"""
AI-powered analyzer for Consigliere.

Uses LLM to generate conversation analysis and model recommendations.
"""

import logging
import json
import time
from typing import Dict, Any, Optional, Callable

from llm.client import OpenRouterClient
from llm.models import ModelCatalog
from llm.exceptions import OpenRouterException, ContextLimitExceededException
from llm.context_utils import calculate_dynamic_max_tokens
from ..prompts import AI_COMPLETE_ANALYSIS_TEMPLATE
from ..config import AIAnalysisConfig

logger = logging.getLogger(__name__)


class ProgressCallback:
    """
    Callback handler for progress updates during AI analysis.

    Allows streaming progress updates to the frontend in real-time.
    """

    def __init__(self, callback_fn: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        Initialize progress callback.

        Args:
            callback_fn: Function to call with progress updates.
                         Receives dict with {step, status, message, timestamp}
        """
        self.callback = callback_fn

    def update(self, step: str, status: str, message: str = ""):
        """
        Send progress update.

        Args:
            step: Step identifier (e.g., "preparing_context", "calling_ai")
            status: Status of step ("pending", "in_progress", "completed", "error")
            message: Optional message with details
        """
        if self.callback:
            self.callback({
                "step": step,
                "status": status,
                "message": message,
                "timestamp": time.time()
            })


class AIAnalyzer:
    """
    AI-powered conversation analyzer that uses LLM to generate insights and recommendations.
    """

    def __init__(self, current_model: str, user=None):
        """
        Initialize AI analyzer.

        Args:
            current_model: Model ID to use for analysis generation
            user: User object for API key resolution
        """
        self.client = OpenRouterClient(user=user, request_source='ai_analyzer')
        self.model = current_model

    def analyze_with_ai_streaming(
        self,
        chat_group_data: Dict[str, Any],
        current_model_id: str,
        metrics: Dict[str, Any],
    ):
        """
        Generate complete analysis using AI with streaming progress events.

        This is a generator that yields progress events and final result.

        Args:
            chat_group_data: Full ChatGroup data from frontend
            current_model_id: Currently selected model ID
            metrics: Pre-calculated metrics (total_messages, total_cost, etc.)

        Yields:
            Progress events as dicts with {step, status, message, timestamp}
            Final result as {"_result": analysis_data}
        """
        # Step 1: Build conversation content
        yield {
            "step": "preparing_context",
            "status": "in_progress",
            "message": "Building conversation context...",
            "timestamp": time.time()
        }

        conversation_content = self._build_conversation_content(chat_group_data)

        yield {
            "step": "preparing_context",
            "status": "completed",
            "message": "Context prepared",
            "timestamp": time.time()
        }

        # Step 2: Get available models for recommendations
        yield {
            "step": "fetching_models",
            "status": "in_progress",
            "message": "Fetching available models...",
            "timestamp": time.time()
        }

        available_models = self._get_available_models_text()

        # Get current model info
        current_model_info = self._get_current_model_info(current_model_id)

        # Build models used text
        models_used = self._get_models_used(chat_group_data)

        # Extract model IDs used for validation
        models_used_ids = self._extract_model_ids_from_chat_group(chat_group_data)

        yield {
            "step": "fetching_models",
            "status": "completed",
            "message": "Models fetched",
            "timestamp": time.time()
        }

        # Build prompt
        prompt = AI_COMPLETE_ANALYSIS_TEMPLATE.format(
            conversation_content=conversation_content,
            total_messages=metrics.get("total_messages", 0),
            models_used=models_used,
            total_cost=float(metrics.get("total_cost", 0)),
            avg_latency=metrics.get("avg_latency", 0.0),
            total_tokens=metrics.get("total_tokens", 0),
            current_model_id=current_model_id,
            current_model_name=current_model_info.get("name", "Unknown"),
            current_model_provider=current_model_info.get("provider", "Unknown"),
            available_models=available_models,
        )

        try:
            start_time = time.time()

            # Step 3: Calculate dynamic max_tokens based on model and prompt size
            # Build messages for the API call
            messages = [{"role": "user", "content": prompt}]

            # Use shared utility function for dynamic max_tokens calculation
            actual_max_tokens = calculate_dynamic_max_tokens(
                model_id=self.model,
                messages=messages,
                configured_max_tokens=AIAnalysisConfig.MAX_TOKENS,
                min_viable_tokens=2000  # Need at least 2000 tokens for JSON response
            )

            # Step 4: Call AI (longest step)
            yield {
                "step": "calling_ai",
                "status": "in_progress",
                "message": "Generating AI analysis...",
                "timestamp": time.time()
            }

            response = self.client.complete(
                model=self.model,
                messages=messages,
                temperature=AIAnalysisConfig.TEMPERATURE,
                max_tokens=actual_max_tokens,
            )

            end_time = time.time()
            latency = end_time - start_time

            yield {
                "step": "calling_ai",
                "status": "completed",
                "message": f"AI response received in {latency:.1f}s",
                "timestamp": time.time()
            }

            content = response.get("content", "")

            # Step 4: Parse JSON response
            yield {
                "step": "parsing_response",
                "status": "in_progress",
                "message": "Parsing AI response...",
                "timestamp": time.time()
            }

            analysis_data = self._parse_ai_response(content, models_used_ids)

            yield {
                "step": "parsing_response",
                "status": "completed",
                "message": "Response parsed successfully",
                "timestamp": time.time()
            }

            # Step 5: Calculate real cost tradeoffs
            yield {
                "step": "calculating_costs",
                "status": "in_progress",
                "message": "Calculating cost tradeoffs...",
                "timestamp": time.time()
            }

            analysis_data = self._calculate_real_cost_tradeoffs(
                analysis_data, chat_group_data, metrics
            )

            yield {
                "step": "calculating_costs",
                "status": "completed",
                "message": "Cost tradeoffs calculated",
                "timestamp": time.time()
            }

            # Step 6: Add metadata and finalize
            yield {
                "step": "saving",
                "status": "in_progress",
                "message": "Finalizing analysis...",
                "timestamp": time.time()
            }

            analysis_data["ai_model_used"] = response.get("model", self.model)
            analysis_data["ai_latency"] = latency
            analysis_data["ai_tokens_used"] = response.get("usage", {}).get(
                "total_tokens", 0
            )

            logger.info(
                f"AI analysis completed in {latency:.2f}s using {analysis_data['ai_model_used']}"
            )

            yield {
                "step": "saving",
                "status": "completed",
                "message": "Analysis complete",
                "timestamp": time.time()
            }

            # Yield final result with special key
            yield {"_result": analysis_data}

        except ContextLimitExceededException as e:
            logger.error(f"Context limit exceeded: {e}")
            raise

        except OpenRouterException as e:
            logger.error(f"OpenRouter error in AI analysis: {e}")
            raise

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            logger.error(f"AI response content: {content}")
            raise ValueError(f"AI returned invalid JSON: {str(e)}")

        except Exception as e:
            logger.error(f"Unexpected error in AI analysis: {e}", exc_info=True)
            raise

    def analyze_with_ai(
        self,
        chat_group_data: Dict[str, Any],
        current_model_id: str,
        metrics: Dict[str, Any],
        progress_callback: Optional[ProgressCallback] = None,
    ) -> Dict[str, Any]:
        """
        Generate complete analysis using AI (non-streaming version for backwards compatibility).

        Args:
            chat_group_data: Full ChatGroup data from frontend
            current_model_id: Currently selected model ID
            metrics: Pre-calculated metrics (total_messages, total_cost, etc.)
            progress_callback: Optional callback for progress updates (ignored, use streaming version)

        Returns:
            Dictionary containing AI-generated analysis
        """
        # Use streaming version and extract final result
        result = None
        for event in self.analyze_with_ai_streaming(chat_group_data, current_model_id, metrics):
            if "_result" in event:
                result = event["_result"]
                break

        if result is None:
            raise ValueError("No result returned from streaming analysis")

        return result

    def _build_conversation_content(self, chat_group: Dict[str, Any]) -> str:
        """Build formatted conversation content for the prompt.

        Includes lightweight attachment context (counts and filenames) so the AI
        is aware that files/images/PDFs were shared without including their
        actual contents.
        """
        chats = chat_group.get("chats", [])

        if not chats:
            return "No conversation messages available."

        content_lines = []
        max_messages_per_chat = AIAnalysisConfig.MAX_MESSAGES_PER_CHAT
        max_message_length = AIAnalysisConfig.MAX_MESSAGE_LENGTH

        # Conversation-level attachments summary (from attachments_meta on messages)
        total_images = 0
        total_pdfs = 0
        total_files = 0
        for chat in chats:
            for m in chat.get("messages", []):
                for att in m.get("attachments_meta", []) or []:
                    if att.get("type") == "image":
                        total_images += 1
                    elif att.get("type") == "file":
                        if att.get("is_pdf"):
                            total_pdfs += 1
                        else:
                            total_files += 1

        if total_images or total_pdfs or total_files:
            parts = []
            if total_images:
                parts.append(f"{total_images} image{'s' if total_images != 1 else ''}")
            if total_pdfs:
                parts.append(f"{total_pdfs} PDF{'s' if total_pdfs != 1 else ''}")
            if total_files:
                parts.append(f"{total_files} file{'s' if total_files != 1 else ''}")
            content_lines.append(
                f"[Attachment Summary] Conversation included: {', '.join(parts)}"
            )
            content_lines.append("")

        for chat_idx, chat in enumerate(chats):
            messages = chat.get("messages", [])
            if not messages:
                continue

            model_name = chat.get("model", {}).get("name", "Unknown Model")
            content_lines.append(f"\n[Chat {chat_idx + 1} - {model_name}]")

            # Take recent messages
            recent_messages = messages[-max_messages_per_chat:]

            for msg in recent_messages:
                role = msg.get("role", "unknown").capitalize()
                content = msg.get("content", "")

                # Truncate long messages
                if len(content) > max_message_length:
                    content = content[:max_message_length] + "... [truncated]"

                content_lines.append(f"{role}: {content}")

                # If this message carried attachments, add a short note with filenames
                attachments_meta = msg.get("attachments_meta") or []
                if attachments_meta:
                    images = [a for a in attachments_meta if a.get("type") == "image"]
                    pdfs = [a for a in attachments_meta if a.get("type") == "file" and a.get("is_pdf")]
                    other_files = [a for a in attachments_meta if a.get("type") == "file" and not a.get("is_pdf")]

                    parts = []

                    # Images with filenames
                    if images:
                        img_names = [a.get("filename") for a in images[:3] if a.get("filename")]
                        if img_names:
                            parts.append(f"{len(images)} image{'s' if len(images) != 1 else ''} ({', '.join(img_names)})")
                        else:
                            parts.append(f"{len(images)} image{'s' if len(images) != 1 else ''}")

                    # PDFs with filenames
                    if pdfs:
                        pdf_names = [a.get("filename") for a in pdfs[:3] if a.get("filename")]
                        if pdf_names:
                            parts.append(f"{len(pdfs)} PDF{'s' if len(pdfs) != 1 else ''} ({', '.join(pdf_names)})")
                        else:
                            parts.append(f"{len(pdfs)} PDF{'s' if len(pdfs) != 1 else ''}")

                    # Other files with filenames
                    if other_files:
                        file_names = [a.get("filename") for a in other_files[:3] if a.get("filename")]
                        if file_names:
                            parts.append(f"{len(other_files)} file{'s' if len(other_files) != 1 else ''} ({', '.join(file_names)})")
                        else:
                            parts.append(f"{len(other_files)} file{'s' if len(other_files) != 1 else ''}")

                    content_lines.append(f"  ↳ Attachments: {', '.join(parts)}")

            # Add separator
            if chat_idx < len(chats) - 1:
                content_lines.append("")

        return "\n".join(content_lines) if content_lines else "No messages found."

    def _get_available_models_text(self) -> str:
        """Get formatted list of available models for recommendations."""
        models = ModelCatalog.objects.filter(
            is_available=True,
            prompt_price__isnull=False,
            completion_price__isnull=False,
        ).values(
            "model_id",
            "name",
            "provider",
            "prompt_price",
            "completion_price",
            "max_tokens",
        )[
            :AIAnalysisConfig.AVAILABLE_MODELS_LIMIT
        ]

        if not models:
            return "No models available"

        lines = []
        for model in models:
            avg_price = (
                float(model["prompt_price"]) + float(model["completion_price"])
            ) / 2
            lines.append(
                f"- {model['model_id']} ({model['name']}) by {model['provider']} "
                f"- Avg price: ${avg_price:.6f}/1K tokens, Max tokens: {model['max_tokens'] or 'N/A'}"
            )

        return "\n".join(lines)

    def _get_current_model_info(self, model_id: str) -> Dict[str, Any]:
        """Get current model information."""
        try:
            model = ModelCatalog.objects.get(model_id=model_id)
            return {
                "name": model.name,
                "provider": model.provider,
                "prompt_price": float(model.prompt_price or 0),
                "completion_price": float(model.completion_price or 0),
            }
        except ModelCatalog.DoesNotExist:
            logger.warning(f"Model {model_id} not found in catalog")
            return {"name": "Unknown", "provider": "Unknown"}

    def _extract_model_ids_from_chat_group(self, chat_group: Dict[str, Any]) -> set:
        """
        Extract unique model IDs used in the conversation.

        Args:
            chat_group: ChatGroup data

        Returns:
            Set of model IDs that were actually used
        """
        chats = chat_group.get("chats", [])
        model_ids = set()

        for chat in chats:
            model = chat.get("model", {})
            model_id = model.get("model_id")  # Use model_id, not id (which is the chat UUID)
            if model_id:
                model_ids.add(model_id)

        return model_ids

    def _get_models_used(self, chat_group: Dict[str, Any]) -> str:
        """Get detailed list of models used in the conversation with metrics."""
        chats = chat_group.get("chats", [])
        models_data = {}

        for chat in chats:
            model = chat.get("model", {})
            model_id = model.get("model_id")  # Use model_id, not id (which is the chat UUID)
            model_name = model.get("name", "Unknown")

            if not model_id:
                continue

            # Initialize or update model entry
            if model_id not in models_data:
                models_data[model_id] = {
                    "model_id": model_id,
                    "model_name": model_name,
                    "message_count": 0,
                    "total_cost": 0.0,
                    "total_latency": 0.0,
                    "latency_count": 0,
                }

            # Count messages and aggregate metrics
            messages = chat.get("messages", [])
            for msg in messages:
                if msg.get("role") == "assistant":
                    models_data[model_id]["message_count"] += 1

                    if msg.get("cost"):
                        models_data[model_id]["total_cost"] += float(msg.get("cost", 0))

                    if msg.get("latency"):
                        # Convert from milliseconds to seconds
                        models_data[model_id]["total_latency"] += float(msg.get("latency", 0)) / 1000.0
                        models_data[model_id]["latency_count"] += 1

        if not models_data:
            return "None"

        # Format output with metrics
        lines = []
        for model_info in sorted(models_data.values(), key=lambda x: x["message_count"], reverse=True):
            msg_count = model_info["message_count"]
            avg_cost = model_info["total_cost"] / msg_count if msg_count > 0 else 0.0
            avg_latency = (
                model_info["total_latency"] / model_info["latency_count"]
                if model_info["latency_count"] > 0
                else 0.0
            )

            lines.append(
                f"- {model_info['model_id']} ({model_info['model_name']}): "
                f"{msg_count} messages, avg cost ${avg_cost:.4f}/msg, avg latency {avg_latency:.2f}s"
            )

        return "\n".join(lines)

    def _parse_ai_response(self, content: str, models_used_ids: Optional[set] = None) -> Dict[str, Any]:
        """
        Parse AI response and validate structure.

        Args:
            content: Raw response content from AI
            models_used_ids: Set of model IDs actually used in the conversation

        Returns:
            Validated analysis dictionary
        """
        if models_used_ids is None:
            models_used_ids = set()
        # Log the raw response for debugging
        logger.debug(f"Raw AI response (first 500 chars): {content[:500]}")

        # Try to extract JSON from response (in case AI adds extra text)
        content = content.strip()

        json_str = None

        # Try to extract from markdown code block first
        import re
        markdown_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if markdown_match:
            json_str = markdown_match.group(1)
            logger.debug("Extracted JSON from markdown code block")
        else:
            # Find JSON object in content
            start_idx = content.find("{")
            end_idx = content.rfind("}") + 1

            if start_idx == -1 or end_idx == 0:
                logger.error(f"No JSON object found in AI response. Full response: {content}")
                raise ValueError(f"No JSON object found in AI response. Response starts with: {content[:200]}")

            json_str = content[start_idx:end_idx]
            logger.debug("Extracted JSON from raw content")

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}. JSON string: {json_str[:500]}")
            raise ValueError(f"Invalid JSON in AI response: {str(e)}")

        # Validate required fields
        required_fields = [
            "conversation_type",
            "detected_needs",
            "insights",
            "recommended_from_conversation",
            "alternative_models",
        ]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        # Validate detected_needs structure
        detected_needs = data["detected_needs"]
        required_needs = ["creativity", "precision", "speed", "cost_efficiency"]
        for need in required_needs:
            if need not in detected_needs:
                raise ValueError(f"Missing detected_need: {need}")
            if detected_needs[need] not in ["high", "medium", "low"]:
                raise ValueError(
                    f"Invalid value for {need}: {detected_needs[need]} (must be high/medium/low)"
                )

        # Validate insights
        if not isinstance(data["insights"], list) or len(data["insights"]) == 0:
            raise ValueError("insights must be a non-empty list")

        # Validate recommended_from_conversation
        rec_from_conv = data["recommended_from_conversation"]
        required_rec_from_conv_fields = [
            "model_id",
            "model_name",
            "provider",
            "reasoning",
            "score",
            "metrics",
        ]
        for field in required_rec_from_conv_fields:
            if field not in rec_from_conv:
                raise ValueError(f"Missing field in recommended_from_conversation: {field}")

        # Validate that recommended model is from the conversation
        recommended_model_id = rec_from_conv["model_id"]
        if models_used_ids and recommended_model_id not in models_used_ids:
            logger.warning(
                f"AI recommended model '{recommended_model_id}' was not used in the conversation. "
                f"Models used: {models_used_ids}"
            )
            raise ValueError(
                f"Recommended model '{recommended_model_id}' must be one of the models "
                f"actually used in the conversation: {', '.join(sorted(models_used_ids))}"
            )

        # Validate alternative_models
        if (
            not isinstance(data["alternative_models"], list)
            or len(data["alternative_models"]) == 0
        ):
            raise ValueError("alternative_models must be a non-empty list")

        for rec in data["alternative_models"]:
            required_rec_fields = [
                "model_id",
                "model_name",
                "provider",
                "rank",
                "score",
                "reasoning",
            ]
            for field in required_rec_fields:
                if field not in rec:
                    raise ValueError(f"Missing field in alternative model: {field}")

        logger.info("AI response validated successfully")
        return data

    def _calculate_real_cost_tradeoffs(
        self,
        analysis_data: Dict[str, Any],
        chat_group_data: Dict[str, Any],
        metrics: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Calculate real cost tradeoffs based on model catalog prices.

        Compares average token prices between the recommended model and alternatives.

        Args:
            analysis_data: Parsed AI response data
            chat_group_data: Full ChatGroup data (unused)
            metrics: Pre-calculated metrics (unused)

        Returns:
            analysis_data with updated tradeoffs (cost_savings, baseline info)
        """
        # Get recommended model from conversation (chosen by AI)
        recommended_from_conv = analysis_data.get("recommended_from_conversation")
        if not recommended_from_conv:
            logger.warning("No recommended_from_conversation available for cost calculation")
            return analysis_data

        # Get the baseline model info
        try:
            baseline_model_id = recommended_from_conv["model_id"]
            baseline_model = ModelCatalog.objects.get(model_id=baseline_model_id)

            # Check if pricing data exists
            if baseline_model.prompt_price is None or baseline_model.completion_price is None:
                logger.warning(f"Baseline model {baseline_model.model_id} has no pricing data")
                return analysis_data

            # Calculate average price for baseline model (simple average of prompt + completion)
            baseline_avg_price = (
                float(baseline_model.prompt_price) + float(baseline_model.completion_price)
            ) / 2

            # Update cost_savings for each alternative model
            for rec in analysis_data.get("alternative_models", []):
                try:
                    alternative_model = ModelCatalog.objects.get(model_id=rec["model_id"])

                    # Check if pricing data exists
                    if alternative_model.prompt_price is None or alternative_model.completion_price is None:
                        logger.warning(f"Alternative model {rec['model_id']} has no pricing data")
                        continue

                    # Calculate average price for alternative model
                    alternative_avg_price = (
                        float(alternative_model.prompt_price) + float(alternative_model.completion_price)
                    ) / 2

                    # Update tradeoffs
                    if "tradeoffs" not in rec:
                        rec["tradeoffs"] = {}

                    rec["tradeoffs"]["baseline_model_name"] = baseline_model.name
                    rec["tradeoffs"]["baseline_model_id"] = baseline_model.model_id

                    # Handle free models specially
                    if baseline_avg_price == 0 and alternative_avg_price == 0:
                        # Both models are free
                        rec["tradeoffs"]["cost_savings"] = "BOTH_FREE"
                        rec["tradeoffs"]["is_baseline_free"] = True
                        logger.debug(f"Both models are free: baseline={baseline_model.model_id}, alternative={rec['model_id']}")

                    elif baseline_avg_price == 0 and alternative_avg_price > 0:
                        # Baseline is free, alternative is paid
                        rec["tradeoffs"]["cost_savings"] = "BASELINE_FREE"
                        rec["tradeoffs"]["is_baseline_free"] = True
                        logger.debug(
                            f"Baseline is free but alternative is paid: "
                            f"baseline={baseline_model.model_id}, alternative={rec['model_id']} (${alternative_avg_price:.6f})"
                        )

                    elif baseline_avg_price > 0 and alternative_avg_price == 0:
                        # Baseline is paid, alternative is free (100% savings)
                        rec["tradeoffs"]["cost_savings"] = "+100%"
                        logger.debug(
                            f"Alternative is free (100% savings): "
                            f"baseline=${baseline_avg_price:.6f}, alternative={rec['model_id']}"
                        )

                    else:
                        # Both models are paid - calculate percentage difference
                        cost_delta = ((baseline_avg_price - alternative_avg_price) / baseline_avg_price) * 100
                        rec["tradeoffs"]["cost_savings"] = f"{cost_delta:+.0f}%"
                        logger.debug(
                            f"Calculated cost tradeoff for {rec['model_id']}: {cost_delta:+.0f}% "
                            f"(baseline avg: ${baseline_avg_price:.6f}, alternative avg: ${alternative_avg_price:.6f})"
                        )

                except ModelCatalog.DoesNotExist:
                    logger.warning(f"Alternative model {rec['model_id']} not found in catalog")
                    continue

        except (ValueError, ModelCatalog.DoesNotExist) as e:
            logger.warning(f"Could not calculate cost tradeoffs: {e}")

        return analysis_data
