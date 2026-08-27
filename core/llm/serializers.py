"""
Serializers for LLM module API endpoints.
"""

from rest_framework import serializers

from .models import ModelCatalog, ImageModelCatalog
from .pricing_config import convert_to_display_unit
from .icon_utils import (
    get_provider_icon_slug,
    get_provider_icon_url,
    get_model_icon_slug,
)


class ModelCatalogSerializer(serializers.ModelSerializer):
    """Serializer for model catalog entries."""

    cost_per_1m_prompt = serializers.SerializerMethodField()
    cost_per_1m_completion = serializers.SerializerMethodField()
    provider_icon_slug = serializers.SerializerMethodField()
    provider_icon_url = serializers.SerializerMethodField()
    model_icon_slug = serializers.SerializerMethodField()
    model_icon_url = serializers.SerializerMethodField()
    is_new = serializers.SerializerMethodField()

    def get_cost_per_1m_prompt(self, obj):
        """Convert price from storage unit to display unit."""
        return convert_to_display_unit(obj.prompt_price)

    def get_cost_per_1m_completion(self, obj):
        """Convert price from storage unit to display unit."""
        return convert_to_display_unit(obj.completion_price)

    def get_provider_icon_slug(self, obj):
        """
        Get the LobeHub icon slug for the provider.

        Returns None if provider has no icon mapping (frontend will use Building2 icon).
        """
        return get_provider_icon_slug(obj.provider)

    def get_provider_icon_url(self, obj):
        """
        Get the CDN URL for the provider icon.

        Returns None if provider has no icon mapping.
        """
        return get_provider_icon_url(obj.provider, size="dark", format="png")

    def get_model_icon_slug(self, obj):
        """
        Get the LobeHub icon slug for the model.

        Returns model-specific icon if available (e.g., "claude" for Claude models),
        otherwise falls back to provider icon (e.g., "anthropic").
        Returns None if no icon mapping found (frontend will use Package icon).
        """
        # Pass both model_id and name for better pattern matching (e.g., GLM-V detection)
        model_slug = get_model_icon_slug(obj.model_id, obj.name)
        if model_slug:
            return model_slug
        return get_provider_icon_slug(obj.provider)

    def get_model_icon_url(self, obj):
        """
        Get the CDN URL for the model icon.

        Returns CDN URL for model-specific icon if available,
        otherwise returns provider icon URL.
        Returns None if no icon mapping found.
        """
        slug = self.get_model_icon_slug(obj)
        if not slug:
            return None
        return get_provider_icon_url(slug, size="dark", format="png")

    def get_is_new(self, obj):
        """Check if model was first seen within the last 48 hours."""
        return obj.is_new

    class Meta:
        model = ModelCatalog
        fields = [
            "id",
            "model_id",
            "name",
            "provider",
            "provider_icon_slug",
            "provider_icon_url",
            "model_icon_slug",
            "model_icon_url",
            "cost_per_1m_prompt",
            "cost_per_1m_completion",
            "max_tokens",
            "supports_streaming",
            "supports_functions",
            "supports_structured_outputs",
            "supports_reasoning",
            "supports_prompt_caching",
            "supports_stream_cancellation",
            "modality",
            "input_modalities",
            "output_modalities",
            "tokenizer",
            "max_completion_tokens",
            "is_moderated",
            "default_parameters",
            "description",
            "tags",
            "is_available",
            "is_new",
            "first_seen_at",
            "fetched_at",
            # Performance stats
            "latency_p50",
            "latency_p90",
            "throughput_p50",
            "throughput_p90",
            "stats_updated_at",
        ]
        read_only_fields = ["id", "first_seen_at", "fetched_at", "stats_updated_at"]


class ModelAvailabilitySerializer(serializers.Serializer):
    """Serializer for model availability check."""

    model_id = serializers.CharField(required=True)
    is_available = serializers.BooleanField(read_only=True)
    provider = serializers.CharField(read_only=True)
    max_tokens = serializers.IntegerField(read_only=True)
    pricing = serializers.DictField(read_only=True)


