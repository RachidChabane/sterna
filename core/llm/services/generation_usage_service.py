"""
OpenRouter generation usage lookup (for precise billing after abort).
"""

import logging

import httpx as httpx_sync

logger = logging.getLogger(__name__)


def fetch_generation_usage(api_key: str, generation_id: str):
    """Query OpenRouter for exact usage/cost of a generation (even interrupted ones).

    OpenRouter takes ~15-20 seconds to finalize generation data after stream
    completion. Retries with backoff until the data is available. Returns
    `(body, status_code)` for the view to wrap in a Response.
    """
    import time

    # Retry with backoff: OpenRouter needs time to finalize generation data
    max_retries = 7
    delays = [2, 3, 3, 4, 4, 5, 5]  # Total wait: ~26 seconds

    try:
        with httpx_sync.Client(timeout=10.0) as client:
            for attempt in range(max_retries):
                response = client.get(
                    f"https://openrouter.ai/api/v1/generation?id={generation_id}",
                    headers={"Authorization": f"Bearer {api_key}"}
                )

                if response.status_code == 200:
                    gen_data = response.json().get("data", {})
                    prompt_tokens = gen_data.get("tokens_prompt", 0)
                    completion_tokens = gen_data.get("tokens_completion", 0)

                    return {
                        "usage": {
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": prompt_tokens + completion_tokens,
                        },
                        "cost": float(gen_data.get("total_cost", 0)),
                        "model": gen_data.get("model"),
                        "generation_id": generation_id,
                    }, 200

                if response.status_code == 404 and attempt < max_retries - 1:
                    # Generation not finalized yet, wait and retry
                    time.sleep(delays[attempt])
                    continue

                # Non-404 error or exhausted retries
                return {"error": f"OpenRouter returned {response.status_code}"}, 502

    except httpx_sync.TimeoutException:
        return {"error": "OpenRouter timeout"}, 504
    except Exception as e:
        logger.error(f"[GenerationUsage] Error querying OpenRouter: {e}")
        return {"error": str(e)}, 500
