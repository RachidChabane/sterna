"""
Tier 1 heuristic scoring for the smart router.

Analyzes message content to estimate complexity without any LLM call.
Designed to be language-agnostic where possible.
"""

import re
from dataclasses import dataclass


@dataclass
class HeuristicResult:
    score: int
    confidence: float
    has_images: bool
    has_code: bool
    is_trivial: bool


# Reasoning keywords (English-only — documented limitation)
REASONING_KEYWORDS = {
    'analyze', 'debug', 'refactor', 'optimize', 'architect', 'design',
    'implement', 'evaluate', 'compare', 'contrast', 'explain', 'prove',
    'derive', 'synthesize', 'critique', 'review', 'diagnose', 'investigate',
    'troubleshoot', 'benchmark', 'migrate', 'integrate', 'decompose',
}

# File extension patterns
FILE_EXTENSION_RE = re.compile(
    r'\.\b(?:py|js|ts|tsx|jsx|java|cpp|c|h|go|rs|rb|php|cs|swift|kt|'
    r'scala|r|sql|html|css|scss|yaml|yml|json|xml|toml|md|csv|xlsx|pdf)\b'
)

# LaTeX patterns
LATEX_RE = re.compile(r'\\(?:frac|int|sum|begin|end|alpha|beta|gamma|delta|theta|lambda|sigma|partial|nabla)')

# URL pattern
URL_RE = re.compile(r'https?://')

# Code indicators
CODE_CHARS = set('{}[]();`~<>|\\')
CODE_BLOCK_RE = re.compile(r'```')


def _is_trivial_message(text: str) -> bool:
    """Language-agnostic trivial message detection."""
    if len(text) > 30:
        return False
    tokens = text.split()
    if len(tokens) > 3:
        return False
    if any(c in CODE_CHARS for c in text):
        return False
    if 'http' in text.lower():
        return False
    return True


def _has_images(messages: list) -> bool:
    """Check if any message contains image content."""
    for msg in messages:
        content = msg.get('content')
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get('type') == 'image_url':
                    return True
    return False


def _get_last_user_text(messages: list) -> str:
    """Extract text from the last user message."""
    for msg in reversed(messages):
        if msg.get('role') != 'user':
            continue
        content = msg.get('content', '')
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get('type') == 'text':
                    parts.append(part.get('text', ''))
            return ' '.join(parts)
    return ''


def _count_user_turns(messages: list) -> int:
    """Count the number of user messages."""
    return sum(1 for m in messages if m.get('role') == 'user')


def score_message(messages: list) -> HeuristicResult:
    """
    Score a message list using Tier 1 heuristics.

    Returns a HeuristicResult with score (0-100), confidence, and feature flags.
    """
    text = _get_last_user_text(messages)
    has_img = _has_images(messages)
    turn_count = _count_user_turns(messages)

    # Trivial message fast path
    if _is_trivial_message(text) and not has_img:
        return HeuristicResult(
            score=5,
            confidence=0.95,
            has_images=False,
            has_code=False,
            is_trivial=True,
        )

    score = 0
    has_code_detected = False

    # Prompt length scoring
    text_len = len(text)
    if text_len < 50:
        pass  # +0
    elif text_len < 200:
        score += 10
    elif text_len < 500:
        score += 20
    elif text_len < 2000:
        score += 35
    else:
        score += 50

    # Turn count
    if turn_count > 10:
        score += 15
    elif turn_count > 5:
        score += 8

    # Images
    if has_img:
        score += 20

    # File references
    if FILE_EXTENSION_RE.search(text):
        score += 15

    # Code blocks / syntax
    if CODE_BLOCK_RE.search(text):
        score += 20
        has_code_detected = True
    elif sum(1 for c in text if c in CODE_CHARS) > 3:
        score += 20
        has_code_detected = True

    # LaTeX
    if LATEX_RE.search(text):
        score += 15

    # URLs
    if URL_RE.search(text):
        score += 5

    # Reasoning keywords (English-only)
    text_lower = text.lower()
    matching_keywords = sum(1 for kw in REASONING_KEYWORDS if kw in text_lower)
    if matching_keywords >= 3:
        score += 25

    # Cap at 100
    score = min(score, 100)

    # Confidence
    if score <= 15:
        confidence = 0.9
    elif score >= 70:
        confidence = 0.85
    else:
        confidence = 0.5

    return HeuristicResult(
        score=score,
        confidence=confidence,
        has_images=has_img,
        has_code=has_code_detected,
        is_trivial=False,
    )
