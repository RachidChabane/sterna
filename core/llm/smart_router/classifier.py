"""
Tier 2 LLM-based complexity classification for the smart router.

Uses Gemini Flash via OpenRouter for fast, cheap complexity scoring.
Results are cached in Redis for 5 minutes.
"""

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

from django.core.cache import cache

logger = logging.getLogger(__name__)

CLASSIFIER_MODEL = "google/gemini-2.0-flash"
CACHE_PREFIX = "smart_router:classify"
CACHE_TTL = 300  # 5 minutes

CLASSIFICATION_PROMPT = """You are a request complexity classifier. Analyze the user's message and return JSON.

The message below may be truncated. Original message length: {original_length} characters.

Dimensions: knowledge depth, reasoning complexity, output quality, technical depth, context dependency.
Longer messages (>2000 chars) often indicate higher complexity (code pastes, detailed requirements).

Return ONLY valid JSON:
{{"complexity_score": 0-100, "reasoning": "...", "capabilities_needed": {{"vision": false, "reasoning": false, "long_context": false, "coding": false, "math": false}}}}

Score guide:
0-20: Greetings, simple factual questions, basic translations
21-40: Moderate questions, simple summaries, basic explanations
41-60: Multi-step reasoning, code generation, detailed analysis
61-80: Complex system design, advanced debugging, research synthesis
81-100: Novel problem solving, formal proofs, multi-domain expertise"""


@dataclass
class ClassificationResult:
    score: int
    reasoning: str
    capabilities_needed: dict
    cost_usd: Optional[float]
    latency_ms: int
    from_cache: bool


def _truncate_message(text: str, max_total: int = 1000) -> tuple:
    """Smart truncation preserving start and end of message."""
    original_length = len(text)
    if len(text) <= max_total:
        return text, original_length
    half = max_total // 2
    return (
        f"{text[:half]}\n\n[... {original_length - max_total} chars omitted ...]\n\n{text[-half:]}",
        original_length,
    )


def _build_history_context(messages: list, max_turns: int = 3) -> str:
    """Build context from recent conversation turns."""
    recent = []
    for msg in reversed(messages[:-1]):  # Exclude last message
        if msg.get('role') in ('user', 'assistant'):
            content = msg.get('content', '')
            if isinstance(content, list):
                content = ' '.join(
                    p.get('text', '') for p in content
                    if isinstance(p, dict) and p.get('type') == 'text'
                )
            recent.append(f"{msg['role']}: {content[:500]}")
            if len(recent) >= max_turns:
                break
    if not recent:
        return ""
    recent.reverse()
    return "Recent conversation context:\n" + "\n".join(recent) + "\n\n"


def _extract_json(text: str) -> Optional[dict]:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try extracting from code block
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding first JSON object
    match = re.search(r'\{[^{}]*"complexity_score"[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def classify_message(messages: list, user=None) -> Optional[ClassificationResult]:
    """
    Classify message complexity using Gemini Flash.

    Returns ClassificationResult or None on failure (caller should fall back to Tier 1).
    """
    from llm.client import OpenRouterClient

    # Get last user message text
    last_text = ''
    for msg in reversed(messages):
        if msg.get('role') == 'user':
            content = msg.get('content', '')
            if isinstance(content, str):
                last_text = content
            elif isinstance(content, list):
                last_text = ' '.join(
                    p.get('text', '') for p in content
                    if isinstance(p, dict) and p.get('type') == 'text'
                )
            break

    if not last_text:
        return None

    # Check cache
    cache_key = f"{CACHE_PREFIX}:{hashlib.md5(last_text[:500].encode()).hexdigest()}"
    cached = cache.get(cache_key)
    if cached is not None:
        logger.debug(f"[SmartRouter Classifier] Cache hit for {cache_key}")
        return ClassificationResult(
            score=cached['score'],
            reasoning=cached.get('reasoning', ''),
            capabilities_needed=cached.get('capabilities_needed', {}),
            cost_usd=None,
            latency_ms=0,
            from_cache=True,
        )

    # Truncate for classification
    truncated_text, original_length = _truncate_message(last_text)
    history_context = _build_history_context(messages)

    prompt = CLASSIFICATION_PROMPT.format(original_length=original_length)
    user_content = f"{history_context}User message:\n{truncated_text}"

    try:
        start_time = time.time()
        # request_source value is persisted verbatim on OpenRouterGenerationRecord
        # rows (core/llm/models.py) for provider analytics attribution — kept
        # unchanged by the engine rename so historical rows stay queryable.
        client = OpenRouterClient(user=user, request_source='sterna_classifier')
        result = client.complete(
            model=CLASSIFIER_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.0,
            max_tokens=200,
            stream=False,
        )
        latency_ms = int((time.time() - start_time) * 1000)

        content = result.get('content', '')
        parsed = _extract_json(content)

        if not parsed or 'complexity_score' not in parsed:
            logger.warning(f"[SmartRouter Classifier] Invalid response: {content[:200]}")
            return None

        score = max(0, min(100, int(parsed['complexity_score'])))
        capabilities = parsed.get('capabilities_needed', {})
        reasoning = parsed.get('reasoning', '')

        # Calculate cost
        cost_usd = result.get('cost')

        # Cache the result
        cache.set(cache_key, {
            'score': score,
            'reasoning': reasoning,
            'capabilities_needed': capabilities,
        }, timeout=CACHE_TTL)

        return ClassificationResult(
            score=score,
            reasoning=reasoning,
            capabilities_needed=capabilities,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            from_cache=False,
        )

    except Exception as e:
        logger.warning(f"[SmartRouter Classifier] Classification failed: {e}")
        return None
