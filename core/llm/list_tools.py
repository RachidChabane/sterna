"""
List Tools for LangChain

Provides premium listing tools to help users discover their resources:
- Sparks (interactive React components)
- Generated images
- Generated videos
- Voice rooms
- Available MCP servers
- Available LLM models

These tools help the LLM answer questions like "What do I have?" with
rich, detailed responses.

All tools support optional filtering parameters for flexible querying.
"""

import json
import logging
from datetime import datetime
from typing import Optional, Literal

from langchain.tools import tool
from pydantic import BaseModel, Field

# Reuse knowledge base context for user info
from .knowledge_base_tools import KNOWLEDGE_BASE_USER_CONTEXT

logger = logging.getLogger(__name__)


# ============================================================================
# MODEL NAME MAPPING (user-friendly → canonical)
# ============================================================================

IMAGE_MODEL_ALIASES = {
    # User-friendly names (case-insensitive matching)
    'nano banana': 'google/gemini-2.5-flash-image',
    'nanobanana': 'google/gemini-2.5-flash-image',
    'nano banana pro': 'google/gemini-3-pro-image-preview',
    'nanobananapro': 'google/gemini-3-pro-image-preview',
    # Short names
    'flash': 'google/gemini-2.5-flash-image',
    'pro': 'google/gemini-3-pro-image-preview',
}


def _resolve_image_model(model: str) -> str:
    """Resolve user-friendly model name to canonical model ID."""
    if not model:
        return model
    normalized = model.lower().strip().replace('-', ' ').replace('_', ' ')
    return IMAGE_MODEL_ALIASES.get(normalized, model)


