"""
Smart router: intelligent model routing engine.

Intercepts requests with model=AUTO_ROUTER_MODEL_ID, analyzes complexity,
and resolves to the optimal real model. Invisible downstream.
"""

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from llm.smart_router.classifier import ClassificationResult

logger = logging.getLogger(__name__)

# The public-facing "Auto" model id (product brand "Sterna"). This is the
# user-visible model slug, not the engine's internal name — kept unchanged
# even though the engine implementing it moved from llm.sterna to
# llm.smart_router. See .oss-prep/notes/naming-map.md.
AUTO_ROUTER_MODEL_ID = "ornithops/sterna"

# Tier 1 bypass: if heuristic score <= this AND confidence >= 0.85, skip Tier 2
TIER1_BYPASS_SCORE = 15
TIER1_BYPASS_CONFIDENCE = 0.85


@dataclass
class RoutingResolution:
    resolved_model_id: str
    resolved_model_name: str
    tier: int  # 1 = heuristic only, 2 = LLM classification
    heuristic_score: int
    llm_score: Optional[int]
    final_score: int
    cost_tier: str
    reason: str
    classification_cost_usd: Optional[float] = None
    classification_latency_ms: Optional[int] = None
    has_images: bool = False
    has_code: bool = False
    prompt_length: int = 0