class CompletionRequestSerializer(serializers.Serializer):
    """Serializer for completion requests."""

    model = serializers.CharField(required=True)
    messages = serializers.ListField(child=serializers.DictField(), required=True)
    temperature = serializers.FloatField(min_value=0, max_value=2, default=0.7)
    max_tokens = serializers.IntegerField(min_value=1, max_value=100000, default=1000)
    top_p = serializers.FloatField(min_value=0, max_value=1, default=1.0)
    stream = serializers.BooleanField(default=False)
    project_id = serializers.UUIDField(required=False, allow_null=True)

    # Additional sampling parameters
    top_k = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    frequency_penalty = serializers.FloatField(min_value=-2, max_value=2, required=False, allow_null=True)
    presence_penalty = serializers.FloatField(min_value=-2, max_value=2, required=False, allow_null=True)
    repetition_penalty = serializers.FloatField(min_value=0, max_value=2, required=False, allow_null=True)
    min_p = serializers.FloatField(min_value=0, max_value=1, required=False, allow_null=True)
    top_a = serializers.FloatField(min_value=0, max_value=1, required=False, allow_null=True)

    # Reasoning parameters (for models that support reasoning)
    enable_reasoning = serializers.BooleanField(
        default=False,
        required=False,
        help_text="Enable extended reasoning mode"
    )
    reasoning_effort = serializers.ChoiceField(
        choices=['low', 'medium', 'high'],
        required=False,
        allow_null=True,
        help_text="Reasoning effort level for effort-based models (OpenAI o-series, Grok)"
    )
    reasoning_max_tokens = serializers.IntegerField(
        min_value=1024,
        max_value=32000,
        required=False,
        allow_null=True,
        help_text="Maximum tokens for reasoning (for token-limited models: Anthropic, Gemini, Qwen)"
    )


    # Multimodal file processing parameters (OpenRouter plugins)
    plugins = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_null=True,
        help_text="List of OpenRouter plugins for file processing (e.g., [{'id': 'file-parser', 'pdf': {'engine': 'pdf-text'}}])"
    )

    # MCP Tools integration
    enable_mcp_tools = serializers.BooleanField(
        default=False,
        required=False,
        help_text="Enable MCP (Model Context Protocol) tools for function calling"
    )

    # Brave Search integration
    enable_brave_search = serializers.BooleanField(
        default=False,
        required=False,
        help_text="Enable Brave Search tools for advanced search (images, videos, places, news)"
    )

    # File Tools integration
    enable_file_tools = serializers.BooleanField(
        default=False,
        required=False,
        help_text="Enable file system tools for code editing and workspace management"
    )
    conversation_id = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Conversation ID for sandbox isolation"
    )
    chat_id = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Chat ID for finer sandbox isolation"
    )

    # Spark auto-fix integration
    spark_fix_request = serializers.DictField(
        required=False,
        allow_null=True,
        help_text="Spark fix request data: {spark_id, spark_title, error}"
    )

    # Sterna routing override
    sterna_strength = serializers.ChoiceField(
        choices=['strong'],
        required=False,
        allow_null=True,
        help_text="Force higher-tier model selection ('strong' = min score 70)"
    )


class CompletionResponseSerializer(serializers.Serializer):
    """Serializer for completion responses."""

    content = serializers.CharField()
    model = serializers.CharField()
    usage = serializers.DictField()
    cost = serializers.DecimalField(max_digits=15, decimal_places=8)
    prompt_cost = serializers.DecimalField(max_digits=15, decimal_places=8)
    completion_cost = serializers.DecimalField(max_digits=15, decimal_places=8)
    model_used = serializers.CharField(required=False)
    fallback_attempts = serializers.IntegerField(required=False)


