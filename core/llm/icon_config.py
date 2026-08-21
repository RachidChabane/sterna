"""
Configuration for provider icons using LobeHub icons library.
"""

# CDN base URL for LobeHub static icons.
# This is an optional, CDN-served asset (MIT-licensed: github.com/lobehub/lobe-icons).
# Version is pinned (not @latest) so a rare-provider icon load can never regress
# unexpectedly; the frontend has a graceful fallback (generic icon) if the CDN
# is unreachable or a slug is missing, so this dependency is not load-bearing.
LOBEHUB_ICONS_STATIC_PNG_VERSION = "1.95.0"
LOBEHUB_ICONS_STATIC_SVG_VERSION = "1.94.0"
LOBEHUB_ICONS_STATIC_WEBP_VERSION = "1.93.0"
LOBEHUB_CDN_BASE = f"https://unpkg.com/@lobehub/icons-static-png@{LOBEHUB_ICONS_STATIC_PNG_VERSION}"
LOBEHUB_CDN_BASE_SVG = f"https://unpkg.com/@lobehub/icons-static-svg@{LOBEHUB_ICONS_STATIC_SVG_VERSION}"
LOBEHUB_CDN_BASE_WEBP = f"https://unpkg.com/@lobehub/icons-static-webp@{LOBEHUB_ICONS_STATIC_WEBP_VERSION}"

# Provider name mappings for special cases
# Format: OpenRouter provider name -> icon slug for frontend registry
# These slugs must match keys in frontend PROVIDER_ICON_COMPONENTS
PROVIDER_ICON_MAPPINGS = {
    # Direct mappings (most providers use their exact name)
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google",
    "microsoft": "microsoft",
    "meta": "meta",
    "cohere": "cohere",
    "mistral": "mistral",
    "perplexity": "perplexity",
    "together": "together",  # Maps to frontend 'together-ai' key which uses Together component
    "groq": "groq",
    "aws": "aws",  # Maps to frontend 'aws-bedrock' key which uses Aws component
    "azure": "azure",
    "huggingface": "huggingface",  # Maps to frontend 'hugging-face' key
    "deepseek": "deepseek",
    "baichuan": "baichuan",
    "qwen": "qwen",
    "zai": "zai",
    "glmv": "glmv",
    "nvidia": "nvidia",
    "ai21": "ai21",
    "aion-labs": "aionlabs",
    "baidu": "baidu",
    "inflection": "inflection",
    "liquid": "liquid",
    "minimax": "minimax",
    "moonshotai": "moonshot",
    "nousresearch": "nousresearch",
    "tencent": "tencent",

    # Providers using HuggingFace icon
    "agentica-org": "huggingface",
    "alfredpros": "huggingface",
    "alpindale": "huggingface",
    "anthracite-org": "huggingface",
    "arliai": "huggingface",
    "bytedance": "huggingface",
    "cognitivecomputations": "huggingface",
    "eleutherai": "huggingface",
    "gryphe": "huggingface",
    "inclusionai": "huggingface",
    "mancer": "huggingface",
    "meituan": "huggingface",
    "neversleep": "huggingface",
    "opengvlab": "huggingface",
    "raifle": "huggingface",
    "sao10k": "huggingface",
    "shisa-ai": "huggingface",
    "stepfun-ai": "huggingface",
    "thudm": "huggingface",
    "tngtech": "huggingface",
    "undi95": "huggingface",

    # Special cases that need transformation
    "meta-llama": "meta",  # Maps to frontend 'meta-llama' key which uses Meta component
    "mistralai": "mistral",
    "amazon": "aws",  # Amazon models use AWS icon
    "google-vertex": "vertexai",  # Maps to frontend 'vertex-ai' key which uses VertexAI component
    "alibaba": "alibabacloud",  # Maps to frontend 'alibaba-cloud' key which uses AlibabaCloud component
    "deepmind": "google",  # DeepMind is part of Google
    "x-ai": "xai",
    "01-ai": "yi",
    "zhipu": "chatglm",
    "z.ai": "zai",
    "z-ai": "zai",
    "glm-v": "glmv",
    "ornithops": "ornithops",
}

# List of known LobeHub icon slugs for validation
# This list includes the most common AI/LLM providers
# These slugs correspond to actual React component exports from @lobehub/icons
KNOWN_LOBEHUB_ICONS = {
    "openai",
    "anthropic",
    "google",
    "microsoft",
    "meta",
    "cohere",
    "mistral",
    "perplexity",
    "together",  # React export is "Together", not "TogetherAI"
    "groq",
    "aws",
    "azure",
    "deepseek",
    "baichuan",
    "xai",
    "yi",
    "chatglm",
    "claude",
    "gemini",
    "nova",
    "qwen",
    "huggingface",
    "alibabacloud",
    "vertexai",
    "zai",
    "glmv",
    "nvidia",
    "ai21",
    "aionlabs",
    "baidu",
    "inflection",
    "liquid",
    "minimax",
    "moonshot",
    "nousresearch",
    "tencent",
    "ornithops",
    "sterna",
}
