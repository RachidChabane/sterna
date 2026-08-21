"""
Conversation complexity score tracking with smooth per-turn decay.

Maintains a running complexity score per conversation to prevent jarring
model switches mid-conversation while still allowing downgrade when
the conversation becomes simpler.
"""

import logging

from django.db import transaction
from django.db.models import F

logger = logging.getLogger(__name__)

DECAY_FACTOR = 0.85  # 15% decay per simple turn after threshold
DOWNGRADE_THRESHOLD = 3  # Simple turns before decay starts
SIMPLE_SCORE_CEILING = 25  # Scores below this are "simple"


def get_conversation_score(conversation_id: str, user) -> int:
    """
    Get the effective conversation complexity score with smooth decay.

    Returns 0 for new conversations.
    """
    from llm.models import RoutingConversationScore

    try:
        record = RoutingConversationScore.objects.get(
            conversation_id=conversation_id, user=user
        )
    except RoutingConversationScore.DoesNotExist:
        return 0

    if record.consecutive_simple_turns >= DOWNGRADE_THRESHOLD:
        decay_turns = record.consecutive_simple_turns - DOWNGRADE_THRESHOLD + 1
        decayed = int(record.current_score * (DECAY_FACTOR ** decay_turns))
        return decayed

    return record.current_score


def update_conversation_score(
    conversation_id: str, user, new_score: int, resolved_model: str
):
    """
    Update conversation score atomically.

    Uses F() expressions for counter updates and select_for_update for score resets.
    """
    from llm.models import RoutingConversationScore

    record, created = RoutingConversationScore.objects.get_or_create(
        conversation_id=conversation_id,
        user=user,
        defaults={
            'current_score': new_score,
            'max_score': new_score,
            'turn_count': 1,
            'last_model_id': resolved_model,
            'consecutive_simple_turns': 0 if new_score >= SIMPLE_SCORE_CEILING else 1,
        },
    )
    if created:
        return

    if new_score < SIMPLE_SCORE_CEILING:
        # Atomic increment for simple turns
        RoutingConversationScore.objects.filter(pk=record.pk).update(
            consecutive_simple_turns=F('consecutive_simple_turns') + 1,
            turn_count=F('turn_count') + 1,
            last_model_id=resolved_model,
        )
    else:
        # Complex message — reset counter, update score
        with transaction.atomic():
            record = RoutingConversationScore.objects.select_for_update().get(pk=record.pk)
            record.consecutive_simple_turns = 0
            record.turn_count += 1
            record.current_score = max(record.current_score, new_score)
            record.max_score = max(record.max_score, new_score)
            record.last_model_id = resolved_model
            record.save()