class FallbackCompletionRequestSerializer(serializers.Serializer):
    """Serializer for completion with fallback."""

    models = serializers.ListField(
        child=serializers.CharField(), min_length=1, required=True
    )
    messages = serializers.ListField(child=serializers.DictField(), required=True)
    max_cost = serializers.FloatField(
        min_value=0,
        required=False,
        allow_null=True,
        help_text="Maximum cost limit in USD",
    )
    temperature = serializers.FloatField(min_value=0, max_value=2, default=0.7)
    max_tokens = serializers.IntegerField(min_value=1, max_value=100000, default=1000)
    top_p = serializers.FloatField(min_value=0, max_value=1, default=1.0)
    project_id = serializers.UUIDField(required=False, allow_null=True)

    # Additional sampling parameters
    top_k = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    frequency_penalty = serializers.FloatField(min_value=-2, max_value=2, required=False, allow_null=True)
    presence_penalty = serializers.FloatField(min_value=-2, max_value=2, required=False, allow_null=True)
    repetition_penalty = serializers.FloatField(min_value=0, max_value=2, required=False, allow_null=True)
    min_p = serializers.FloatField(min_value=0, max_value=1, required=False, allow_null=True)
    top_a = serializers.FloatField(min_value=0, max_value=1, required=False, allow_null=True)
    reasoning_effort = serializers.ChoiceField(
        choices=['low', 'medium', 'high'],
        required=False,
        allow_null=True
    )
    reasoning_max_tokens = serializers.IntegerField(
        min_value=1024,
        max_value=32000,
        required=False,
        allow_null=True
    )


class CostEstimateRequestSerializer(serializers.Serializer):
    """Serializer for cost estimation requests."""

    model_id = serializers.CharField(required=True)
    prompt_tokens = serializers.IntegerField(min_value=0, required=True)
    completion_tokens = serializers.IntegerField(min_value=0, required=True)


class CostEstimateResponseSerializer(serializers.Serializer):
    """Serializer for cost estimation responses."""

    model_id = serializers.CharField()
    prompt_tokens = serializers.IntegerField()
    completion_tokens = serializers.IntegerField()
    prompt_cost = serializers.DecimalField(max_digits=15, decimal_places=8)
    completion_cost = serializers.DecimalField(max_digits=15, decimal_places=8)
    total_cost = serializers.DecimalField(max_digits=15, decimal_places=8)
    currency = serializers.CharField(default="USD")


class RateLimitInfoSerializer(serializers.Serializer):
    """Serializer for rate limit information."""

    model_id = serializers.CharField()
    rate_per_second = serializers.FloatField()
    burst_capacity = serializers.IntegerField()
    current_tokens = serializers.FloatField()
    tokens_available = serializers.BooleanField()
    time_until_available = serializers.FloatField()


class CatalogRefreshResponseSerializer(serializers.Serializer):
    """Serializer for catalog refresh response."""

    success = serializers.BooleanField()
    total_models = serializers.IntegerField(required=False)
    providers = serializers.DictField(required=False)
    error = serializers.CharField(required=False)
    timestamp = serializers.DateTimeField()


class ModelTierSerializer(serializers.Serializer):
    """Serializer for model tier information."""

    tier = serializers.ChoiceField(choices=["budget", "balanced", "quality"])
    models = serializers.ListField(child=serializers.CharField())
    cost_estimate = serializers.FloatField()
    available_count = serializers.IntegerField()


class ModelFilterSerializer(serializers.Serializer):
    """Serializer for model filtering parameters."""

    search = serializers.CharField(required=False, help_text="Search term for model name or provider")
    provider = serializers.CharField(required=False)
    tier = serializers.ChoiceField(choices=['budget', 'balanced', 'quality'], required=False)
    tags = serializers.ListField(child=serializers.CharField(), required=False)
    available_only = serializers.BooleanField(default=True)
    min_context_length = serializers.IntegerField(min_value=0, required=False)
    supports_functions = serializers.BooleanField(required=False)
    supports_streaming = serializers.BooleanField(required=False)
    supports_structured_outputs = serializers.BooleanField(required=False)
    supports_reasoning = serializers.BooleanField(required=False)
    supports_prompt_caching = serializers.BooleanField(required=False)
    supports_stream_cancellation = serializers.BooleanField(required=False)
    input_modalities = serializers.CharField(required=False, help_text="Comma-separated list of input modalities (e.g., 'image,audio')")
    min_price = serializers.FloatField(min_value=0, required=False, help_text="Minimum price per 1M tokens")
    max_price = serializers.FloatField(min_value=0, required=False, help_text="Maximum price per 1M tokens")
    sort_by = serializers.ChoiceField(
        choices=['none', 'prompt_cost', 'completion_cost', 'overall_cost', 'max_tokens', 'provider', 'latency', 'throughput'],
        required=False,
        default='none',
        help_text="Field to sort by"
    )
    order = serializers.ChoiceField(
        choices=['asc', 'desc'],
        required=False,
        default='asc',
        help_text="Sort order (ascending or descending)"
    )
    has_icon = serializers.BooleanField(
        required=False,
        default=True,
        help_text="Filter to only show models with icons (default: True)"
    )

    def validate_input_modalities(self, value):
        """Convert comma-separated string to list of modalities."""
        if value:
            # Split by comma, strip whitespace, and filter empty strings
            return [m.strip() for m in value.split(',') if m.strip()]
        return []