def _resolve_current_ids(
    conversation_id: Optional[str],
    chat_id: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """
    Resolve 'current' keyword to actual IDs from context.

    Returns (resolved_conversation_id, resolved_chat_id)
    """
    user_context = KNOWLEDGE_BASE_USER_CONTEXT.get()
    if not user_context:
        return conversation_id, chat_id

    resolved_conv = conversation_id
    resolved_chat = chat_id

    if conversation_id and conversation_id.lower() == 'current':
        resolved_conv = user_context.get('conversation_id')

    if chat_id and chat_id.lower() == 'current':
        resolved_chat = user_context.get('chat_id')

    return resolved_conv, resolved_chat


# ============================================================================
# INPUT SCHEMAS FOR LIST TOOLS
# ============================================================================

class ListSparksInput(BaseModel):
    """Input schema for list_sparks tool."""
    framework: Optional[Literal['react', 'html', 'svg']] = Field(
        default=None, description="Filter by framework type"
    )
    conversation_id: Optional[str] = Field(
        default=None,
        description="Only set this if the user explicitly asks to filter by a specific conversation. Pass a UUID, or 'current' only if user says 'this conversation' or 'current conversation'. Omit entirely for all sparks."
    )
    chat_id: Optional[str] = Field(
        default=None,
        description="Only set this if the user explicitly asks to filter by a specific chat. Pass a UUID, or 'current' only if user says 'this chat' or 'current chat'. Omit entirely for all sparks."
    )
    title_contains: Optional[str] = Field(
        default=None, description="Filter by title containing this text (case-insensitive)"
    )
    min_version: Optional[int] = Field(
        default=None, ge=1, description="Minimum version number"
    )
    has_dependency: Optional[str] = Field(
        default=None, description="Filter by sparks that use a specific dependency (e.g., 'recharts', 'lucide-react')"
    )
    created_after: Optional[str] = Field(
        default=None, description="Filter by creation date (ISO format: YYYY-MM-DD)"
    )
    created_before: Optional[str] = Field(
        default=None, description="Filter by creation date (ISO format: YYYY-MM-DD)"
    )
    limit: Optional[int] = Field(
        default=25, ge=1, le=100, description="Maximum number of results (1-100)"
    )


class ListGeneratedImagesInput(BaseModel):
    """Input schema for list_generated_images tool."""
    conversation_id: Optional[str] = Field(
        default=None,
        description="Only set this if the user explicitly asks to filter by a specific conversation. Pass a UUID, or 'current' only if user says 'this conversation'. Omit entirely for all images."
    )
    chat_id: Optional[str] = Field(
        default=None,
        description="Only set this if the user explicitly asks to filter by a specific chat. Pass a UUID, or 'current' only if user says 'this chat'. Omit entirely for all images."
    )
    orientation: Optional[Literal['square', 'landscape', 'portrait']] = Field(
        default=None, description="Filter by image orientation"
    )
    model: Optional[str] = Field(
        default=None,
        description="Filter by generation model. Accepts: 'nano banana' or 'nano banana pro' (user-friendly names), or model IDs like 'gemini-2.5-flash-image'"
    )
    min_width: Optional[int] = Field(
        default=None, ge=1, description="Minimum image width in pixels"
    )
    max_width: Optional[int] = Field(
        default=None, ge=1, description="Maximum image width in pixels"
    )
    min_height: Optional[int] = Field(
        default=None, ge=1, description="Minimum image height in pixels"
    )
    max_height: Optional[int] = Field(
        default=None, ge=1, description="Maximum image height in pixels"
    )
    prompt_contains: Optional[str] = Field(
        default=None, description="Filter by prompt containing this text (case-insensitive)"
    )
    filename_contains: Optional[str] = Field(
        default=None, description="Filter by filename containing this text (case-insensitive)"
    )
    min_size_kb: Optional[float] = Field(
        default=None, ge=0, description="Minimum file size in KB"
    )
    max_size_kb: Optional[float] = Field(
        default=None, ge=0, description="Maximum file size in KB"
    )
    created_after: Optional[str] = Field(
        default=None, description="Filter by creation date (ISO format: YYYY-MM-DD)"
    )
    created_before: Optional[str] = Field(
        default=None, description="Filter by creation date (ISO format: YYYY-MM-DD)"
    )
    limit: Optional[int] = Field(
        default=25, ge=1, le=100, description="Maximum number of results (1-100)"
    )


class ListGeneratedVideosInput(BaseModel):
    """Input schema for list_generated_videos tool."""
    conversation_id: Optional[str] = Field(
        default=None,
        description="Only set this if the user explicitly asks to filter by a specific conversation. Pass a UUID, or 'current' only if user says 'this conversation'. Omit entirely for all videos."
    )
    chat_id: Optional[str] = Field(
        default=None,
        description="Only set this if the user explicitly asks to filter by a specific chat. Pass a UUID, or 'current' only if user says 'this chat'. Omit entirely for all videos."
    )
    min_duration: Optional[float] = Field(
        default=None, ge=0, description="Minimum duration in seconds"
    )
    max_duration: Optional[float] = Field(
        default=None, ge=0, description="Maximum duration in seconds"
    )
    min_width: Optional[int] = Field(
        default=None, ge=1, description="Minimum video width in pixels"
    )
    max_width: Optional[int] = Field(
        default=None, ge=1, description="Maximum video width in pixels"
    )
    prompt_contains: Optional[str] = Field(
        default=None, description="Filter by prompt containing this text (case-insensitive)"
    )
    filename_contains: Optional[str] = Field(
        default=None, description="Filter by filename containing this text (case-insensitive)"
    )
    min_size_mb: Optional[float] = Field(
        default=None, ge=0, description="Minimum file size in MB"
    )
    max_size_mb: Optional[float] = Field(
        default=None, ge=0, description="Maximum file size in MB"
    )
    created_after: Optional[str] = Field(
        default=None, description="Filter by creation date (ISO format: YYYY-MM-DD)"
    )
    created_before: Optional[str] = Field(
        default=None, description="Filter by creation date (ISO format: YYYY-MM-DD)"
    )
    limit: Optional[int] = Field(
        default=25, ge=1, le=100, description="Maximum number of results (1-100)"
    )


class ListVoiceRoomsInput(BaseModel):
    """Input schema for list_voice_rooms tool."""
    name_contains: Optional[str] = Field(
        default=None, description="Filter by room name containing this text (case-insensitive)"
    )
    description_contains: Optional[str] = Field(
        default=None, description="Filter by description containing this text (case-insensitive)"
    )
    language: Optional[str] = Field(
        default=None, description="Filter by language code (e.g., 'en', 'fr', 'es')"
    )
    min_agents: Optional[int] = Field(
        default=None, ge=1, description="Minimum number of agents in the room"
    )
    max_agents: Optional[int] = Field(
        default=None, ge=1, description="Maximum number of agents in the room"
    )
    has_agent_model: Optional[str] = Field(
        default=None, description="Filter rooms that have an agent using this model (partial match)"
    )
    created_after: Optional[str] = Field(
        default=None, description="Filter by creation date (ISO format: YYYY-MM-DD)"
    )
    created_before: Optional[str] = Field(
        default=None, description="Filter by creation date (ISO format: YYYY-MM-DD)"
    )
    limit: Optional[int] = Field(
        default=20, ge=1, le=50, description="Maximum number of results (1-50)"
    )


class ListMCPServersInput(BaseModel):
    """Input schema for list_mcp_servers tool."""
    category: Optional[str] = Field(
        default=None, description="Filter by category (e.g., 'productivity', 'developer', 'cloud')"
    )
    is_connected: Optional[bool] = Field(
        default=None, description="Filter by connection status (True = connected, False = not connected)"
    )
    is_official: Optional[bool] = Field(
        default=None, description="Filter by official status"
    )
    is_preconfigured: Optional[bool] = Field(
        default=None, description="Filter by preconfigured status"
    )
    name_contains: Optional[str] = Field(
        default=None, description="Filter by server name containing this text (case-insensitive)"
    )
    description_contains: Optional[str] = Field(
        default=None, description="Filter by description containing this text (case-insensitive)"
    )
    limit: Optional[int] = Field(
        default=50, ge=1, le=100, description="Maximum number of results (1-100)"
    )


class ListAvailableModelsInput(BaseModel):
    """Input schema for list_available_models tool."""
    provider: Optional[str] = Field(
        default=None, description="Filter by provider (e.g., 'anthropic', 'openai', 'google')"
    )
    supports_vision: Optional[bool] = Field(
        default=None, description="Filter by vision capability"
    )
    supports_tools: Optional[bool] = Field(
        default=None, description="Filter by tools/function-calling capability"
    )
    supports_reasoning: Optional[bool] = Field(
        default=None, description="Filter by reasoning/thinking capability"
    )
    min_context_window: Optional[int] = Field(
        default=None, ge=1, description="Minimum context window size in tokens"
    )
    max_context_window: Optional[int] = Field(
        default=None, ge=1, description="Maximum context window size in tokens"
    )
    name_contains: Optional[str] = Field(
        default=None, description="Filter by model name containing this text (case-insensitive)"
    )
    limit: Optional[int] = Field(
        default=None, ge=1, description="Maximum number of results. If not set, returns all models."
    )


class ListCodingAgentsInput(BaseModel):
    """Input schema for list_coding_agents tool."""
    name_contains: Optional[str] = Field(
        default=None, description="Filter by agent name containing this text (case-insensitive)"
    )
    model_tier: Optional[Literal['fast', 'balanced', 'powerful', 'inherit']] = Field(
        default=None, description="Filter by model tier"
    )
    is_active: Optional[bool] = Field(
        default=None, description="Filter by active status (True = active, False = inactive)"
    )
    limit: Optional[int] = Field(
        default=30, ge=1, le=100, description="Maximum number of results (1-100)"
    )


class UpdateCodingAgentInput(BaseModel):
    """Input schema for update_coding_agent tool."""
    agent_id: Optional[str] = Field(
        default=None, description="UUID of the agent to update (use this or agent_name)"
    )
    agent_name: Optional[str] = Field(
        default=None, description="Name of the agent to update (use this or agent_id). Agent names are unique per user."
    )
    description: Optional[str] = Field(
        default=None, description="New description for the agent"
    )
    model_tier: Optional[Literal['fast', 'balanced', 'powerful', 'inherit']] = Field(
        default=None, description="New model tier"
    )
    tools: Optional[list[str]] = Field(
        default=None, description="New list of allowed tools (e.g. ['Read', 'Glob', 'Grep'])"
    )
    disallowed_tools: Optional[list[str]] = Field(
        default=None, description="New list of disallowed tools"
    )
    max_turns: Optional[int] = Field(
        default=None, ge=1, le=100, description="New maximum agentic turns (1-100)"
    )
    permission_mode: Optional[Literal['default', 'plan', 'autoEdit', 'fullAuto']] = Field(
        default=None, description="New permission mode"
    )
    is_active: Optional[bool] = Field(
        default=None, description="Set active/inactive status"
    )


class CompareModelsInput(BaseModel):
    """Input schema for compare_models tool."""
    preset: Optional[Literal['balanced', 'budget', 'long_context', 'tool_use', 'multimodal', 'coding']] = Field(
        default='balanced',
        description="Comparison preset: 'balanced' (default), 'budget' (minimize cost), 'long_context' (prioritize context window), 'tool_use' (prioritize function calling), 'multimodal' (prioritize multi-modal support), 'coding' (optimized for coding)"
    )
    model_ids: Optional[list[str]] = Field(
        default=None,
        description="Specific model IDs to compare (e.g., ['anthropic/claude-sonnet-4-20250514', 'openai/gpt-4o']). If not provided, compares all available models."
    )
    provider: Optional[str] = Field(
        default=None,
        description="Filter to models from a specific provider (e.g., 'anthropic', 'openai', 'google')"
    )
    must_support_tools: Optional[bool] = Field(
        default=False,
        description="Only include models that support function calling/tools"
    )
    must_support_vision: Optional[bool] = Field(
        default=False,
        description="Only include models that support image inputs"
    )
    must_support_reasoning: Optional[bool] = Field(
        default=False,
        description="Only include models that support reasoning/thinking"
    )
    min_context_tokens: Optional[int] = Field(
        default=None, ge=1,
        description="Minimum context window size in tokens"
    )
    max_cost_per_1m_tokens: Optional[float] = Field(
        default=None, ge=0,
        description="Maximum cost per 1M tokens in USD (filters out expensive models)"
    )
    limit: Optional[int] = Field(
        default=10, ge=1, le=25,
        description="Maximum number of models to return in the comparison (1-25)"
    )


# ============================================================================
# SPARKS LISTING
# ============================================================================

@tool(args_schema=ListSparksInput)
def list_sparks(
    framework: Optional[str] = None,
    conversation_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    title_contains: Optional[str] = None,
    min_version: Optional[int] = None,
    has_dependency: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    limit: Optional[int] = 25,
) -> str:
    """
    List Sparks (interactive React components) the user has created.

    Use this when the user asks about their sparks, creations, components,
    interactive elements, visualizations, or apps they've built.

    IMPORTANT: All parameters are optional. Only pass filters the user explicitly requests.
    - Do NOT pass conversation_id or chat_id unless user specifically asks for "this conversation" or "this chat"
    - For general queries like "list my sparks" or "what sparks do I have", pass NO filters

    Returns:
        A detailed list of sparks with titles, frameworks, versions, and dependencies.
    """
    user_context = KNOWLEDGE_BASE_USER_CONTEXT.get()

    if not user_context:
        return "Error: No user context available."

    user = user_context.get('user')
    if not user:
        return "Error: User not authenticated."

    # Resolve 'current' keywords
    conversation_id, chat_id = _resolve_current_ids(conversation_id, chat_id)

    try:
        from sparks.models import Spark

        queryset = Spark.objects.filter(user=user)

        # Apply filters
        if framework:
            queryset = queryset.filter(framework=framework)
        if conversation_id:
            queryset = queryset.filter(chat__conversation_id=conversation_id)
        if chat_id:
            queryset = queryset.filter(chat_id=chat_id)
        if title_contains:
            queryset = queryset.filter(title__icontains=title_contains)
        if min_version:
            queryset = queryset.filter(version__gte=min_version)
        if has_dependency:
            queryset = queryset.filter(dependencies__contains=[has_dependency])
        if created_after:
            try:
                date = datetime.fromisoformat(created_after)
                queryset = queryset.filter(created_at__gte=date)
            except ValueError:
                pass
        if created_before:
            try:
                date = datetime.fromisoformat(created_before)
                queryset = queryset.filter(created_at__lte=date)
            except ValueError:
                pass

        sparks = queryset.order_by('-updated_at')[:limit or 25]

        if not sparks:
            return json.dumps({
                'total_sparks': 0,
                'sparks': [],
                'formatted_text': "No Sparks found matching your criteria. Try adjusting your filters or ask me to create an interactive component."
            })

        spark_list = []
        framework_counts = {'react': 0, 'html': 0, 'svg': 0}

        for spark in sparks:
            framework_counts[spark.framework] = framework_counts.get(spark.framework, 0) + 1

            # Detect notable dependencies
            notable_deps = []
            if spark.dependencies:
                if 'recharts' in spark.dependencies:
                    notable_deps.append('recharts')
                if 'lucide-react' in spark.dependencies:
                    notable_deps.append('lucide')

            spark_list.append({
                'id': str(spark.id),
                'title': spark.title,
                'framework': spark.framework,
                'version': spark.version,
                'dependencies': spark.dependencies or [],
                'notable_deps': notable_deps,
                'created_at': spark.created_at.strftime('%Y-%m-%d') if spark.created_at else None,
                'updated_at': spark.updated_at.strftime('%Y-%m-%d %H:%M') if spark.updated_at else None,
            })

        # Format for LLM (text-only)
        formatted_lines = [f"Your Sparks ({len(spark_list)} component{'s' if len(spark_list) != 1 else ''}):\n"]

        # Stats summary
        stats = []
        if framework_counts['react'] > 0:
            stats.append(f"{framework_counts['react']} React")
        if framework_counts['html'] > 0:
            stats.append(f"{framework_counts['html']} HTML")
        if framework_counts['svg'] > 0:
            stats.append(f"{framework_counts['svg']} SVG")
        if stats:
            formatted_lines.append(f"Breakdown: {', '.join(stats)}\n")

        for i, spark in enumerate(spark_list, 1):
            version_info = f" (v{spark['version']})" if spark['version'] > 1 else ""
            formatted_lines.append(
                f"{i}. {spark['title']}{version_info} - {spark['framework'].upper()}"
            )

        return json.dumps({
            'total_sparks': len(spark_list),
            'framework_breakdown': framework_counts,
            'sparks': spark_list,
            'formatted_text': '\n'.join(formatted_lines)
        })

    except Exception as e:
        logger.exception(f"Error listing sparks: {e}")
        return f"Error accessing sparks: {str(e)}"


# ============================================================================
# GENERATED IMAGES LISTING
# ============================================================================

@tool(args_schema=ListGeneratedImagesInput)
def list_generated_images(
    conversation_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    orientation: Optional[str] = None,
    model: Optional[str] = None,
    min_width: Optional[int] = None,
    max_width: Optional[int] = None,
    min_height: Optional[int] = None,
    max_height: Optional[int] = None,
    prompt_contains: Optional[str] = None,
    filename_contains: Optional[str] = None,
    min_size_kb: Optional[float] = None,
    max_size_kb: Optional[float] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    limit: Optional[int] = 25,
) -> str:
    """
    List AI-generated images the user has created.

    Use this when the user asks about their generated images, AI art,
    creations, artwork, or wants to see what images they've made.

    IMPORTANT: All parameters are optional. Only pass filters the user explicitly requests.
    - Do NOT pass conversation_id or chat_id unless user specifically asks for "this conversation" or "this chat"
    - For general queries like "list my images" or "show my generated images", pass NO filters
    - Model filter accepts 'nano banana', 'nano banana pro', or model IDs

    Returns:
        A detailed list of generated images with prompts, dimensions, and models used.
    """
    user_context = KNOWLEDGE_BASE_USER_CONTEXT.get()

    if not user_context:
        return "Error: No user context available."

    user = user_context.get('user')
    if not user:
        return "Error: User not authenticated."

    # Resolve 'current' keywords and model aliases
    conversation_id, chat_id = _resolve_current_ids(conversation_id, chat_id)
    resolved_model = _resolve_image_model(model) if model else None

    try:
        from workspaces.models import Asset

        # Get AI-generated images (have generation_prompt)
        queryset = Asset.objects.filter(
            user=user,
            asset_type__in=['generated', 'image']
        ).exclude(
            generation_prompt__isnull=True
        ).exclude(
            generation_prompt=''
        )

        # Apply filters
        if conversation_id:
            queryset = queryset.filter(chat__conversation_id=conversation_id)
        if chat_id:
            queryset = queryset.filter(chat_id=chat_id)
        if resolved_model:
            queryset = queryset.filter(generation_model__icontains=resolved_model)
        if min_width:
            queryset = queryset.filter(width__gte=min_width)
        if max_width:
            queryset = queryset.filter(width__lte=max_width)
        if min_height:
            queryset = queryset.filter(height__gte=min_height)
        if max_height:
            queryset = queryset.filter(height__lte=max_height)
        if prompt_contains:
            queryset = queryset.filter(generation_prompt__icontains=prompt_contains)
        if filename_contains:
            queryset = queryset.filter(filename__icontains=filename_contains)
        if min_size_kb:
            queryset = queryset.filter(size_bytes__gte=min_size_kb * 1024)
        if max_size_kb:
            queryset = queryset.filter(size_bytes__lte=max_size_kb * 1024)
        if created_after:
            try:
                date = datetime.fromisoformat(created_after)
                queryset = queryset.filter(created_at__gte=date)
            except ValueError:
                pass
        if created_before:
            try:
                date = datetime.fromisoformat(created_before)
                queryset = queryset.filter(created_at__lte=date)
            except ValueError:
                pass

        # Orientation filter (requires post-filtering since it's computed)
        images = list(queryset.order_by('-created_at')[:limit or 25])

        if orientation:
            filtered_images = []
            for img in images:
                if img.width and img.height:
                    if img.width == img.height and orientation == 'square':
                        filtered_images.append(img)
                    elif img.width > img.height and orientation == 'landscape':
                        filtered_images.append(img)
                    elif img.width < img.height and orientation == 'portrait':
                        filtered_images.append(img)
            images = filtered_images

        if not images:
            return json.dumps({
                'total_images': 0,
                'images': [],
                'formatted_text': "No images found matching your criteria. Try adjusting your filters or ask me to generate an image."
            })

        image_list = []
        total_size = 0

        for img in images:
            size_kb = img.size_bytes / 1024 if img.size_bytes else 0
            total_size += img.size_bytes or 0

            # Dimension orientation
            if img.width and img.height:
                if img.width == img.height:
                    img_orientation = "square"
                elif img.width > img.height:
                    img_orientation = "landscape"
                else:
                    img_orientation = "portrait"
                dimensions = f"{img.width}x{img.height}"
            else:
                img_orientation = None
                dimensions = None

            # Truncate prompt for display
            prompt_preview = img.generation_prompt[:80] + '...' if len(img.generation_prompt or '') > 80 else img.generation_prompt

            image_list.append({
                'id': str(img.id),
                'filename': img.filename,
                'prompt': prompt_preview,
                'full_prompt': img.generation_prompt,
                'size_kb': round(size_kb, 1),
                'dimensions': dimensions,
                'orientation': img_orientation,
                'width': img.width,
                'height': img.height,
                'model': img.generation_model if hasattr(img, 'generation_model') else None,
                'created_at': img.created_at.strftime('%Y-%m-%d %H:%M') if img.created_at else None,
            })

        # Format for LLM (text-only)
        total_size_mb = total_size / (1024 * 1024)
        formatted_lines = [f"Your Generated Images ({len(image_list)} image{'s' if len(image_list) != 1 else ''})"]
        formatted_lines.append(f"Total size: {total_size_mb:.1f} MB\n")

        for i, img in enumerate(image_list, 1):
            dims = f" [{img['dimensions']}]" if img['dimensions'] else ""
            formatted_lines.append(f"{i}. {img['filename']}{dims} - \"{img['prompt']}\"")

        return json.dumps({
            'total_images': len(image_list),
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size_mb, 2),
            'images': image_list,
            'formatted_text': '\n'.join(formatted_lines)
        })

    except Exception as e:
        logger.exception(f"Error listing generated images: {e}")
        return f"Error accessing images: {str(e)}"


