"""
Cost estimation for completions.

Owns the pricing math `CompletionViewSet.estimate_cost` and
`estimate_batch_cost` return; the view keeps only request/response
serialization.
"""

import logging
from typing import Any, Dict, List

from ..catalog_service import CatalogService
from ..prompts_v2 import estimate_system_prompt

logger = logging.getLogger(__name__)


def estimate_single_cost(model_id: str, prompt_tokens: int, completion_tokens: int) -> dict:
    """Estimate cost for a single completion, given exact token counts."""
    catalog = CatalogService()
    total_cost = catalog.estimate_cost(model_id, prompt_tokens, completion_tokens)

    # Get individual costs
    pricing = catalog.get_model_pricing(model_id)
    from ..estimation_config import FALLBACK_PROMPT_PRICE_PER_1K, FALLBACK_COMPLETION_PRICE_PER_1K
    prompt_unit = pricing["prompt_price"] if pricing["prompt_price"] is not None else FALLBACK_PROMPT_PRICE_PER_1K
    completion_unit = pricing["completion_price"] if pricing["completion_price"] is not None else FALLBACK_COMPLETION_PRICE_PER_1K
    prompt_cost = float(prompt_tokens) * prompt_unit / 1000
    completion_cost = float(completion_tokens) * completion_unit / 1000

    # Round to 8 decimal places to avoid float precision issues with serializer validation
    return {
        "model_id": model_id,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "prompt_cost": round(prompt_cost, 8),
        "completion_cost": round(completion_cost, 8),
        "total_cost": round(float(total_cost), 8),
        "currency": "USD",
    }