class UsageStatsSerializer(serializers.Serializer):
    """Serializer for usage statistics."""

    period = serializers.CharField()
    total_requests = serializers.IntegerField()
    total_tokens = serializers.IntegerField()
    total_cost = serializers.DecimalField(max_digits=10, decimal_places=2)
    models_used = serializers.DictField()
    daily_breakdown = serializers.ListField(
        child=serializers.DictField(), required=False
    )


class BatchCostEstimateRequestSerializer(serializers.Serializer):
    """Serializer for batch cost estimation requests."""

    model_ids = serializers.ListField(
        child=serializers.CharField(),
        required=True,
        help_text="List of model IDs to estimate costs for"
    )
    prompt_text = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Deprecated: full prompt text. Use typed_text + files_text for better estimates."
    )
    typed_text = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Raw text typed by the user (used for weighted token estimation)"
    )
    files_text = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Concatenated text extracted from attached text/code files"
    )
    system_prompt = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Optional base system prompt to include in token estimation"
    )
    enable_mcp_tools = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Whether MCP tools are enabled (adds to system prompt)"
    )
    enable_reasoning = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Whether reasoning is enabled (adds to system prompt)"
    )
    enable_file_tools = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Whether file tools are enabled (adds to system prompt)"
    )
    features_by_model = serializers.DictField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
        help_text="Optional per-model features override: {model_id: {enable_mcp_tools, enable_reasoning, enable_file_tools, system_prompt}}"
    )
    files = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
        help_text="Optional file metadata list: [{filename, mime, size?}]"
    )
    images = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        allow_empty=True,
        help_text="Optional image metadata list: [{mime?, size?, width?, height?}]"
    )
    estimated_completion_tokens = serializers.IntegerField(
        min_value=0,
        required=False,
        help_text="Deprecated: Optional override for estimated completion tokens. Prefer alpha/beta/margin/max_new_tokens."
    )

    # Optional coefficients for completion estimation Ĉ(P) = min(M, W − P − margin, max(0, alpha + beta·P))
    alpha = serializers.FloatField(required=False, allow_null=True)
    beta = serializers.FloatField(required=False, allow_null=True)
    margin = serializers.IntegerField(required=False, allow_null=True)
    max_new_tokens = serializers.IntegerField(required=False, allow_null=True)
    max_new_tokens_by_model = serializers.DictField(
        child=serializers.IntegerField(min_value=0),
        required=False,
        allow_empty=True,
        help_text="Optional per-model override for max new tokens (e.g., { 'openai/gpt-4o': 2048 })"
    )


class ModelCostEstimateSerializer(serializers.Serializer):
    """Serializer for individual model cost estimate."""

    model_id = serializers.CharField()
    model_name = serializers.CharField()
    cost = serializers.DecimalField(max_digits=15, decimal_places=8)
    prompt_tokens = serializers.IntegerField()
    completion_tokens = serializers.IntegerField()


class BatchCostEstimateResponseSerializer(serializers.Serializer):
    """Serializer for batch cost estimation responses."""

    costs = ModelCostEstimateSerializer(many=True)
    total_cost = serializers.DecimalField(max_digits=15, decimal_places=8)
    prompt_tokens = serializers.IntegerField()
    completion_tokens = serializers.IntegerField()