# ============================================================================
# GENERATED VIDEOS LISTING
# ============================================================================

@tool(args_schema=ListGeneratedVideosInput)
def list_generated_videos(
    conversation_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    min_duration: Optional[float] = None,
    max_duration: Optional[float] = None,
    min_width: Optional[int] = None,
    max_width: Optional[int] = None,
    prompt_contains: Optional[str] = None,
    filename_contains: Optional[str] = None,
    min_size_mb: Optional[float] = None,
    max_size_mb: Optional[float] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    limit: Optional[int] = 25,
) -> str:
    """
    List AI-generated videos the user has created.

    Use this when the user asks about their generated videos, AI videos,
    animations, or video creations.

    IMPORTANT: All parameters are optional. Only pass filters the user explicitly requests.
    - Do NOT pass conversation_id or chat_id unless user specifically asks for "this conversation" or "this chat"
    - For general queries like "list my videos" or "show my generated videos", pass NO filters

    Returns:
        A detailed list of generated videos with prompts, durations, and dimensions.
    """
    user_context = KNOWLEDGE_BASE_USER_CONTEXT.get()

    if not user_context:
        return "Error: No user context available."

    user = user_context.get('user')
    if not user:
        return "Error: User not authenticated."

    # Resolve 'current' keywords
    conversation_id, chat_id = _resolve_current_ids(conversation_id, chat_id)

    try:
        from workspaces.models import Asset

        # Get AI-generated videos
        queryset = Asset.objects.filter(
            user=user,
            asset_type='video'
        )

        # Apply filters
        if conversation_id:
            queryset = queryset.filter(chat__conversation_id=conversation_id)
        if chat_id:
            queryset = queryset.filter(chat_id=chat_id)
        if min_duration:
            queryset = queryset.filter(duration_seconds__gte=min_duration)
        if max_duration:
            queryset = queryset.filter(duration_seconds__lte=max_duration)
        if min_width:
            queryset = queryset.filter(width__gte=min_width)
        if max_width:
            queryset = queryset.filter(width__lte=max_width)
        if prompt_contains:
            queryset = queryset.filter(generation_prompt__icontains=prompt_contains)
        if filename_contains:
            queryset = queryset.filter(filename__icontains=filename_contains)
        if min_size_mb:
            queryset = queryset.filter(size_bytes__gte=min_size_mb * 1024 * 1024)
        if max_size_mb:
            queryset = queryset.filter(size_bytes__lte=max_size_mb * 1024 * 1024)
        if created_after:
            try:
                date = datetime.fromisoformat(created_after)
                queryset = queryset.filter(created_at__gte=date)
            except ValueError:
                pass
        if created_before:
            try:
                date = datetime.fromisoformat(created_before)
                queryset = queryset.filter(created_at__lte=date)
            except ValueError:
                pass

        videos = queryset.order_by('-created_at')[:limit or 25]

        if not videos:
            return json.dumps({
                'total_videos': 0,
                'videos': [],
                'formatted_text': "No videos found matching your criteria. Try adjusting your filters or ask me to generate a video."
            })

        video_list = []
        total_size = 0
        total_duration = 0

        for vid in videos:
            size_mb = vid.size_bytes / (1024 * 1024) if vid.size_bytes else 0
            total_size += vid.size_bytes or 0
            total_duration += vid.duration_seconds or 0

            # Duration formatting
            if vid.duration_seconds:
                if vid.duration_seconds < 60:
                    duration_str = f"{vid.duration_seconds:.1f}s"
                else:
                    mins = int(vid.duration_seconds // 60)
                    secs = int(vid.duration_seconds % 60)
                    duration_str = f"{mins}:{secs:02d}"
            else:
                duration_str = None

            # Aspect ratio
            if vid.width and vid.height:
                ratio = vid.width / vid.height
                if abs(ratio - 1) < 0.1:
                    aspect = "square"
                elif ratio > 1:
                    aspect = "landscape"
                else:
                    aspect = "portrait"
                dimensions = f"{vid.width}x{vid.height}"
            else:
                aspect = None
                dimensions = None

            prompt_preview = (vid.generation_prompt[:60] + '...') if vid.generation_prompt and len(vid.generation_prompt) > 60 else vid.generation_prompt

            video_list.append({
                'id': str(vid.id),
                'filename': vid.filename,
                'prompt': prompt_preview,
                'full_prompt': vid.generation_prompt,
                'size_mb': round(size_mb, 2),
                'duration_seconds': vid.duration_seconds,
                'duration_str': duration_str,
                'dimensions': dimensions,
                'aspect': aspect,
                'width': vid.width,
                'height': vid.height,
                'created_at': vid.created_at.strftime('%Y-%m-%d %H:%M') if vid.created_at else None,
            })

        # Format for LLM (text-only)
        total_size_mb = total_size / (1024 * 1024)
        formatted_lines = [f"Your Generated Videos ({len(video_list)} video{'s' if len(video_list) != 1 else ''})"]

        # Stats
        stats = [f"{total_size_mb:.1f} MB total"]
        if total_duration > 0:
            if total_duration < 60:
                stats.append(f"{total_duration:.1f}s runtime")
            else:
                stats.append(f"{total_duration/60:.1f}min runtime")
        formatted_lines.append(f"{' | '.join(stats)}\n")

        for i, vid in enumerate(video_list, 1):
            dims = f" [{vid['dimensions']}]" if vid['dimensions'] else ""
            duration = f" ({vid['duration_str']})" if vid['duration_str'] else ""
            prompt_line = f" - \"{vid['prompt']}\"" if vid['prompt'] else ""
            formatted_lines.append(f"{i}. {vid['filename']}{dims}{duration}{prompt_line}")

        return json.dumps({
            'total_videos': len(video_list),
            'total_size_bytes': total_size,
            'total_size_mb': round(total_size_mb, 2),
            'total_duration_seconds': total_duration,
            'videos': video_list,
            'formatted_text': '\n'.join(formatted_lines)
        })

    except Exception as e:
        logger.exception(f"Error listing generated videos: {e}")
        return f"Error accessing videos: {str(e)}"


# ============================================================================
# VOICE ROOMS LISTING
# ============================================================================

@tool(args_schema=ListVoiceRoomsInput)
def list_voice_rooms(
    name_contains: Optional[str] = None,
    description_contains: Optional[str] = None,
    language: Optional[str] = None,
    min_agents: Optional[int] = None,
    max_agents: Optional[int] = None,
    has_agent_model: Optional[str] = None,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    limit: Optional[int] = 20,
) -> str:
    """
    List voice rooms the user has created.

    Use this when the user asks about their voice rooms, voice conversations,
    multi-AI rooms, AI panels, or voice-based discussions.

    All parameters are optional filters to narrow down results.

    Returns:
        A detailed list of voice rooms with agents, models, and voices.
    """
    user_context = KNOWLEDGE_BASE_USER_CONTEXT.get()

    if not user_context:
        return "Error: No user context available."

    user = user_context.get('user')
    if not user:
        return "Error: User not authenticated."

    try:
        from voice_rooms.models import VoiceRoom

        queryset = VoiceRoom.objects.filter(user=user, is_active=True).prefetch_related('agents')

        # Apply filters
        if name_contains:
            queryset = queryset.filter(name__icontains=name_contains)
        if description_contains:
            queryset = queryset.filter(description__icontains=description_contains)
        if language:
            queryset = queryset.filter(language=language)
        if created_after:
            try:
                date = datetime.fromisoformat(created_after)
                queryset = queryset.filter(created_at__gte=date)
            except ValueError:
                pass
        if created_before:
            try:
                date = datetime.fromisoformat(created_before)
                queryset = queryset.filter(created_at__lte=date)
            except ValueError:
                pass

        rooms = list(queryset.order_by('-updated_at')[:limit or 20])

        # Post-filter by agent count and model (requires prefetch)
        if min_agents or max_agents or has_agent_model:
            filtered_rooms = []
            for room in rooms:
                agents = list(room.agents.filter(is_active=True))
                agent_count = len(agents)

                if min_agents and agent_count < min_agents:
                    continue
                if max_agents and agent_count > max_agents:
                    continue
                if has_agent_model:
                    model_match = any(
                        has_agent_model.lower() in (a.model_id or '').lower()
                        for a in agents
                    )
                    if not model_match:
                        continue
                filtered_rooms.append(room)
            rooms = filtered_rooms

        if not rooms:
            return json.dumps({
                'total_rooms': 0,
                'rooms': [],
                'formatted_text': "No voice rooms found matching your criteria. Try adjusting your filters or create a new voice room."
            })

        room_list = []
        total_agents = 0

        for room in rooms:
            agents = list(room.agents.filter(is_active=True).values(
                'display_name', 'model_id', 'voice_name', 'order'
            ))
            total_agents += len(agents)

            # Agent details
            agent_details = []
            for a in sorted(agents, key=lambda x: x['order']):
                model_short = a['model_id'].split('/')[-1] if a['model_id'] else 'unknown'
                # Model provider
                provider = 'other'
                if 'claude' in model_short.lower():
                    provider = 'anthropic'
                elif 'gpt' in model_short.lower() or 'openai' in model_short.lower():
                    provider = 'openai'
                elif 'gemini' in model_short.lower():
                    provider = 'google'
                elif 'llama' in model_short.lower() or 'meta' in model_short.lower():
                    provider = 'meta'

                agent_details.append({
                    'name': a['display_name'],
                    'model': model_short,
                    'provider': provider,
                    'voice': a['voice_name']
                })

            # Room status
            session_count = room.sessions.count() if hasattr(room, 'sessions') else 0

            room_list.append({
                'id': str(room.id),
                'name': room.name,
                'description': room.description[:100] + '...' if room.description and len(room.description) > 100 else room.description,
                'agent_count': len(agents),
                'agents': agent_details,
                'language': room.language,
                'session_count': session_count,
                'created_at': room.created_at.strftime('%Y-%m-%d') if room.created_at else None,
                'updated_at': room.updated_at.strftime('%Y-%m-%d %H:%M') if room.updated_at else None,
            })

        # Format for LLM (text-only)
        formatted_lines = [f"Your Voice Rooms ({len(room_list)} room{'s' if len(room_list) != 1 else ''})"]
        formatted_lines.append(f"{total_agents} total agent{'s' if total_agents != 1 else ''} configured\n")

        for i, room in enumerate(room_list, 1):
            agent_line = ""
            if room['agents']:
                agent_strs = [f"{a['name']} ({a['provider']})" for a in room['agents'][:3]]
                if len(room['agents']) > 3:
                    agent_strs.append(f"+{len(room['agents'])-3} more")
                agent_line = f" - Agents: {', '.join(agent_strs)}"

            formatted_lines.append(
                f"{i}. {room['name']} ({room['agent_count']} agent{'s' if room['agent_count'] != 1 else ''}){agent_line}"
            )

        return json.dumps({
            'total_rooms': len(room_list),
            'total_agents': total_agents,
            'rooms': room_list,
            'formatted_text': '\n'.join(formatted_lines)
        })

    except Exception as e:
        logger.exception(f"Error listing voice rooms: {e}")
        return f"Error accessing voice rooms: {str(e)}"


# ============================================================================
# MCP SERVERS LISTING
# ============================================================================

@tool(args_schema=ListMCPServersInput)
def list_mcp_servers(
    category: Optional[str] = None,
    is_connected: Optional[bool] = None,
    is_official: Optional[bool] = None,
    is_preconfigured: Optional[bool] = None,
    name_contains: Optional[str] = None,
    description_contains: Optional[str] = None,
    limit: Optional[int] = 50,
) -> str:
    """
    List available MCP (Model Context Protocol) servers and integrations.

    Use this when the user asks about available integrations, MCP servers,
    connected tools, external services, or what apps they can use.

    Shows both preconfigured (system-wide) servers and user's connected servers.

    All parameters are optional filters to narrow down results.

    Returns:
        A detailed list of MCP servers organized by category with connection status.
    """
    user_context = KNOWLEDGE_BASE_USER_CONTEXT.get()

    if not user_context:
        return "Error: No user context available."

    user = user_context.get('user')
    if not user:
        return "Error: User not authenticated."

    try:
        from mcp.models import MCPServer
        from django.db.models import Q

        # Get preconfigured servers and user's custom servers
        queryset = MCPServer.objects.filter(
            Q(is_preconfigured=True) | Q(user=user)
        ).filter(is_active=True)

        # Apply filters
        if category:
            queryset = queryset.filter(category__iexact=category)
        if is_official is not None:
            queryset = queryset.filter(is_official=is_official)
        if is_preconfigured is not None:
            queryset = queryset.filter(is_preconfigured=is_preconfigured)
        if name_contains:
            queryset = queryset.filter(name__icontains=name_contains)
        if description_contains:
            queryset = queryset.filter(description__icontains=description_contains)

        servers = list(queryset.order_by('category', 'name')[:limit or 50])

        # Post-filter by connection status
        if is_connected is not None:
            servers = [
                s for s in servers
                if (s.user_id == user.id) == is_connected
            ]

        if not servers:
            return json.dumps({
                'total_servers': 0,
                'categories': {},
                'formatted_text': "No MCP servers found matching your criteria. Try adjusting your filters."
            })

        # Organize by category
        categories = {}
        connected_count = 0

        for server in servers:
            cat_key = server.category or 'other'
            cat_display = server.get_category_display() if hasattr(server, 'get_category_display') else cat_key.title()

            if cat_display not in categories:
                categories[cat_display] = {
                    'category_key': cat_key,
                    'servers': []
                }

            server_connected = server.user_id == user.id if server.user_id else False
            if server_connected:
                connected_count += 1

            categories[cat_display]['servers'].append({
                'id': str(server.id),
                'name': server.name,
                'description': server.description[:80] + '...' if server.description and len(server.description) > 80 else server.description,
                'is_preconfigured': server.is_preconfigured,
                'is_connected': server_connected,
                'is_official': server.is_official,
                'npm_package': server.npm_package,
                'icon_url': server.icon_url,
            })

        # Format for LLM (text-only)
        total = len(servers)
        formatted_lines = [f"Available MCP Servers ({total} server{'s' if total != 1 else ''})"]
        formatted_lines.append(f"{connected_count} connected | {total - connected_count} available\n")

        for cat_name, cat_data in categories.items():
            formatted_lines.append(f"\n{cat_name} ({len(cat_data['servers'])})")

            for srv in cat_data['servers'][:5]:
                status = "[connected]" if srv['is_connected'] else ""
                official = "[official]" if srv['is_official'] else ""
                desc = f" - {srv['description']}" if srv['description'] else ""
                formatted_lines.append(f"  - {srv['name']} {status}{official}{desc}")

            if len(cat_data['servers']) > 5:
                formatted_lines.append(f"  (+{len(cat_data['servers'])-5} more)")

        return json.dumps({
            'total_servers': total,
            'connected_count': connected_count,
            'available_count': total - connected_count,
            'categories': {k: v['servers'] for k, v in categories.items()},
            'formatted_text': '\n'.join(formatted_lines)
        })

    except Exception as e:
        logger.exception(f"Error listing MCP servers: {e}")
        return f"Error accessing MCP servers: {str(e)}"


# ============================================================================
# AVAILABLE MODELS LISTING
# ============================================================================

@tool(args_schema=ListAvailableModelsInput)
def list_available_models(
    provider: Optional[str] = None,
    supports_vision: Optional[bool] = None,
    supports_tools: Optional[bool] = None,
    supports_reasoning: Optional[bool] = None,
    min_context_window: Optional[int] = None,
    max_context_window: Optional[int] = None,
    name_contains: Optional[str] = None,
    limit: Optional[int] = None,
) -> str:
    """
    List available AI language models (LLMs) the user can chat with.

    Use this when the user asks about available models, what LLMs they can use,
    AI options, or wants to know their choices for AI assistants.

    All parameters are optional filters to narrow down results.

    Returns:
        A detailed list of available models grouped by provider with capabilities.
    """
    try:
        from llm.models import ModelCatalog

        # Get all available models
        queryset = ModelCatalog.objects.filter(is_available=True)

        # Apply filters
        if provider:
            queryset = queryset.filter(provider__iexact=provider)
        if supports_vision is not None:
            # Vision support is determined by 'image' being in input_modalities
            if supports_vision:
                queryset = queryset.filter(input_modalities__contains=['image'])
            else:
                queryset = queryset.exclude(input_modalities__contains=['image'])
        if supports_tools is not None:
            # supports_tools maps to supports_functions in the model
            queryset = queryset.filter(supports_functions=supports_tools)
        if supports_reasoning is not None:
            queryset = queryset.filter(supports_reasoning=supports_reasoning)
        if min_context_window:
            # context_length maps to max_tokens in the model
            queryset = queryset.filter(max_tokens__gte=min_context_window)
        if max_context_window:
            queryset = queryset.filter(max_tokens__lte=max_context_window)
        if name_contains:
            queryset = queryset.filter(name__icontains=name_contains)

        queryset = queryset.order_by('provider', '-max_tokens')
        if limit:
            queryset = queryset[:limit]
        models = list(queryset)

        if not models:
            return json.dumps({
                'total_models': 0,
                'providers': {},
                'formatted_text': "No models found matching your criteria. Try adjusting your filters."
            })

        # Organize by provider
        providers = {}
        capability_counts = {'vision': 0, 'tools': 0, 'reasoning': 0}

        for model in models:
            model_provider = model.provider or 'Other'

            if model_provider not in providers:
                providers[model_provider] = {
                    'models': []
                }

            # Build capabilities list
            caps = []
            # Vision support is determined by 'image' being in input_modalities
            has_vision = 'image' in (model.input_modalities or [])
            if has_vision:
                caps.append('vision')
                capability_counts['vision'] += 1
            # supports_tools maps to supports_functions
            if model.supports_functions:
                caps.append('tools')
                capability_counts['tools'] += 1
            if model.supports_reasoning:
                caps.append('reasoning')
                capability_counts['reasoning'] += 1

            # Context length formatting (max_tokens in the model)
            ctx = model.max_tokens or 0
            if ctx >= 1000000:
                ctx_str = f"{ctx//1000000}M"
            elif ctx >= 1000:
                ctx_str = f"{ctx//1000}K"
            else:
                ctx_str = str(ctx)

            providers[model_provider]['models'].append({
                'id': model.model_id,
                'name': model.name,
                'provider': model_provider,
                'context_length': ctx,
                'context_str': ctx_str,
                'capabilities': caps,
                'supports_vision': has_vision,
                'supports_tools': model.supports_functions,
                'supports_reasoning': model.supports_reasoning,
            })

        # Format for LLM (text-only)
        total = len(models)
        formatted_lines = [f"Available AI Models ({total} model{'s' if total != 1 else ''})"]

        # Capability summary
        cap_stats = []
        if capability_counts['vision'] > 0:
            cap_stats.append(f"{capability_counts['vision']} with vision")
        if capability_counts['reasoning'] > 0:
            cap_stats.append(f"{capability_counts['reasoning']} with reasoning")
        if capability_counts['tools'] > 0:
            cap_stats.append(f"{capability_counts['tools']} with tools")
        if cap_stats:
            formatted_lines.append(f"{' | '.join(cap_stats)}\n")

        for provider_name, provider_data in providers.items():
            formatted_lines.append(f"\n{provider_name} ({len(provider_data['models'])})")

            for m in provider_data['models'][:6]:
                caps_display = f" [{', '.join(m['capabilities'])}]" if m['capabilities'] else ""
                formatted_lines.append(f"  - {m['name']} ({m['context_str']}){caps_display}")

            if len(provider_data['models']) > 6:
                formatted_lines.append(f"  (+{len(provider_data['models'])-6} more)")

        # Create flat models list for frontend adapter
        all_models = []
        for provider_data in providers.values():
            all_models.extend(provider_data['models'])

        return json.dumps({
            'total_models': total,
            'capability_counts': capability_counts,
            'providers': {k: v['models'] for k, v in providers.items()},
            'models': all_models,  # Flat list for frontend display
            'formatted_text': '\n'.join(formatted_lines)
        })

    except Exception as e:
        logger.exception(f"Error listing models: {e}")
        return f"Error accessing models: {str(e)}"


# ============================================================================
# MODEL COMPARISON
# ============================================================================

@tool(args_schema=CompareModelsInput)
def compare_models(
    preset: Optional[str] = 'balanced',
    model_ids: Optional[list[str]] = None,
    provider: Optional[str] = None,
    must_support_tools: bool = False,
    must_support_vision: bool = False,
    must_support_reasoning: bool = False,
    min_context_tokens: Optional[int] = None,
    max_cost_per_1m_tokens: Optional[float] = None,
    limit: Optional[int] = 10,
) -> str:
    """
    Compare AI models using a weighted scoring algorithm.

    This tool helps users find the best model for their specific needs by scoring
    models across multiple dimensions: cost efficiency, context length, capabilities,
    multimodality, and availability.

    Use presets for common use cases:
    - 'balanced': Equal weight to cost, context, and capabilities (default)
    - 'budget': Minimize costs while maintaining quality
    - 'long_context': Prioritize large context windows (32K+ tokens)
    - 'tool_use': Focus on function calling and structured outputs
    - 'multimodal': Prefer models with image/audio/video support
    - 'coding': Optimized for programming tasks (context + reasoning)

    Returns models ranked by score with the best match highlighted.
    """
    try:
        from llm.models import ModelCatalog
        from llm.comparison_service import comparison_service
        from llm.comparison_config import ComparisonConstraints, get_preset
        from llm.utils import exclude_blacklisted_providers

        # Start with available models that support function calling,
        # excluding blacklisted providers (matches /models page behavior)
        queryset = exclude_blacklisted_providers(
            ModelCatalog.objects.filter(
                is_available=True,
                supports_functions=True,  # Frontend always requires this
            )
        )

        # Filter by specific model IDs if provided
        if model_ids:
            queryset = queryset.filter(model_id__in=model_ids)

        # Apply provider filter
        if provider:
            queryset = queryset.filter(provider__iexact=provider)

        models = list(queryset)

        if not models:
            return json.dumps({
                'total_compared': 0,
                'preset': preset,
                'preset_label': get_preset(preset or 'balanced').label,
                'models': [],
                'best_model': None,
                'formatted_text': "No models found matching your criteria. Try relaxing your constraints."
            })

        # Build additional constraints from tool parameters
        additional_constraints = ComparisonConstraints(
            must_support_functions=must_support_tools,
            must_support_vision=must_support_vision,
            must_support_reasoning=must_support_reasoning,
            min_context_tokens=min_context_tokens,
            max_cost_per_1m_tokens=max_cost_per_1m_tokens,
        )

        # Use the comparison service
        result = comparison_service.compare_with_preset(
            models=models,
            preset_id=preset or 'balanced',
            additional_constraints=additional_constraints,
            limit=limit or 10,
        )

        if result.total_compared == 0:
            return json.dumps({
                'total_compared': 0,
                'preset': result.preset_id,
                'preset_label': result.preset_label,
                'models': [],
                'best_model': None,
                'formatted_text': "No models match your constraints. Try relaxing your filters."
            })

        # Helper to strip provider prefix from model name
        def strip_provider(name: str, provider: str) -> str:
            import re
            pattern = re.compile(rf'^{re.escape(provider)}\s*:\s*', re.IGNORECASE)
            return pattern.sub('', name).strip()

        # Format text output (no emojis)
        formatted_lines = [
            f"Model Comparison ({result.total_compared} models)",
            f"Preset: {result.preset_label}",
            ""
        ]

        if result.best_model:
            best_name = strip_provider(result.best_model.name, result.best_model.provider)
            formatted_lines.append(f"Best Match: {best_name} ({result.best_model.provider})")
            formatted_lines.append(
                f"  Score: {result.best_model.score_percentage:.1f}% | "
                f"Cost: ${result.best_model.cost_per_1m_tokens:.2f}/1M | "
                f"Context: {result.best_model.context_display}"
            )
            formatted_lines.append("")

        formatted_lines.append("Rankings:")
        for i, score in enumerate(result.scores, 1):
            model_name = strip_provider(score.name, score.provider)
            formatted_lines.append(
                f"  {i}. {model_name} - {score.score_percentage:.1f}% "
                f"(${score.cost_per_1m_tokens:.2f}/1M, {score.context_display})"
            )

        # Build response using service result
        response = result.to_dict()
        response['formatted_text'] = '\n'.join(formatted_lines)

        return json.dumps(response)

    except Exception as e:
        logger.exception(f"Error comparing models: {e}")
        return f"Error comparing models: {str(e)}"


# ============================================================================
# CODING AGENTS (SUB-AGENTS) LISTING
# ============================================================================

@tool(args_schema=ListCodingAgentsInput)
def list_coding_agents(
    name_contains: Optional[str] = None,
    model_tier: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: Optional[int] = 30,
) -> str:
    """
    List the user's coding agents (sub-agents) with their configuration.

    Use this when the user asks about their coding agents, sub-agents,
    custom agents, or wants to know what agents they have configured.

    Returns agent name, description, model tier, tools, permissions, and active status.
    Does NOT return the full system prompt (too large). Direct users to the Agents page to view/edit prompts.

    All parameters are optional filters to narrow down results.
    """
    user_context = KNOWLEDGE_BASE_USER_CONTEXT.get()

    if not user_context:
        return "Error: No user context available."

    user = user_context.get('user')
    if not user:
        return "Error: User not authenticated."

    try:
        from code_sessions.models import SubAgent

        queryset = SubAgent.objects.filter(user=user)

        # Apply filters
        if name_contains:
            queryset = queryset.filter(name__icontains=name_contains)
        if model_tier:
            queryset = queryset.filter(model_tier=model_tier)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active)

        agents = queryset.order_by('-updated_at')[:limit or 30]

        if not agents:
            return json.dumps({
                'total_agents': 0,
                'agents': [],
                'formatted_text': "No coding agents found. The user can create agents on the Agents page (sidebar navigation) or import one from a markdown definition."
            })

        agent_list = []
        active_count = 0

        for agent in agents:
            if agent.is_active:
                active_count += 1

            agent_list.append({
                'id': str(agent.id),
                'name': agent.name,
                'description': agent.description,
                'model_tier': agent.model_tier,
                'tools': list(agent.tools) if agent.tools else [],
                'disallowed_tools': list(agent.disallowed_tools) if agent.disallowed_tools else [],
                'max_turns': agent.max_turns,
                'permission_mode': agent.permission_mode,
                'is_active': agent.is_active,
                'updated_at': agent.updated_at.strftime('%Y-%m-%d %H:%M') if agent.updated_at else None,
            })

        # Format for LLM
        formatted_lines = [f"Your Coding Agents ({len(agent_list)} agent{'s' if len(agent_list) != 1 else ''})"]
        formatted_lines.append(f"{active_count} active | {len(agent_list) - active_count} inactive\n")

        for i, agent in enumerate(agent_list, 1):
            status = "[active]" if agent['is_active'] else "[inactive]"
            tools_str = f" tools: {', '.join(agent['tools'])}" if agent['tools'] else ""
            desc = f" - {agent['description'][:80]}" if agent['description'] else ""
            formatted_lines.append(
                f"{i}. {agent['name']} ({agent['model_tier']}) {status}{desc}{tools_str}"
            )

        return json.dumps({
            'total_agents': len(agent_list),
            'active_count': active_count,
            'agents': agent_list,
            'formatted_text': '\n'.join(formatted_lines)
        })

    except Exception as e:
        logger.exception(f"Error listing coding agents: {e}")
        return f"Error accessing coding agents: {str(e)}"


