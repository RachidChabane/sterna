"""
Models for LLM module.
"""

import uuid
from decimal import Decimal

from django.db import models
from django.conf import settings


class ModelCatalog(models.Model):
    """Cache of available models from OpenRouter."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_id = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    provider = models.CharField(max_length=100)

    # Pricing (stored as per 1K tokens, exposed as per 1M tokens via API)
    prompt_price = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Price per 1K prompt tokens (internal storage)",
    )
    completion_price = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Price per 1K completion tokens (internal storage)",
    )

    # Capabilities
    max_tokens = models.IntegerField(null=True, blank=True)
    supports_streaming = models.BooleanField(default=True)
    supports_functions = models.BooleanField(default=False)
    supports_structured_outputs = models.BooleanField(default=False)
    supports_reasoning = models.BooleanField(default=False)
    supports_prompt_caching = models.BooleanField(default=False)
    supports_stream_cancellation = models.BooleanField(default=False)

    # Architecture details
    modality = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Model modality (e.g., 'text->text', 'text+image->text')",
    )
    input_modalities = models.JSONField(
        default=list,
        blank=True,
        help_text="List of supported input modalities (e.g., ['text', 'image'])",
    )
    output_modalities = models.JSONField(
        default=list,
        blank=True,
        help_text="List of supported output modalities (e.g., ['text'])",
    )
    tokenizer = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Tokenizer type (e.g., 'Llama3', 'Gemini')",
    )

    # Top provider details
    max_completion_tokens = models.IntegerField(
        null=True,
        blank=True,
        help_text="Maximum completion tokens from top provider",
    )
    is_moderated = models.BooleanField(
        default=False,
        help_text="Whether content moderation is enabled by top provider",
    )

    # Default parameters
    default_parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text="Default generation parameters (temperature, top_p, etc.)",
    )

    # Performance stats (from OpenRouter)
    latency_p50 = models.IntegerField(
        null=True,
        blank=True,
        help_text="Median latency (time-to-first-token) in milliseconds",
    )
    latency_p90 = models.IntegerField(
        null=True,
        blank=True,
        help_text="90th percentile latency in milliseconds",
    )
    throughput_p50 = models.FloatField(
        null=True,
        blank=True,
        help_text="Median throughput in tokens per second",
    )
    throughput_p90 = models.FloatField(
        null=True,
        blank=True,
        help_text="90th percentile throughput in tokens per second",
    )
    stats_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When performance stats were last updated",
    )

    # Metadata
    description = models.TextField(blank=True)
    tags = models.JSONField(default=list, blank=True)
    is_available = models.BooleanField(default=True)

    # Timestamps
    first_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this model was first seen in OpenRouter catalog"
    )
    fetched_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_new(self) -> bool:
        """Check if model was first seen within the last 48 hours."""
        from django.utils import timezone
        from datetime import timedelta
        if not self.first_seen_at:
            return False
        return timezone.now() - self.first_seen_at < timedelta(hours=48)

    class Meta:
        ordering = ["provider", "name"]
        indexes = [
            models.Index(fields=["provider"]),
            models.Index(fields=["is_available"]),
        ]

    def __str__(self):
        return f"{self.provider}/{self.name}"


class ImageModelCatalog(models.Model):
    """Catalog of available image generation models."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model_id = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique identifier (e.g., 'openai/dall-e-3', 'bfl/flux-1.1-pro')"
    )
    name = models.CharField(max_length=255, help_text="Display name")
    provider = models.CharField(max_length=100, help_text="Provider name (openai, bfl, stability, etc.)")

    # Pricing
    price_per_image = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Base price per generated image in USD"
    )
    price_per_megapixel = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Price per megapixel (for resolution-based pricing)"
    )

    # Capabilities
    supports_generation = models.BooleanField(
        default=True,
        help_text="Whether model supports image generation from text"
    )
    supports_editing = models.BooleanField(
        default=False,
        help_text="Whether model supports image editing/inpainting"
    )
    supports_variations = models.BooleanField(
        default=False,
        help_text="Whether model supports creating image variations"
    )
    supports_outpainting = models.BooleanField(
        default=False,
        help_text="Whether model supports outpainting/extending images"
    )
    supports_upscaling = models.BooleanField(
        default=False,
        help_text="Whether model supports image upscaling"
    )

    # Supported sizes and aspect ratios
    supported_sizes = models.JSONField(
        default=list,
        blank=True,
        help_text="List of supported image sizes (e.g., ['1024x1024', '1792x1024'])"
    )
    supported_aspect_ratios = models.JSONField(
        default=list,
        blank=True,
        help_text="List of supported aspect ratios (e.g., ['1:1', '16:9', '9:16'])"
    )
    max_resolution = models.IntegerField(
        null=True,
        blank=True,
        help_text="Maximum resolution in pixels (width * height)"
    )

    # Quality options
    supported_qualities = models.JSONField(
        default=list,
        blank=True,
        help_text="List of quality options (e.g., ['standard', 'hd'])"
    )

    # Style options
    supported_styles = models.JSONField(
        default=list,
        blank=True,
        help_text="List of style presets (e.g., ['vivid', 'natural'])"
    )

    # Generation limits
    max_images_per_request = models.IntegerField(
        default=1,
        help_text="Maximum number of images per request"
    )
    max_prompt_length = models.IntegerField(
        null=True,
        blank=True,
        help_text="Maximum prompt length in characters"
    )

    # Performance characteristics
    typical_generation_time_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="Typical generation time in milliseconds"
    )
    is_fast = models.BooleanField(
        default=False,
        help_text="Whether this is a fast/turbo model variant"
    )

    # Special capabilities
    best_for_text = models.BooleanField(
        default=False,
        help_text="Whether model excels at rendering text in images"
    )
    best_for_photorealism = models.BooleanField(
        default=False,
        help_text="Whether model excels at photorealistic images"
    )
    best_for_illustration = models.BooleanField(
        default=False,
        help_text="Whether model excels at illustrations/art"
    )

    # Metadata
    description = models.TextField(blank=True)
    tags = models.JSONField(default=list, blank=True)
    is_available = models.BooleanField(default=True)

    # Timestamps
    first_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this model was first added to the catalog"
    )
    fetched_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_new(self) -> bool:
        """Check if model was first seen within the last 48 hours."""
        from django.utils import timezone
        from datetime import timedelta
        if not self.first_seen_at:
            return False
        return timezone.now() - self.first_seen_at < timedelta(hours=48)

    class Meta:
        ordering = ["provider", "name"]
        verbose_name = "Image Model"
        verbose_name_plural = "Image Models"
        indexes = [
            models.Index(fields=["provider"]),
            models.Index(fields=["is_available"]),
        ]

    def __str__(self):
        return f"{self.provider}/{self.name}"