def estimate_batch_cost(data: dict) -> dict:
    """Estimate cost for multiple models from validated request data.

    Prefers `typed_text` + `files_text` for accurate estimation. Falls
    back to `prompt_text` + optional `estimated_completion_tokens` for
    backward compatibility.
    """
    from ..estimation_config import (
        CHARS_PER_TOKEN,
        SAFETY_COMPLETION_RESERVE,
        DEFAULT_MAX_TOKENS_FALLBACK,
        ALPHA_T_DEFAULT,
        BETA_T_DEFAULT,
        ABS_COMPLETION_CAP,
        LINEAR_P_CAP,
        SUMMARIZATION_FILE_BOOST_PER_FILE,
        SUMMARIZATION_FILE_BOOST_MAX_FILES,
        SUMMARIZATION_PROMPT_PERCENT_BOOST,
        KEYWORD_SCALE_PER_HIT,
        KEYWORD_SCALE_MAX,
        IMAGE_PROMPT_BASE_TOKENS,
        IMAGE_PROMPT_TOKENS_PER_MB,
        IMAGE_PROMPT_TOKENS_PER_MP,
        IMAGE_PROMPT_TOKENS_CAP_PER_IMAGE,
        IMAGE_MAX_COUNT,
        IMAGE_LINEAR_WEIGHT,
    )

    # Token estimation helpers (approximate: ~4 chars per token)
    def approx_tokens(s: str) -> int:
        return max(0, len(s) // CHARS_PER_TOKEN)

    typed_text = data.get("typed_text") or ""
    files_text = data.get("files_text") or ""
    base_system_prompt = data.get("system_prompt") or ""
    images_meta = data.get("images") or []
    has_breakdown = bool(typed_text or files_text)
    files_meta = data.get("files") or []
    features_by_model = data.get("features_by_model") or {}

    # Build complete system prompt with all enabled features (global fallback)
    global_system_prompt = estimate_system_prompt(
        base_system_prompt if base_system_prompt else None, data
    )
    # Choose alpha/beta: request override > task-derived > defaults
    alpha_override = data.get("alpha")
    beta_override = data.get("beta")
    if alpha_override is not None and beta_override is not None:
        alpha = float(alpha_override)
        beta = float(beta_override)
    else:
        try:
            from ..prompt_classifier import predict_prompt_type, get_task_coefficients
            task_info = predict_prompt_type(typed_text, files_meta)
            primary = task_info.get('task_primary') or 'explanation'
            alpha, beta = get_task_coefficients(primary)
            # Special case: files-only (no typed text) → summarization-like output
            if task_info.get('signals', {}).get('has_files') and not task_info.get('signals', {}).get('has_text'):
                alpha, beta = get_task_coefficients('summarization')
            # Scale coefficients by keyword intensity for the primary task
            kw_scores = task_info.get('signals', {}).get('keyword_scores', {}) or {}
            kw_primary = int(kw_scores.get(primary, 0))
            if kw_primary > 0:
                scale = 1.0 + min(kw_primary * KEYWORD_SCALE_PER_HIT, KEYWORD_SCALE_MAX - 1.0)
                alpha *= scale
                beta *= scale
            # Keep task_info around for later summarization boosts
            task_primary = primary
            task_detection = task_info
        except Exception:
            alpha = ALPHA_T_DEFAULT
            beta = BETA_T_DEFAULT
            task_primary = 'explanation'
            task_detection = None
    margin_override = data.get("margin")
    margin = margin_override if margin_override is not None else SAFETY_COMPLETION_RESERVE

    # Compute prompt tokens P
    def image_tokens(images) -> int:
        total = 0
        count = 0
        for img in images or []:
            if count >= IMAGE_MAX_COUNT:
                break
            size = img.get('size') or 0
            width = img.get('width')
            height = img.get('height')
            # Prefer megapixels if dimensions are provided
            if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
                mp = (width * height) / 1_000_000.0
                t = IMAGE_PROMPT_BASE_TOKENS + int(IMAGE_PROMPT_TOKENS_PER_MP * mp)
            else:
                mb = float(size) / (1024.0 * 1024.0)
                t = IMAGE_PROMPT_BASE_TOKENS + int(IMAGE_PROMPT_TOKENS_PER_MB * mb)
            t = min(t, IMAGE_PROMPT_TOKENS_CAP_PER_IMAGE)
            total += max(0, t)
            count += 1
        return total

    # Calculate base token counts (without system prompt)
    if has_breakdown:
        typed_tokens = approx_tokens(typed_text)
        file_tokens = approx_tokens(files_text)
        img_tokens = image_tokens(images_meta)
    else:
        prompt_text = data.get("prompt_text") or ""
        # If client sent only prompt_text, we cannot distinguish files/images; treat all as text
        base_prompt_tokens = max(1, len(prompt_text) // CHARS_PER_TOKEN)

    # Helper: Calculate file tools tokens (LangChain adds tool descriptions to prompt)
    def calc_file_tools_tokens() -> int:
        """Estimate tokens added by FILE_TOOLS descriptions in LangChain"""
        try:
            from ..agent_tool_handlers import FILE_TOOLS
            # Each tool has name + description + args schema
            # Rough estimate: ~60-100 tokens per tool
            return len(FILE_TOOLS) * 80  # Conservative estimate
        except Exception:
            return 0

    # Helper function to calculate prompt tokens for a given system prompt
    def calc_prompt_tokens(sys_prompt: str, include_file_tools: bool = False) -> int:
        system_tokens = approx_tokens(sys_prompt)
        # Add file tools overhead if enabled (LangChain adds tool descriptions)
        if include_file_tools:
            system_tokens += calc_file_tools_tokens()
        if has_breakdown:
            return typed_tokens + file_tokens + img_tokens + system_tokens
        else:
            return base_prompt_tokens + system_tokens

    # Calculate global prompt tokens (used for models without specific features)
    global_prompt_tokens = calc_prompt_tokens(global_system_prompt)

    # Base completion from alpha + beta·min(P, LINEAR_P_CAP) (lower bounded at 0)
    # Linear term uses a reduced image contribution to avoid inflating expected output
    if has_breakdown:
        P_linear_raw = typed_tokens + file_tokens + int(img_tokens * IMAGE_LINEAR_WEIGHT)
    else:
        P_linear_raw = base_prompt_tokens
    P_eff = min(P_linear_raw, LINEAR_P_CAP)
    base_completion_linear = max(0, int(alpha + beta * P_eff))
    # Additional boosts for summarization based on number of files and prompt size
    try:
        file_count = len(files_meta)
    except Exception:
        file_count = 0
    if file_count > 0 and (locals().get('task_primary') == 'summarization'):
        file_boost = SUMMARIZATION_FILE_BOOST_PER_FILE * min(file_count, SUMMARIZATION_FILE_BOOST_MAX_FILES)
        tokens_boost = int(SUMMARIZATION_PROMPT_PERCENT_BOOST * P_eff)
        base_completion_linear += file_boost + tokens_boost
    # Deprecated override
    deprecated_override = data.get("estimated_completion_tokens")

    catalog = CatalogService()

    # Compute costs per model with per-model capacity using Ĉ(P) = min(M, W − P − margin, max(0, α + β·P))
    costs: List[Dict[str, Any]] = []
    total_cost = 0.0
    per_model_estimates = []
    per_model_prompt_tokens = {}  # Track prompt tokens per model

    for model_id in data["model_ids"]:
        try:
            model_info = catalog.get_model(model_id)
            if not model_info:
                continue
            max_tokens = model_info.get("max_tokens") or DEFAULT_MAX_TOKENS_FALLBACK

            # Calculate model-specific prompt tokens if features_by_model is provided
            if model_id in features_by_model:
                model_features = features_by_model[model_id]
                has_file_tools = model_features.get("enable_file_tools", False)
                model_system_prompt = estimate_system_prompt(
                    model_features.get("system_prompt") or base_system_prompt or None,
                    model_features,
                )
                model_prompt_tokens = calc_prompt_tokens(model_system_prompt, include_file_tools=has_file_tools)
            else:
                # Use global prompt tokens for this model
                model_prompt_tokens = global_prompt_tokens

            per_model_prompt_tokens[model_id] = model_prompt_tokens

            # M from per-model override > request > model property
            per_model = (data.get("max_new_tokens_by_model") or {}).get(model_id)
            req_max_new = data.get("max_new_tokens")
            model_max_new = model_info.get("max_completion_tokens") or (max_tokens - margin)
            if per_model is not None:
                M = int(per_model)
            elif req_max_new is not None:
                M = int(req_max_new)
            else:
                M = int(model_max_new)
            # Apply absolute cap to M
            M = min(M, ABS_COMPLETION_CAP)
            # Compute Ĉ(P) using model-specific prompt tokens
            capacity = max(0, max_tokens - model_prompt_tokens - margin)
            c_hat = min(M, capacity, base_completion_linear) if deprecated_override is None else min(M, capacity, int(deprecated_override))
            per_model_estimates.append(max(0, int(c_hat)))

            # Clamp prompt for cost computation to respect total window with chosen completion
            effective_prompt = max(0, min(model_prompt_tokens, max_tokens - margin - c_hat))
            cost = catalog.estimate_cost(model_id, effective_prompt, int(c_hat))
            # Round to 8 decimal places to avoid float precision issues with serializer validation
            cost_rounded = round(float(cost), 8)
            costs.append({
                "model_id": model_id,
                "model_name": model_info.get("name", model_id),
                "cost": cost_rounded,
                "prompt_tokens": model_prompt_tokens,
                "completion_tokens": int(c_hat),
            })
            total_cost += cost_rounded
            logger.debug(f"Estimated cost for {model_id}: ${cost_rounded:.6f}")
        except Exception as e:
            logger.warning(f"Failed to estimate cost for {model_id}: {e}")
            continue

    # Report representative estimates across models (median of per-model values)
    if per_model_estimates:
        sorted_est = sorted(per_model_estimates)
        mid = len(sorted_est) // 2
        if len(sorted_est) % 2 == 1:
            reported_completion = sorted_est[mid]
        else:
            reported_completion = int((sorted_est[mid - 1] + sorted_est[mid]) / 2)
    else:
        reported_completion = base_completion_linear

    # Report median prompt tokens across models (since they can differ now)
    if per_model_prompt_tokens:
        sorted_prompts = sorted(per_model_prompt_tokens.values())
        mid = len(sorted_prompts) // 2
        if len(sorted_prompts) % 2 == 1:
            reported_prompt_tokens = sorted_prompts[mid]
        else:
            reported_prompt_tokens = int((sorted_prompts[mid - 1] + sorted_prompts[mid]) / 2)
    else:
        reported_prompt_tokens = global_prompt_tokens

    # Round total_cost to avoid float precision issues with serializer validation
    total_cost_rounded = round(total_cost, 8)

    response_data = {
        "costs": costs,
        "total_cost": total_cost_rounded,
        "prompt_tokens": reported_prompt_tokens,
        "completion_tokens": int(reported_completion),
    }

    return response_data