class ComparisonPrioritiesSerializer(serializers.Serializer):
    # `context` here is a genuine JSON field name (ComparisonPriorities.context in
    # comparison_config.py) that happens to collide with DRF's own Field.context
    # property. DRF's SerializerMetaclass pops declared-field attributes out of the
    # class body at class-creation time (see rest_framework.serializers.
    # SerializerMetaclass._get_declared_fields), so this never actually shadows the
    # real property at runtime — mypy can't see that dynamic step.
    cost = serializers.ChoiceField(choices=["off", "nice", "important", "critical"], required=False)
    context = serializers.ChoiceField(choices=["off", "nice", "important", "critical"], required=False)  # type: ignore[assignment]
    capabilities = serializers.ChoiceField(choices=["off", "nice", "important", "critical"], required=False)
    multimodality = serializers.ChoiceField(choices=["off", "nice", "important", "critical"], required=False)
    availability = serializers.ChoiceField(choices=["off", "nice", "important", "critical"], required=False)


class ComparisonConstraintsSerializer(serializers.Serializer):
    mustSupportFunctions = serializers.BooleanField(required=False)
    mustSupportStructuredOutputs = serializers.BooleanField(required=False)
    mustSupportReasoning = serializers.BooleanField(required=False)
    mustSupportPromptCaching = serializers.BooleanField(required=False)
    mustSupportStreamCancellation = serializers.BooleanField(required=False)
    mustBeAvailable = serializers.BooleanField(required=False)
    mustBeMultimodal = serializers.BooleanField(required=False)
    minContextTokens = serializers.IntegerField(required=False, allow_null=True)
    maxCostPer1MTokens = serializers.FloatField(required=False, allow_null=True)


class CapabilityWeightsSerializer(serializers.Serializer):
    functions = serializers.FloatField(required=False)
    structured_outputs = serializers.FloatField(required=False)
    reasoning = serializers.FloatField(required=False)
    prompt_caching = serializers.FloatField(required=False)
    stream_cancellation = serializers.FloatField(required=False)


class ModelComparisonRequestSerializer(serializers.Serializer):
    model_ids = serializers.ListField(child=serializers.CharField(), min_length=1)
    priorities = ComparisonPrioritiesSerializer(required=False)
    constraints = ComparisonConstraintsSerializer(required=False)
    costDirection = serializers.ChoiceField(choices=["lower", "higher"], required=False)
    capabilityWeights = CapabilityWeightsSerializer(required=False)


class ScoreBreakdownSerializer(serializers.Serializer):
    cost = serializers.FloatField()
    context = serializers.FloatField()  # type: ignore[assignment]  # see ComparisonPrioritiesSerializer.context note
    capabilities = serializers.FloatField()
    multimodality = serializers.FloatField()
    availability = serializers.FloatField()


class ModelScoreSerializer(serializers.Serializer):
    model_id = serializers.CharField()
    id = serializers.CharField()
    score = serializers.FloatField()
    breakdown = ScoreBreakdownSerializer()


class ModelComparisonResponseSerializer(serializers.Serializer):
    scores = ModelScoreSerializer(many=True)
    best_model_id = serializers.CharField(allow_null=True)
    considered = serializers.IntegerField()