# ============================================================================
# CODING AGENT (SUB-AGENT) UPDATE
# ============================================================================

@tool(args_schema=UpdateCodingAgentInput)
def update_coding_agent(
    agent_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    description: Optional[str] = None,
    model_tier: Optional[str] = None,
    tools: Optional[list[str]] = None,
    disallowed_tools: Optional[list[str]] = None,
    max_turns: Optional[int] = None,
    permission_mode: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> str:
    """
    Update an existing coding agent's (sub-agent's) configuration.

    Identify the agent by agent_id (UUID) or agent_name (unique per user).
    You can update: description, model_tier, tools, disallowed_tools, max_turns, permission_mode, is_active.

    Does NOT update the agent's name (identity) or system_prompt (too risky for LLM to rewrite).
    For system prompt changes, direct the user to the Agents page.

    Use list_coding_agents first to find the agent's ID or name.
    """
    user_context = KNOWLEDGE_BASE_USER_CONTEXT.get()

    if not user_context:
        return "Error: No user context available."

    user = user_context.get('user')
    if not user:
        return "Error: User not authenticated."

    # Must provide either agent_id or agent_name
    if not agent_id and not agent_name:
        return json.dumps({
            'success': False,
            'error': "You must provide either agent_id or agent_name to identify the agent."
        })

    try:
        from code_sessions.models import SubAgent, VALID_AGENT_TOOLS

        # Look up the agent
        if agent_id:
            try:
                agent = SubAgent.objects.get(id=agent_id, user=user)
            except SubAgent.DoesNotExist:
                return json.dumps({
                    'success': False,
                    'error': f"No coding agent found with ID '{agent_id}'. Use list_coding_agents to see available agents."
                })
        else:
            try:
                agent = SubAgent.objects.get(name=agent_name, user=user)
            except SubAgent.DoesNotExist:
                return json.dumps({
                    'success': False,
                    'error': f"No coding agent found with name '{agent_name}'. Use list_coding_agents to see available agents."
                })

        # Collect fields to update
        updates = {}
        changes = []

        if description is not None:
            updates['description'] = description
            changes.append(f"description → \"{description[:60]}{'...' if len(description) > 60 else ''}\"")

        if model_tier is not None:
            valid_tiers = {'fast', 'balanced', 'powerful', 'inherit'}
            if model_tier not in valid_tiers:
                return json.dumps({
                    'success': False,
                    'error': f"Invalid model_tier '{model_tier}'. Must be one of: {', '.join(sorted(valid_tiers))}."
                })
            updates['model_tier'] = model_tier
            changes.append(f"model_tier → {model_tier}")

        if tools is not None:
            for t in tools:
                if t not in VALID_AGENT_TOOLS:
                    return json.dumps({
                        'success': False,
                        'error': f"Invalid tool '{t}'. Must be one of: {', '.join(sorted(VALID_AGENT_TOOLS))}."
                    })
            updates['tools'] = tools
            changes.append(f"tools → [{', '.join(tools)}]")

        if disallowed_tools is not None:
            for t in disallowed_tools:
                if t not in VALID_AGENT_TOOLS:
                    return json.dumps({
                        'success': False,
                        'error': f"Invalid disallowed tool '{t}'. Must be one of: {', '.join(sorted(VALID_AGENT_TOOLS))}."
                    })
            updates['disallowed_tools'] = disallowed_tools
            changes.append(f"disallowed_tools → [{', '.join(disallowed_tools)}]")

        # Check for overlap between tools and disallowed_tools
        final_tools = set(updates.get('tools', agent.tools or []))
        final_disallowed = set(updates.get('disallowed_tools', agent.disallowed_tools or []))
        overlap = final_tools & final_disallowed
        if overlap:
            return json.dumps({
                'success': False,
                'error': f"Tools cannot be both allowed and disallowed: {', '.join(sorted(overlap))}."
            })

        if max_turns is not None:
            if not (1 <= max_turns <= 100):
                return json.dumps({
                    'success': False,
                    'error': f"max_turns must be between 1 and 100, got {max_turns}."
                })
            updates['max_turns'] = max_turns
            changes.append(f"max_turns → {max_turns}")

        if permission_mode is not None:
            valid_modes = {'default', 'plan', 'autoEdit', 'fullAuto'}
            if permission_mode not in valid_modes:
                return json.dumps({
                    'success': False,
                    'error': f"Invalid permission_mode '{permission_mode}'. Must be one of: {', '.join(sorted(valid_modes))}."
                })
            updates['permission_mode'] = permission_mode
            changes.append(f"permission_mode → {permission_mode}")

        if is_active is not None:
            updates['is_active'] = is_active
            changes.append(f"is_active → {is_active}")

        if not updates:
            return json.dumps({
                'success': False,
                'error': "No update fields provided. Specify at least one field to change (description, model_tier, tools, etc.)."
            })

        # Apply updates
        for field, value in updates.items():
            setattr(agent, field, value)
        agent.save(update_fields=list(updates.keys()) + ['updated_at'])

        # Build response
        formatted_lines = [f"Updated agent '{agent.name}':"]
        for change in changes:
            formatted_lines.append(f"  - {change}")

        return json.dumps({
            'success': True,
            'agent': {
                'id': str(agent.id),
                'name': agent.name,
                'description': agent.description,
                'model_tier': agent.model_tier,
                'tools': list(agent.tools) if agent.tools else [],
                'disallowed_tools': list(agent.disallowed_tools) if agent.disallowed_tools else [],
                'max_turns': agent.max_turns,
                'permission_mode': agent.permission_mode,
                'is_active': agent.is_active,
            },
            'changes': changes,
            'formatted_text': '\n'.join(formatted_lines)
        })

    except Exception as e:
        logger.exception(f"Error updating coding agent: {e}")
        return f"Error updating coding agent: {str(e)}"


# ============================================================================
# EXPORT ALL LIST TOOLS
# ============================================================================

LIST_TOOLS = [
    list_sparks,
    list_generated_images,
    list_generated_videos,
    list_voice_rooms,
    list_mcp_servers,
    list_available_models,
    compare_models,
    list_coding_agents,
    update_coding_agent,
]
