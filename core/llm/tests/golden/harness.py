"""Capture and compare helpers shared by the golden SSE transcript tests.

A golden test drives one streaming endpoint through Django's test client
with the provider fully mocked, joins the whole response body, normalizes
it (see `normalization`), and compares it to a committed file under
`transcripts/`.

Set the environment variable `GOLDEN_UPDATE=1` to rewrite the transcripts
from the current behavior instead of asserting against them.
"""

import os
from decimal import Decimal
from pathlib import Path

from django.core.cache import cache
from django.utils import timezone

from .normalization import normalize

TRANSCRIPTS_DIR = Path(__file__).resolve().parent / "transcripts"
TRANSCRIPT_SUFFIX = ".sse"
UPDATE_ENV_VAR = "GOLDEN_UPDATE"

# --- Fixture constants ------------------------------------------------
#
# Deliberately non-UUID, non-hex shapes so no normalization rule can
# match them: what the fixture supplies must survive to the transcript
# byte for byte.

MODEL_ID = "fixture/golden-model"
MODEL_NAME = "Golden Fixture Model"
MODEL_PROVIDER = "fixture"
# Catalog prices are stored per 1K tokens (see llm/pricing_config.py).
# Fixed prices make every derived cost figure reproducible, so cost
# fields stay unnormalized and a pricing regression fails the test.
PROMPT_PRICE_PER_1K_TOKENS = Decimal("0.001")
COMPLETION_PRICE_PER_1K_TOKENS = Decimal("0.002")
MODEL_CONTEXT_LENGTH = 128000
MODEL_MAX_COMPLETION_TOKENS = 4096

CONVERSATION_ID = "conv-golden"
FILE_TOOL_CALL_ID = "toolcall-read-file"
CATALOG_TOOL_CALL_ID = "toolcall-web-search"
GENERATION_ID = "genid-golden-first"
FOLLOW_UP_GENERATION_ID = "genid-golden-follow-up"

FILE_TOOL_NAME = "read_file"
CATALOG_TOOL_NAME = "brave_web_search"

PROVIDER_ERROR_MESSAGE = "Upstream provider returned 502 Bad Gateway"

BILLING_PLAN_NAME = "golden-transcripts-plan"


def seed_model_catalog():
    """Insert the catalog row every golden scenario prices against."""
    from llm.models import ModelCatalog

    cache.clear()
    model, _ = ModelCatalog.objects.update_or_create(
        model_id=MODEL_ID,
        defaults={
            "name": MODEL_NAME,
            "provider": MODEL_PROVIDER,
            "description": "Catalog row backing the golden SSE transcripts.",
            "prompt_price": PROMPT_PRICE_PER_1K_TOKENS,
            "completion_price": COMPLETION_PRICE_PER_1K_TOKENS,
            "max_tokens": MODEL_CONTEXT_LENGTH,
            "max_completion_tokens": MODEL_MAX_COMPLETION_TOKENS,
            "supports_streaming": True,
            "supports_functions": True,
            "is_available": True,
            "output_modalities": ["text"],
            "input_modalities": ["text"],
            "fetched_at": timezone.now(),
        },
    )
    return model


def capture_sse(response) -> bytes:
    """Join a streaming response into the exact bytes a client receives.

    Works for both loops: V1 streams a synchronous generator, V2 an
    asynchronous one, and `StreamingHttpResponse.__iter__` drains either.
    """
    return b"".join(response)


def transcript_path(name: str) -> Path:
    return TRANSCRIPTS_DIR / f"{name}{TRANSCRIPT_SUFFIX}"


def assert_matches_golden(test_case, name: str, raw: bytes) -> None:
    """Compare a captured transcript to its committed golden file."""
    normalized = normalize(raw)
    path = transcript_path(name)

    if os.environ.get(UPDATE_ENV_VAR) == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(normalized)
        return

    test_case.assertTrue(
        path.exists(),
        f"Missing golden transcript {path}. Run with {UPDATE_ENV_VAR}=1 to create it.",
    )
    expected = path.read_bytes()
    test_case.assertEqual(
        normalized.decode("utf-8"),
        expected.decode("utf-8"),
        f"Captured SSE stream diverged from {path.name}.",
    )


def parse_event_names(raw: bytes) -> list:
    """Event names in the order the stream emitted them."""
    return [
        line[len("event: "):].decode("utf-8")
        for line in raw.split(b"\n")
        if line.startswith(b"event: ")
    ]


def assert_stream_is_substantive(test_case, raw: bytes, expected_events) -> None:
    """Guard against a golden file that locks in a degenerate stream.

    A quota denial or an authentication failure also produces a stable
    transcript; asserting the scenario's own events are present keeps such
    a stream from being committed as the baseline.
    """
    names = parse_event_names(raw)
    for expected in expected_events:
        test_case.assertIn(
            expected,
            names,
            f"Expected a '{expected}' event in the captured stream, got {names}.",
        )