class ImageModelCatalogSerializer(serializers.ModelSerializer):
    """Serializer for image model catalog entries."""

    provider_icon_slug = serializers.SerializerMethodField()
    provider_icon_url = serializers.SerializerMethodField()
    model_icon_slug = serializers.SerializerMethodField()
    model_icon_url = serializers.SerializerMethodField()
    is_new = serializers.SerializerMethodField()

    def get_provider_icon_slug(self, obj):
        """Get the LobeHub icon slug for the provider."""
        return get_provider_icon_slug(obj.provider)

    def get_provider_icon_url(self, obj):
        """Get the CDN URL for the provider icon."""
        return get_provider_icon_url(obj.provider, size="dark", format="png")

    def get_model_icon_slug(self, obj):
        """Get the LobeHub icon slug for the model."""
        model_slug = get_model_icon_slug(obj.model_id, obj.name)
        if model_slug:
            return model_slug
        return get_provider_icon_slug(obj.provider)

    def get_model_icon_url(self, obj):
        """Get the CDN URL for the model icon."""
        slug = self.get_model_icon_slug(obj)
        if not slug:
            return None
        return get_provider_icon_url(slug, size="dark", format="png")

    def get_is_new(self, obj):
        """Check if model was first seen within the last 48 hours."""
        return obj.is_new

    class Meta:
        model = ImageModelCatalog
        fields = [
            "id",
            "model_id",
            "name",
            "provider",
            "provider_icon_slug",
            "provider_icon_url",
            "model_icon_slug",
            "model_icon_url",
            "price_per_image",
            "price_per_megapixel",
            "supports_generation",
            "supports_editing",
            "supports_variations",
            "supports_outpainting",
            "supports_upscaling",
            "supported_sizes",
            "supported_aspect_ratios",
            "max_resolution",
            "supported_qualities",
            "supported_styles",
            "max_images_per_request",
            "max_prompt_length",
            "typical_generation_time_ms",
            "is_fast",
            "best_for_text",
            "best_for_photorealism",
            "best_for_illustration",
            "description",
            "tags",
            "is_available",
            "is_new",
            "first_seen_at",
            "fetched_at",
        ]
        read_only_fields = ["id", "first_seen_at", "fetched_at"]


class ImageModelFilterSerializer(serializers.Serializer):
    """Serializer for image model filtering parameters."""

    search = serializers.CharField(required=False, help_text="Search term for model name or provider")
    provider = serializers.CharField(required=False)
    available_only = serializers.BooleanField(default=True)
    supports_editing = serializers.BooleanField(required=False)
    supports_variations = serializers.BooleanField(required=False)
    best_for_text = serializers.BooleanField(required=False)
    best_for_photorealism = serializers.BooleanField(required=False)
    is_fast = serializers.BooleanField(required=False)
    max_price = serializers.FloatField(min_value=0, required=False, help_text="Maximum price per image in USD")
    sort_by = serializers.ChoiceField(
        choices=['none', 'price', 'name', 'provider'],
        required=False,
        default='none',
        help_text="Field to sort by"
    )
    order = serializers.ChoiceField(
        choices=['asc', 'desc'],
        required=False,
        default='asc',
        help_text="Sort order (ascending or descending)"
    )


# =============================================================================
# Video Model Serializers
# =============================================================================


class VideoModelSerializer(serializers.Serializer):
    """Serializer for video generation model configuration."""

    model_id = serializers.CharField(help_text="Model identifier (e.g., 'sora-2')")
    canonical_id = serializers.CharField(help_text="Canonical ID with provider prefix")
    display_name = serializers.CharField(help_text="User-friendly model name")
    provider = serializers.CharField(help_text="Provider name (e.g., 'openai')")
    price_per_second_usd = serializers.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="Price per second of video in USD"
    )
    max_duration_seconds = serializers.IntegerField(help_text="Maximum video duration in seconds")
    is_pro = serializers.BooleanField(help_text="Whether this is a pro/premium model")
    supported_fps = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="Supported frame rates"
    )
    description = serializers.CharField(help_text="Model description", allow_blank=True)

    # Computed fields
    provider_icon_slug = serializers.SerializerMethodField()
    provider_icon_url = serializers.SerializerMethodField()

    def get_provider_icon_slug(self, obj):
        """Get the LobeHub icon slug for the provider."""
        return get_provider_icon_slug(obj.get("provider", "openai"))

    def get_provider_icon_url(self, obj):
        """Get the CDN URL for the provider icon."""
        return get_provider_icon_url(obj.get("provider", "openai"), size="dark", format="png")


class VideoModelConfigSerializer(serializers.Serializer):
    """
    Serializer for video generation configuration.

    Returns available models and supported options.
    """

    models = VideoModelSerializer(many=True)
    supported_aspect_ratios = serializers.ListField(
        child=serializers.CharField(),
        help_text="List of supported aspect ratios (e.g., '16:9', '9:16')"
    )
    default_aspect_ratio = serializers.CharField(help_text="Default aspect ratio")
    default_duration_seconds = serializers.IntegerField(help_text="Default video duration")
    default_model = serializers.CharField(help_text="Default model ID")
