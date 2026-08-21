"""
Serializers for Consigliere AI API endpoints.
"""

from rest_framework import serializers
from .models import (
    ConsiglierSession,
    ConversationAnalysis,
    ModelRecommendation,
    ConsigliereMessage,
)
from .config import ModelParametersDefaults as MPD
from llm.models import ModelCatalog
from llm.icon_utils import (
    get_provider_icon_slug,
    get_provider_icon_url,
    get_model_icon_slug,
)
from llm.icon_config import LOBEHUB_CDN_BASE
from llm.serializers import convert_to_display_unit


# ============================================================================
# Request Serializers
# ============================================================================


class AnalyzeConversationRequestSerializer(serializers.Serializer):
    """
    Request serializer for analyzing a conversation.
    """

    chat_group = serializers.JSONField(
        help_text="Full ChatGroup data from frontend"
    )
    current_model = serializers.CharField(
        max_length=255,
        help_text="Currently selected model in the app"
    )
    user_preferences = serializers.JSONField(
        required=False,
        default=dict,
        help_text="Optional user preferences (budget, priority)"
    )


class ChatMessageParametersSerializer(serializers.Serializer):
    """
    Parameters for Consigliere chat message.

    Default values are centralized in config.ModelParametersDefaults.
    """

    temperature = serializers.FloatField(required=False, default=MPD.TEMPERATURE)
    max_tokens = serializers.IntegerField(required=False, default=MPD.MAX_TOKENS)
    top_p = serializers.FloatField(required=False, default=MPD.TOP_P)
    top_k = serializers.IntegerField(required=False, default=MPD.TOP_K)
    frequency_penalty = serializers.FloatField(required=False, default=MPD.FREQUENCY_PENALTY)
    presence_penalty = serializers.FloatField(required=False, default=MPD.PRESENCE_PENALTY)
    repetition_penalty = serializers.FloatField(required=False, default=MPD.REPETITION_PENALTY)
    min_p = serializers.FloatField(required=False, default=MPD.MIN_P)
    top_a = serializers.FloatField(required=False, default=MPD.TOP_A)


class ChatMessageRequestSerializer(serializers.Serializer):
    """
    Request serializer for sending a message to Consigliere.
    """

    session_id = serializers.UUIDField(
        help_text="ID of the Consigliere session"
    )
    message = serializers.CharField(
        help_text="User's message to Consigliere"
    )
    current_model = serializers.CharField(
        max_length=255,
        help_text="Currently selected model (used for Consigliere's responses)"
    )
    stream = serializers.BooleanField(
        default=False,
        help_text="Enable streaming responses"
    )
    parameters = ChatMessageParametersSerializer(
        required=False,
        help_text="Optional model parameters for the response"
    )


class ContinueSessionRequestSerializer(serializers.Serializer):
    """
    Request serializer for continuing a previous session.
    """

    chat_group = serializers.JSONField(
        required=False,
        help_text="Updated ChatGroup data (optional)"
    )


# ============================================================================
# Response Serializers (Model Serializers)
# ============================================================================