class SmartRouter:
    @staticmethod
    def is_auto_router_model(model_id: str) -> bool:
        """Check if model_id is the auto-router variant. Strips OpenRouter suffixes."""
        if not model_id:
            return False
        return model_id.split(':')[0] == AUTO_ROUTER_MODEL_ID

    def resolve(
        self,
        model_id: str,
        messages: list,
        conversation_id: Optional[str] = None,
        user=None,
        excluded_models: Optional[list] = None,
        min_score_override: Optional[int] = None,
    ) -> RoutingResolution:
        """
        Resolve the auto-router model ID to a real model.

        1. Tier 1 heuristics
        2. Conversation context score
        3. Tier 2 LLM classification (if ambiguous)
        4. Select model from pool
        5. Update conversation tracker
        6. Log and emit metrics
        """
        from llm.smart_router.heuristics import score_message
        from llm.smart_router.classifier import classify_message
        from llm.smart_router.scorer import select_model
        from llm.smart_router.conversation_tracker import (
            get_conversation_score,
            update_conversation_score,
        )
        from llm.smart_router.metrics import record_routing_decision

        # 1. Tier 1 heuristics
        heuristic = score_message(messages)
        h_score = heuristic.score
        prompt_length = self._get_prompt_length(messages)

        # 2. Conversation context score
        conv_score = 0
        if conversation_id and user:
            conv_score = get_conversation_score(conversation_id, user)

        # 3. Apply min_score_override ("regenerate stronger")
        effective_score = h_score
        if min_score_override is not None:
            effective_score = max(effective_score, min_score_override)

        # 4. Decide if Tier 2 is needed
        tier = 1
        llm_score = None
        classification_cost = None
        classification_latency = None
        classification: Optional["ClassificationResult"] = None
        reason = ""

        if heuristic.is_trivial:
            reason = "trivial message"
        elif h_score <= TIER1_BYPASS_SCORE and heuristic.confidence >= TIER1_BYPASS_CONFIDENCE:
            reason = "simple message (high confidence)"
        elif heuristic.confidence < TIER1_BYPASS_CONFIDENCE and (
            min_score_override is None  # Don't classify if user forced strength
        ):
            # Tier 2: LLM classification
            classification = classify_message(messages, user=user)
            if classification:
                tier = 2
                llm_score = classification.score
                effective_score = max(effective_score, llm_score)
                classification_cost = classification.cost_usd
                classification_latency = classification.latency_ms
                reason = classification.reasoning or "LLM classification"
                if classification.from_cache:
                    reason = f"(cached) {reason}"
            else:
                reason = "Tier 2 failed, using heuristic"

        if not reason:
            reason = f"heuristic score {h_score}"

        # 5. Final score = max(effective, conversation)
        final_score = max(effective_score, conv_score)

        # Determine capability needs
        needs_vision = heuristic.has_images
        needs_reasoning = False
        needs_long_context = False

        if tier == 2 and classification:
            caps = classification.capabilities_needed
            needs_reasoning = caps.get('reasoning', False)
            needs_long_context = caps.get('long_context', False)
            if caps.get('vision', False):
                needs_vision = True

        # 6. Select model
        resolved_model_id, cost_tier = select_model(
            final_score=final_score,
            needs_vision=needs_vision,
            needs_reasoning=needs_reasoning,
            needs_long_context=needs_long_context,
            excluded_models=excluded_models,
        )

        # Get display name
        resolved_model_name = self._get_model_name(resolved_model_id)

        # 7. Update conversation tracker
        if conversation_id and user:
            try:
                update_conversation_score(
                    conversation_id, user, final_score, resolved_model_id
                )
            except Exception as e:
                logger.warning(f"[SmartRouter] Failed to update conversation score: {e}")

        # 8. Log decision
        if user:
            try:
                from llm.models import RoutingLog
                RoutingLog.objects.create(
                    user=user,
                    conversation_id=conversation_id or '',
                    tier_used=tier,
                    heuristic_score=h_score,
                    llm_score=llm_score,
                    final_score=final_score,
                    resolved_model_id=resolved_model_id,
                    prompt_length=prompt_length,
                    has_images=heuristic.has_images,
                    has_code=heuristic.has_code,
                    classification_cost_usd=classification_cost,
                    classification_latency_ms=classification_latency,
                )
            except Exception as e:
                logger.warning(f"[SmartRouter] Failed to log routing decision: {e}")

        # 9. Emit metrics
        try:
            record_routing_decision(
                tier=tier,
                resolved_model=resolved_model_id,
                cost_tier=cost_tier,
                score=final_score,
                classification_latency_ms=classification_latency,
            )
        except Exception as e:
            logger.debug(f"[SmartRouter] Failed to record metrics: {e}")

        return RoutingResolution(
            resolved_model_id=resolved_model_id,
            resolved_model_name=resolved_model_name,
            tier=tier,
            heuristic_score=h_score,
            llm_score=llm_score,
            final_score=final_score,
            cost_tier=cost_tier,
            reason=reason,
            classification_cost_usd=classification_cost,
            classification_latency_ms=classification_latency,
            has_images=heuristic.has_images,
            has_code=heuristic.has_code,
            prompt_length=prompt_length,
        )

    def reroute_on_rate_limit(
        self,
        failed_model: str,
        messages: list,
        conversation_id: Optional[str] = None,
        user=None,
        excluded_models: Optional[list] = None,
    ) -> Optional[str]:
        """Re-run resolution excluding the failed model."""
        excluded = list(excluded_models or [])
        if failed_model not in excluded:
            excluded.append(failed_model)

        try:
            resolution = self.resolve(
                model_id=AUTO_ROUTER_MODEL_ID,
                messages=messages,
                conversation_id=conversation_id,
                user=user,
                excluded_models=excluded,
            )

            if resolution.resolved_model_id != failed_model:
                # Log the reroute
                if user:
                    try:
                        from llm.models import RoutingLog
                        RoutingLog.objects.create(
                            user=user,
                            conversation_id=conversation_id or '',
                            tier_used=resolution.tier,
                            heuristic_score=resolution.heuristic_score,
                            llm_score=resolution.llm_score,
                            final_score=resolution.final_score,
                            resolved_model_id=resolution.resolved_model_id,
                            prompt_length=resolution.prompt_length,
                            has_images=resolution.has_images,
                            has_code=resolution.has_code,
                            is_reroute=True,
                            rerouted_from_model=failed_model,
                        )
                    except Exception:
                        pass
                return resolution.resolved_model_id
        except Exception as e:
            logger.warning(f"[SmartRouter] Reroute failed: {e}")

        return None

    def _get_prompt_length(self, messages: list) -> int:
        """Get length of the last user message."""
        for msg in reversed(messages):
            if msg.get('role') == 'user':
                content = msg.get('content', '')
                if isinstance(content, str):
                    return len(content)
                if isinstance(content, list):
                    return sum(
                        len(p.get('text', ''))
                        for p in content
                        if isinstance(p, dict) and p.get('type') == 'text'
                    )
        return 0

    def _get_model_name(self, model_id: str) -> str:
        """Get display name for a model ID."""
        try:
            from llm.models import ModelCatalog
            model = ModelCatalog.objects.filter(model_id=model_id).first()
            if model:
                return model.name
        except Exception:
            pass
        # Fallback: extract from model_id
        return model_id.split('/')[-1].replace('-', ' ').title()