class VideoInputType(models.TextChoices):
    """Types of input a video model can accept."""
    TEXT = 'text', 'Text Only'
    IMAGE = 'image', 'Image Required'
    VIDEO = 'video', 'Video Required'
    IMAGE_VIDEO = 'image_video', 'Image or Video'
    TEXT_IMAGE = 'text_image', 'Text + Optional Image'
    IMAGE_AUDIO = 'image_audio', 'Image + Audio'


class VideoOutputType(models.TextChoices):
    """Types of output a video model produces."""
    VIDEO = 'video', 'Generated Video'
    UPSCALED_VIDEO = 'upscaled', 'Upscaled Video'


class VideoModelCatalog(models.Model):
    """
    Catalog of available video generation models.

    This is the SINGLE SOURCE OF TRUTH for all video generation model configuration.
    Replaces hardcoded VideoModelConfig in constants.py.

    Supports multiple input types:
    - Text-to-video (veo3.1, veo3.1_fast, veo3, sora-2)
    - Image-to-video (gen4_turbo)
    - Image/Video-to-video (gen4_aleph)
    - Video upscaling (upscale_v1)
    - Character animation (act_two)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Identification
    model_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="API model identifier (e.g., 'veo3.1_fast', 'sora-2')"
    )
    canonical_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Full canonical ID with provider prefix (e.g., 'runway/veo3.1-fast')"
    )
    provider = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Provider name (e.g., 'runway', 'openai')"
    )

    # Display
    display_name = models.CharField(max_length=255, help_text="User-friendly display name")
    description = models.TextField(blank=True, help_text="Description of the model's capabilities")
    best_for = models.CharField(
        max_length=500,
        blank=True,
        help_text="Use case description (e.g., 'Quick iterations, social media clips')"
    )

    # Input/Output Types
    input_type = models.CharField(
        max_length=20,
        choices=VideoInputType.choices,
        default=VideoInputType.TEXT,
        db_index=True,
        help_text="Type of input the model requires"
    )
    output_type = models.CharField(
        max_length=20,
        choices=VideoOutputType.choices,
        default=VideoOutputType.VIDEO,
        help_text="Type of output the model produces"
    )

    # Capabilities (flexible JSON for provider-specific features)
    capabilities = models.JSONField(
        default=dict,
        blank=True,
        help_text="""Flexible capabilities dict. Expected structure:
        {
            "supports_audio": bool,
            "supports_lip_sync": bool,
            "min_duration": int,
            "max_duration": int,
            "valid_durations": [int],
            "supported_resolutions": ["720p", "1080p", "4K"],
            "supported_aspect_ratios": ["16:9", "9:16", "1:1"],
            "supported_fps": [24, 30, 60],
            "max_input_size_mb": int,
            "upscale_factor": int (for upscaling models),
            "supported_input_formats": ["jpeg", "png", "webp", "mp4"],
            "supported_audio_formats": ["mp3", "wav", "flac"],
            "output_format": "mp4"
        }"""
    )

    # Pricing (current prices for quick lookups)
    # Authoritative pricing history should use ServicePricing model
    current_price_per_second = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Current price per second of video in USD"
    )
    current_price_per_request = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Current price per request in USD (for non-duration-based pricing)"
    )

    # Status & Ordering
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this model is currently available for use"
    )
    is_pro = models.BooleanField(
        default=False,
        help_text="Whether this is a premium/pro tier model"
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Whether this is the default model for its input type"
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order (lower numbers shown first)"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'provider', 'display_name']
        verbose_name = 'Video Model'
        verbose_name_plural = 'Video Models'
        indexes = [
            models.Index(fields=['provider']),
            models.Index(fields=['is_active']),
            models.Index(fields=['input_type']),
            models.Index(fields=['sort_order']),
        ]

    def __str__(self):
        return f"{self.display_name} ({self.canonical_id})"

    # Convenience properties for common capability lookups
    @property
    def max_duration(self) -> int:
        """Maximum video duration in seconds."""
        return self.capabilities.get('max_duration', 10)

    @property
    def min_duration(self) -> int:
        """Minimum video duration in seconds."""
        return self.capabilities.get('min_duration', 4)

    @property
    def valid_durations(self) -> list:
        """List of valid duration values (if constrained)."""
        return self.capabilities.get('valid_durations', [])

    @property
    def supported_resolutions(self) -> list:
        """List of supported resolution names."""
        return self.capabilities.get('supported_resolutions', ['720p'])

    @property
    def supported_aspect_ratios(self) -> list:
        """List of supported aspect ratios."""
        return self.capabilities.get('supported_aspect_ratios', ['16:9', '9:16'])

    @property
    def supported_fps(self) -> list:
        """List of supported frame rates."""
        return self.capabilities.get('supported_fps', [24])

    @property
    def supports_audio(self) -> bool:
        """Whether model supports audio generation."""
        return self.capabilities.get('supports_audio', False)

    @property
    def max_input_size_mb(self) -> int:
        """Maximum input file size in MB."""
        return self.capabilities.get('max_input_size_mb', 16)

    @classmethod
    def get_active_models(cls, provider: str = None, input_type: str = None):
        """
        Get all active models, optionally filtered by provider or input type.

        Args:
            provider: Filter by provider name (e.g., 'runway', 'openai')
            input_type: Filter by input type (e.g., 'text', 'image')

        Returns:
            QuerySet of active VideoModelCatalog objects
        """
        qs = cls.objects.filter(is_active=True)
        if provider:
            qs = qs.filter(provider=provider)
        if input_type:
            qs = qs.filter(input_type=input_type)
        return qs.order_by('sort_order')

    @classmethod
    def get_by_canonical_id(cls, canonical_id: str):
        """
        Get model by canonical ID with caching.

        Args:
            canonical_id: Full canonical ID (e.g., 'runway/veo3.1-fast')

        Returns:
            VideoModelCatalog instance or None
        """
        from django.core.cache import cache
        cache_key = f"video_model:{canonical_id}"
        model = cache.get(cache_key)
        if model is None:
            model = cls.objects.filter(
                canonical_id=canonical_id,
                is_active=True
            ).first()
            if model:
                cache.set(cache_key, model, timeout=300)  # 5 min cache
        return model

    @classmethod
    def get_by_model_id(cls, model_id: str):
        """
        Get model by short model ID with caching.

        Args:
            model_id: Short model ID (e.g., 'veo3.1_fast')

        Returns:
            VideoModelCatalog instance or None
        """
        from django.core.cache import cache
        cache_key = f"video_model_short:{model_id}"
        model = cache.get(cache_key)
        if model is None:
            model = cls.objects.filter(
                model_id=model_id,
                is_active=True
            ).first()
            if model:
                cache.set(cache_key, model, timeout=300)  # 5 min cache
        return model

    @classmethod
    def get_default_model(cls, input_type: str = None):
        """
        Get the default model, optionally filtered by input type.

        Args:
            input_type: Filter by input type (defaults to 'text')

        Returns:
            VideoModelCatalog instance or None
        """
        qs = cls.objects.filter(is_active=True, is_default=True)
        if input_type:
            qs = qs.filter(input_type=input_type)
        return qs.first()

    @classmethod
    def get_default_for_input_type(cls, input_type: str):
        """
        Get the default model for a specific input type.

        First looks for a model marked as default, then falls back to
        the first active model with the lowest sort_order.

        Args:
            input_type: Input type value (e.g., 'text', 'image', 'video')

        Returns:
            VideoModelCatalog instance or None
        """
        # First try to find a default model for this input type
        model = cls.objects.filter(
            input_type=input_type,
            is_active=True,
            is_default=True,
        ).first()

        # Fall back to first active model by sort order
        if not model:
            model = cls.objects.filter(
                input_type=input_type,
                is_active=True,
            ).order_by('sort_order').first()

        return model

    @classmethod
    def invalidate_cache(cls, canonical_id: str = None, model_id: str = None):
        """Invalidate cache for a specific model or all models."""
        from django.core.cache import cache
        if canonical_id:
            cache.delete(f"video_model:{canonical_id}")
        if model_id:
            cache.delete(f"video_model_short:{model_id}")

    def calculate_cost(self, duration_seconds: float = None, request_count: int = 1) -> Decimal:
        """
        Calculate cost for a video generation operation.

        Args:
            duration_seconds: Video duration (for duration-based pricing)
            request_count: Number of requests (for per-request pricing)

        Returns:
            Cost in USD as Decimal
        """
        cost = Decimal('0')

        if self.current_price_per_second and duration_seconds:
            cost += self.current_price_per_second * Decimal(str(duration_seconds))

        if self.current_price_per_request:
            cost += self.current_price_per_request * Decimal(str(request_count))

        return cost


class OpenRouterGenerationRecord(models.Model):
    """
    Per-request OpenRouter provider analytics, keyed by user and model.

    Scope is analytics only: token counts, cost, and source breakdowns
    for OpenRouter generations. Billing of record lives in
    usage_quota.UsageLog; this model must never be read for quota or
    invoicing decisions.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='openrouter_generation_records',
        db_index=True,
    )

    # Request details
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    model_id = models.CharField(max_length=128, db_index=True)

    # Token usage
    prompt_tokens = models.IntegerField(default=0)
    completion_tokens = models.IntegerField(default=0)
    total_tokens = models.IntegerField(default=0)

    # Cost (in USD, stored as Decimal for precision)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)

    # Request metadata
    endpoint = models.CharField(max_length=64, default='chat/completions')
    request_source = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Where the request originated (e.g., 'chat', 'voice_room', 'mcp_discovery')",
    )

    # Optional: store request ID for debugging
    openrouter_request_id = models.CharField(max_length=128, blank=True, null=True)

    # Additional context
    extra_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional request metadata (project_id, etc.)",
    )

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'OpenRouter Generation Record'
        verbose_name_plural = 'OpenRouter Generation Records'
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['user', 'model_id']),
            models.Index(fields=['request_source', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.model_id} - {self.total_tokens} tokens"


class RoutingPool(models.Model):
    """Pool of models available for smart-router intelligent routing."""

    COST_TIER_CHOICES = [
        ('budget', 'Budget'),
        ('balanced', 'Balanced'),
        ('premium', 'Premium'),
    ]

    model = models.ForeignKey(
        ModelCatalog,
        on_delete=models.CASCADE,
        related_name='routing_pool_entries',
    )
    is_active = models.BooleanField(default=True)
    cost_tier = models.CharField(max_length=20, choices=COST_TIER_CHOICES)
    min_complexity_score = models.IntegerField(
        default=0,
        help_text="Minimum complexity score (0-100) for this model",
    )
    max_complexity_score = models.IntegerField(
        default=100,
        help_text="Maximum complexity score (0-100) for this model",
    )
    priority = models.IntegerField(
        default=0,
        help_text="Tiebreaker within same cost tier (higher = preferred)",
    )

    class Meta:
        ordering = ['cost_tier', 'priority']
        indexes = [
            models.Index(fields=['is_active', 'cost_tier']),
        ]
        verbose_name = 'Routing Pool Entry'
        verbose_name_plural = 'Routing Pool'

    def __str__(self):
        return f"{self.model.model_id} [{self.cost_tier}] ({self.min_complexity_score}-{self.max_complexity_score})"


class RoutingConversationScore(models.Model):
    """Tracks running complexity score per conversation for smart-router routing."""

    conversation_id = models.CharField(max_length=255, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='routing_conversation_scores',
    )
    current_score = models.IntegerField(default=0)
    max_score = models.IntegerField(default=0)
    turn_count = models.IntegerField(default=0)
    last_model_id = models.CharField(max_length=255, null=True, blank=True)
    consecutive_simple_turns = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('conversation_id', 'user')]
        verbose_name = 'Routing Conversation Score'
        verbose_name_plural = 'Routing Conversation Scores'

    def __str__(self):
        return f"Conv {self.conversation_id} score={self.current_score} turns={self.turn_count}"


class RoutingLog(models.Model):
    """Logs smart-router routing decisions for analytics and debugging."""

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='routing_logs',
    )
    conversation_id = models.CharField(max_length=255)
    tier_used = models.IntegerField(help_text="1 = heuristic only, 2 = LLM classification")
    heuristic_score = models.IntegerField()
    llm_score = models.IntegerField(null=True, blank=True)
    final_score = models.IntegerField()
    resolved_model_id = models.CharField(max_length=255)
    prompt_length = models.IntegerField()
    has_images = models.BooleanField(default=False)
    has_code = models.BooleanField(default=False)
    classification_cost_usd = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True,
    )
    classification_latency_ms = models.IntegerField(null=True, blank=True)
    is_reroute = models.BooleanField(default=False)
    rerouted_from_model = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Routing Log'
        verbose_name_plural = 'Routing Logs'

    def __str__(self):
        return f"[{self.timestamp}] score={self.final_score} -> {self.resolved_model_id}"