class ConsigliereMessageSerializer(serializers.ModelSerializer):
    """
    Serializer for Consigliere messages.
    Enriches model information from ModelCatalog if available.
    """

    # Explicitly serialize DecimalField as float for frontend compatibility
    cost = serializers.FloatField(read_only=True)
    prompt_cost = serializers.FloatField(read_only=True)
    completion_cost = serializers.FloatField(read_only=True)

    # Enrich model information if not already set
    model_id = serializers.SerializerMethodField()
    provider = serializers.SerializerMethodField()
    model_icon_slug = serializers.SerializerMethodField()
    model_icon_url = serializers.SerializerMethodField()
    provider_icon_slug = serializers.SerializerMethodField()
    provider_icon_url = serializers.SerializerMethodField()

    class Meta:
        model = ConsigliereMessage
        fields = [
            "id",
            "role",
            "content",
            "model_used",
            "model_id",
            "provider",
            "model_icon_slug",
            "model_icon_url",
            "provider_icon_slug",
            "provider_icon_url",
            "tokens_used",
            "prompt_tokens",
            "completion_tokens",
            "cost",
            "prompt_cost",
            "completion_cost",
            "latency",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def _get_model_catalog(self, obj):
        """Helper to fetch model from catalog if model_used is available."""
        if not obj.model_used:
            return None

        if not hasattr(self, '_model_cache'):
            self._model_cache = {}

        if obj.model_used not in self._model_cache:
            try:
                # Try exact match with model_used
                self._model_cache[obj.model_used] = ModelCatalog.objects.get(model_id=obj.model_used)
            except ModelCatalog.DoesNotExist:
                try:
                    # Try case-insensitive match
                    self._model_cache[obj.model_used] = ModelCatalog.objects.get(model_id__iexact=obj.model_used)
                except ModelCatalog.DoesNotExist:
                    self._model_cache[obj.model_used] = None

        return self._model_cache[obj.model_used]

    def get_model_id(self, obj):
        """Get model_id from stored field or model_used."""
        if obj.model_id:
            return obj.model_id
        return obj.model_used if obj.model_used else None

    def get_provider(self, obj):
        """Get provider from stored field or extract from model_used."""
        if obj.provider:
            return obj.provider
        if obj.model_used and '/' in obj.model_used:
            return obj.model_used.split('/')[0]
        model = self._get_model_catalog(obj)
        return model.provider if model else None

    def get_model_icon_slug(self, obj):
        """Get model icon slug."""
        if obj.model_icon_slug:
            return obj.model_icon_slug
        model = self._get_model_catalog(obj)
        if model:
            return get_model_icon_slug(model.model_id, model.name)
        return None

    def get_model_icon_url(self, obj):
        """Get model icon URL."""
        if obj.model_icon_url:
            return obj.model_icon_url
        slug = self.get_model_icon_slug(obj)
        if slug:
            return f"{LOBEHUB_CDN_BASE}/dark/{slug}.png"
        return None

    def get_provider_icon_slug(self, obj):
        """Get provider icon slug."""
        if obj.provider_icon_slug:
            return obj.provider_icon_slug
        provider = self.get_provider(obj)
        if provider:
            return get_provider_icon_slug(provider)
        return None

    def get_provider_icon_url(self, obj):
        """Get provider icon URL."""
        if obj.provider_icon_url:
            return obj.provider_icon_url
        slug = self.get_provider_icon_slug(obj)
        if slug:
            return f"{LOBEHUB_CDN_BASE}/provider/{slug}.png"
        return None


class RecommendedModelFromConversationSerializer(serializers.Serializer):
    """
    Serializer for the recommended model from those actually used in the conversation.
    Enriched with full model details from ModelCatalog.
    """

    model_id = serializers.CharField()
    model_name = serializers.CharField()
    provider = serializers.CharField()
    reasoning = serializers.CharField()
    score = serializers.FloatField()
    metrics = serializers.JSONField()

    # Model catalog details (SerializerMethodFields)
    model_icon_slug = serializers.SerializerMethodField()
    model_icon_url = serializers.SerializerMethodField()
    provider_icon_slug = serializers.SerializerMethodField()
    provider_icon_url = serializers.SerializerMethodField()
    cost_per_1m_prompt = serializers.SerializerMethodField()
    cost_per_1m_completion = serializers.SerializerMethodField()
    max_tokens = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()
    supports_streaming = serializers.SerializerMethodField()
    supports_functions = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()

    def _get_model_catalog(self, obj):
        """Helper method to fetch model from catalog with fallback search."""
        import logging
        logger = logging.getLogger(__name__)

        if not hasattr(self, '_model_cache'):
            self._model_cache = {}

        model_id = obj.get('model_id')
        if model_id not in self._model_cache:
            try:
                # Try exact match first
                self._model_cache[model_id] = ModelCatalog.objects.get(model_id=model_id)
            except ModelCatalog.DoesNotExist:
                try:
                    # Try case-insensitive match
                    self._model_cache[model_id] = ModelCatalog.objects.get(model_id__iexact=model_id)
                except ModelCatalog.DoesNotExist:
                    logger.warning(
                        f"Model '{model_id}' not found in catalog for recommended_from_conversation. "
                        f"Model name: {obj.get('model_name')}, Provider: {obj.get('provider')}"
                    )
                    self._model_cache[model_id] = None

        return self._model_cache[model_id]

    def get_model_icon_slug(self, obj):
        model = self._get_model_catalog(obj)
        return get_model_icon_slug(obj.get('model_id')) if model else None

    def get_model_icon_url(self, obj):
        slug = self.get_model_icon_slug(obj)
        return f"{LOBEHUB_CDN_BASE}/model/{slug}.png" if slug else None

    def get_provider_icon_slug(self, obj):
        return get_provider_icon_slug(obj.get('provider'))

    def get_provider_icon_url(self, obj):
        slug = self.get_provider_icon_slug(obj)
        return f"{LOBEHUB_CDN_BASE}/provider/{slug}.png" if slug else None

    def get_cost_per_1m_prompt(self, obj):
        model = self._get_model_catalog(obj)
        if not model or model.prompt_price is None:
            return None
        return convert_to_display_unit(model.prompt_price)

    def get_cost_per_1m_completion(self, obj):
        model = self._get_model_catalog(obj)
        if not model or model.completion_price is None:
            return None
        return convert_to_display_unit(model.completion_price)

    def get_max_tokens(self, obj):
        model = self._get_model_catalog(obj)
        return model.max_tokens if model else None

    def get_description(self, obj):
        model = self._get_model_catalog(obj)
        return model.description if model else None

    def get_is_available(self, obj):
        model = self._get_model_catalog(obj)
        return model.is_available if model else True

    def get_supports_streaming(self, obj):
        model = self._get_model_catalog(obj)
        return model.supports_streaming if model else True

    def get_supports_functions(self, obj):
        model = self._get_model_catalog(obj)
        return model.supports_functions if model else False

    def get_tags(self, obj):
        model = self._get_model_catalog(obj)
        return model.tags if model else []


class ModelRecommendationSerializer(serializers.ModelSerializer):
    """
    Serializer for model recommendations (alternatives).
    Enriched with full model details from ModelCatalog.
    """

    # Explicitly serialize DecimalField as float for frontend compatibility
    estimated_cost_per_message = serializers.FloatField(read_only=True)

    # Model catalog details (SerializerMethodFields)
    model_icon_slug = serializers.SerializerMethodField()
    model_icon_url = serializers.SerializerMethodField()
    provider_icon_slug = serializers.SerializerMethodField()
    provider_icon_url = serializers.SerializerMethodField()
    cost_per_1m_prompt = serializers.SerializerMethodField()
    cost_per_1m_completion = serializers.SerializerMethodField()
    max_tokens = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()
    supports_streaming = serializers.SerializerMethodField()
    supports_functions = serializers.SerializerMethodField()
    tags = serializers.SerializerMethodField()

    class Meta:
        model = ModelRecommendation
        fields = [
            "id",
            "model_id",
            "model_name",
            "provider",
            "score",
            "rank",
            "reasoning",
            "tradeoffs",
            "estimated_cost_per_message",
            "estimated_quality_score",
            # Additional model catalog fields
            "model_icon_slug",
            "model_icon_url",
            "provider_icon_slug",
            "provider_icon_url",
            "cost_per_1m_prompt",
            "cost_per_1m_completion",
            "max_tokens",
            "description",
            "is_available",
            "supports_streaming",
            "supports_functions",
            "tags",
        ]
        read_only_fields = ["id"]

    def _get_model_catalog(self, obj):
        """
        Helper method to fetch model from catalog.
        Cached to avoid multiple queries per recommendation.
        """
        if not hasattr(self, '_model_cache'):
            self._model_cache = {}

        if obj.model_id not in self._model_cache:
            try:
                self._model_cache[obj.model_id] = ModelCatalog.objects.get(
                    model_id=obj.model_id
                )
            except ModelCatalog.DoesNotExist:
                self._model_cache[obj.model_id] = None

        return self._model_cache[obj.model_id]

    def get_model_icon_slug(self, obj):
        """Get model icon slug from ModelCatalog."""
        model = self._get_model_catalog(obj)
        if not model:
            return None
        model_slug = get_model_icon_slug(model.model_id, model.name)
        if model_slug:
            return model_slug
        return get_provider_icon_slug(model.provider)

    def get_model_icon_url(self, obj):
        """Get model icon URL from ModelCatalog."""
        model = self._get_model_catalog(obj)
        if not model:
            return None

        # Try to get model-specific icon
        model_slug = get_model_icon_slug(model.model_id, model.name)
        if model_slug:
            return f"{LOBEHUB_CDN_BASE}/dark/{model_slug}.png"

        # Fallback to provider icon
        return get_provider_icon_url(model.provider, size="dark", format="png")

    def get_provider_icon_slug(self, obj):
        """Get provider icon slug from ModelCatalog."""
        model = self._get_model_catalog(obj)
        if not model:
            return None
        return get_provider_icon_slug(model.provider)

    def get_provider_icon_url(self, obj):
        """Get provider icon URL from ModelCatalog."""
        model = self._get_model_catalog(obj)
        if not model:
            return None
        return get_provider_icon_url(model.provider, size="dark", format="png")

    def get_cost_per_1m_prompt(self, obj):
        """Get prompt pricing from ModelCatalog."""
        model = self._get_model_catalog(obj)
        if not model or model.prompt_price is None:
            return None
        return convert_to_display_unit(model.prompt_price)

    def get_cost_per_1m_completion(self, obj):
        """Get completion pricing from ModelCatalog."""
        model = self._get_model_catalog(obj)
        if not model or model.completion_price is None:
            return None
        return convert_to_display_unit(model.completion_price)

    def get_max_tokens(self, obj):
        """Get max tokens from ModelCatalog."""
        model = self._get_model_catalog(obj)
        return model.max_tokens if model else None

    def get_description(self, obj):
        """Get description from ModelCatalog."""
        model = self._get_model_catalog(obj)
        return model.description if model else None

    def get_is_available(self, obj):
        """Get availability from ModelCatalog."""
        model = self._get_model_catalog(obj)
        return model.is_available if model else False

    def get_supports_streaming(self, obj):
        """Get streaming support from ModelCatalog."""
        model = self._get_model_catalog(obj)
        return model.supports_streaming if model else False

    def get_supports_functions(self, obj):
        """Get function calling support from ModelCatalog."""
        model = self._get_model_catalog(obj)
        return model.supports_functions if model else False

    def get_tags(self, obj):
        """Get tags from ModelCatalog."""
        model = self._get_model_catalog(obj)
        return model.tags if model else []


class ConversationAnalysisSerializer(serializers.ModelSerializer):
    """
    Serializer for conversation analysis results.
    """

    # Recommended model from conversation
    recommended_from_conversation = serializers.SerializerMethodField()

    # Alternative models (renamed from recommendations)
    alternative_models = ModelRecommendationSerializer(
        source='recommendations', many=True, read_only=True
    )

    # Keep for backward compatibility
    recommendations = ModelRecommendationSerializer(many=True, read_only=True)

    # Explicitly serialize DecimalField as float for frontend compatibility
    total_cost = serializers.FloatField(read_only=True)
    avg_cost_per_message = serializers.FloatField(read_only=True)

    class Meta:
        model = ConversationAnalysis
        fields = [
            "id",
            "conversation_type",
            "total_messages",
            "total_tokens",
            "avg_cost_per_message",
            "avg_latency",
            "total_cost",
            "insights",
            "detected_needs",
            "user_preferences",
            "recommended_from_conversation",
            "alternative_models",
            "recommendations",  # deprecated but kept for compatibility
            "analyzed_at",
        ]
        read_only_fields = ["id", "analyzed_at"]

    def get_recommended_from_conversation(self, obj):
        """
        Serialize the recommended model from conversation.
        Returns None if not set.
        """
        if not obj.recommended_model_from_conversation:
            return None

        serializer = RecommendedModelFromConversationSerializer(
            obj.recommended_model_from_conversation
        )
        return serializer.data


class ConsiglierSessionSerializer(serializers.ModelSerializer):
    """
    Serializer for Consigliere sessions.
    """

    analysis = ConversationAnalysisSerializer(read_only=True)
    messages = ConsigliereMessageSerializer(many=True, read_only=True)
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = ConsiglierSession
        fields = [
            "id",
            "chat_group_id",
            "chat_group_data",
            "current_model_at_start",
            "is_active",
            "created_at",
            "updated_at",
            "analysis",
            "messages",
            "message_count",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_message_count(self, obj):
        """Get the count of messages in this session."""
        return obj.messages.count()


class ConsiglierSessionSummarySerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing sessions (without full data).
    """

    has_analysis = serializers.SerializerMethodField()
    message_count = serializers.SerializerMethodField()

    class Meta:
        model = ConsiglierSession
        fields = [
            "id",
            "chat_group_id",
            "current_model_at_start",
            "is_active",
            "created_at",
            "updated_at",
            "has_analysis",
            "message_count",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_has_analysis(self, obj):
        """Check if this session has an analysis."""
        return hasattr(obj, "analysis")

    def get_message_count(self, obj):
        """Get the count of messages in this session."""
        return obj.messages.count()


# ============================================================================
# Response-only Serializers
# ============================================================================


class AnalyzeConversationResponseSerializer(serializers.Serializer):
    """
    Response serializer for conversation analysis.
    """

    session_id = serializers.UUIDField()
    analysis = ConversationAnalysisSerializer()


class ChatMessageResponseSerializer(serializers.Serializer):
    """
    Response serializer for chat messages.
    """

    message = ConsigliereMessageSerializer()
    session_id = serializers.UUIDField()
