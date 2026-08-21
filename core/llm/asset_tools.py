"""
Asset Access Tools for LangChain

Provides tools for LLMs to read and access user assets:
- Images (base64 for vision models, or presigned URLs)
- Videos (presigned URLs and metadata)
- Sparks (code content)
- Knowledge Base Documents (text content)

These tools enable LLMs to analyze, reference, and work with user content.
"""

import base64
import json
import logging
from typing import Optional

from langchain.tools import tool
from pydantic import BaseModel, Field

# Reuse knowledge base context for user info
from .knowledge_base_tools import KNOWLEDGE_BASE_USER_CONTEXT

logger = logging.getLogger(__name__)


# ============================================================================
# INPUT SCHEMAS
# ============================================================================

class GetImageInput(BaseModel):
    """Input schema for get_image tool."""
    asset_id: str = Field(
        description="The UUID of the image asset to retrieve"
    )
    return_base64: bool = Field(
        default=True,
        description="If true, return base64-encoded image data for vision analysis. If false, return a presigned URL."
    )


class GetVideoInput(BaseModel):
    """Input schema for get_video tool."""
    asset_id: str = Field(
        description="The UUID of the video asset to retrieve"
    )


class GetSparkInput(BaseModel):
    """Input schema for get_spark tool."""
    spark_id: str = Field(
        description="The UUID of the spark to retrieve"
    )


class GetDocumentInput(BaseModel):
    """Input schema for get_document tool."""
    document_id: str = Field(
        description="The UUID or filename of the knowledge base document to retrieve"
    )
    max_chars: Optional[int] = Field(
        default=50000,
        ge=1000,
        le=200000,
        description="Maximum characters to return (default 50000, max 200000)"
    )


# ============================================================================
# IMAGE ACCESS
# ============================================================================

@tool(args_schema=GetImageInput)
def get_image(asset_id: str, return_base64: bool = True) -> str:
    """
    Retrieve an image asset for analysis or reference.

    Use this when you need to:
    - Analyze or describe an image the user has uploaded or generated
    - Reference a specific image in the conversation
    - Compare images or extract information from them

    IMPORTANT: Base64 is only returned for images under 100KB to avoid context overflow.
    For larger images, a presigned URL is returned instead. Use return_base64=False
    if you only need to reference the image URL.

    Args:
        asset_id: The UUID of the image asset
        return_base64: If true, return base64 data (only for images <100KB)

    Returns:
        Image data (base64 for small images) or presigned URL with metadata
    """
    user_context = KNOWLEDGE_BASE_USER_CONTEXT.get()

    if not user_context:
        return json.dumps({"error": "No user context available"})

    user = user_context.get('user')
    if not user:
        return json.dumps({"error": "User not authenticated"})

    try:
        from workspaces.models import Asset
        from workspaces.services.asset_storage import get_asset_storage_service

        # Find the asset
        asset = Asset.objects.filter(
            id=asset_id,
            user=user
        ).first()

        if not asset:
            return json.dumps({
                "error": f"Image not found with ID: {asset_id}",
                "hint": "Use list_generated_images to find available images and their IDs"
            })

        # Verify it's an image
        if asset.asset_type not in ['image', 'generated'] and not (asset.mime_type or '').startswith('image/'):
            return json.dumps({
                "error": f"Asset {asset_id} is not an image (type: {asset.asset_type})"
            })

        storage_service = get_asset_storage_service()

        # Build response metadata
        metadata = {
            "asset_id": str(asset.id),
            "filename": asset.filename,
            "mime_type": asset.mime_type,
            "width": asset.width,
            "height": asset.height,
            "size_bytes": asset.size_bytes,
        }

        if asset.generation_prompt:
            metadata["generation_prompt"] = asset.generation_prompt
        if asset.generation_model:
            metadata["generation_model"] = asset.generation_model

        if return_base64:
            # Retrieve and base64 encode the image
            content = storage_service.retrieve_asset(asset)
            if not content:
                return json.dumps({
                    "error": "Failed to retrieve image content",
                    "metadata": metadata
                })

            # Check size limit for base64 - must be conservative to avoid context overflow
            # Base64 increases size by ~33%, and large images can easily exceed model context limits
            # 100KB raw = ~133KB base64 = ~133K tokens (still large but manageable)
            max_size_for_base64 = 100 * 1024  # 100KB limit for inline base64
            if len(content) > max_size_for_base64:
                # Fall back to presigned URL for large images
                presigned_url = storage_service.get_presigned_url(asset, expiration=3600)
                size_kb = len(content) / 1024
                return json.dumps({
                    "note": f"Image is {size_kb:.0f}KB - too large for inline base64 (limit 100KB). Use the URL to reference the image.",
                    "url": presigned_url,
                    "metadata": metadata
                })

            # Return base64 encoded image (only for small images)
            b64_data = base64.b64encode(content).decode('utf-8')
            return json.dumps({
                "image_base64": b64_data,
                "data_url": f"data:{asset.mime_type};base64,{b64_data}",
                "metadata": metadata,
                "note": "Base64 data included for vision analysis. For larger images, use return_base64=False."
            })

        else:
            # Return presigned URL
            presigned_url = storage_service.get_presigned_url(asset, expiration=3600)

            if not presigned_url:
                # Fallback to internal URL if presigned not available
                presigned_url = f"/api/workspaces/assets/{asset_id}/download/"

            return json.dumps({
                "url": presigned_url,
                "metadata": metadata
            })

    except Exception as e:
        logger.exception(f"Error retrieving image: {e}")
        return json.dumps({"error": f"Failed to retrieve image: {str(e)}"})


# ============================================================================
# VIDEO ACCESS
# ============================================================================

@tool(args_schema=GetVideoInput)
def get_video(asset_id: str) -> str:
    """
    Retrieve a video asset's metadata and playback URL.

    Use this when you need to:
    - Get information about a video the user has generated
    - Provide a playback link for a video
    - Reference video details in the conversation

    Note: Videos cannot be directly analyzed by the LLM, but metadata
    and presigned URLs for playback are provided.

    Args:
        asset_id: The UUID of the video asset

    Returns:
        Video metadata and presigned URL for playback
    """
    user_context = KNOWLEDGE_BASE_USER_CONTEXT.get()

    if not user_context:
        return json.dumps({"error": "No user context available"})

    user = user_context.get('user')
    if not user:
        return json.dumps({"error": "User not authenticated"})

    try:
        from workspaces.models import Asset
        from workspaces.services.asset_storage import get_asset_storage_service

        # Find the asset
        asset = Asset.objects.filter(
            id=asset_id,
            user=user
        ).first()

        if not asset:
            return json.dumps({
                "error": f"Video not found with ID: {asset_id}",
                "hint": "Use list_generated_videos to find available videos and their IDs"
            })

        # Verify it's a video
        if asset.asset_type != 'video' and not (asset.mime_type or '').startswith('video/'):
            return json.dumps({
                "error": f"Asset {asset_id} is not a video (type: {asset.asset_type})"
            })

        storage_service = get_asset_storage_service()

        # Generate presigned URL for playback
        presigned_url = storage_service.get_presigned_url(asset, expiration=3600)

        if not presigned_url:
            presigned_url = f"/api/workspaces/assets/{asset_id}/download/"

        # Format duration
        duration_str = None
        if asset.duration_seconds:
            if asset.duration_seconds < 60:
                duration_str = f"{asset.duration_seconds:.1f}s"
            else:
                mins = int(asset.duration_seconds // 60)
                secs = int(asset.duration_seconds % 60)
                duration_str = f"{mins}:{secs:02d}"

        return json.dumps({
            "url": presigned_url,
            "metadata": {
                "asset_id": str(asset.id),
                "filename": asset.filename,
                "mime_type": asset.mime_type,
                "width": asset.width,
                "height": asset.height,
                "duration_seconds": asset.duration_seconds,
                "duration_formatted": duration_str,
                "size_bytes": asset.size_bytes,
                "size_mb": round(asset.size_bytes / (1024 * 1024), 2) if asset.size_bytes else None,
                "generation_prompt": asset.generation_prompt,
            }
        })

    except Exception as e:
        logger.exception(f"Error retrieving video: {e}")
        return json.dumps({"error": f"Failed to retrieve video: {str(e)}"})


# ============================================================================
# SPARK ACCESS
# ============================================================================

@tool(args_schema=GetSparkInput)
def get_spark(spark_id: str) -> str:
    """
    Retrieve a Spark's code and metadata.

    Use this when you need to:
    - Read the code of an existing spark to understand or modify it
    - Reference a spark's implementation details
    - Update or create a new version of a spark

    Args:
        spark_id: The UUID of the spark

    Returns:
        Spark code, framework, dependencies, and metadata
    """
    user_context = KNOWLEDGE_BASE_USER_CONTEXT.get()

    if not user_context:
        return json.dumps({"error": "No user context available"})

    user = user_context.get('user')
    if not user:
        return json.dumps({"error": "User not authenticated"})

    try:
        from sparks.models import Spark

        # Find the spark
        spark = Spark.objects.filter(
            id=spark_id,
            user=user
        ).first()

        if not spark:
            return json.dumps({
                "error": f"Spark not found with ID: {spark_id}",
                "hint": "Use list_sparks to find available sparks and their IDs"
            })

        # Get code content
        code = spark.code
        if not code and spark.r2_key:
            # Code stored in R2, need to retrieve it
            try:
                from workspaces.services import get_storage_service
                storage = get_storage_service()
                code_bytes = storage._download_from_r2(spark.r2_key)
                if code_bytes:
                    code = code_bytes.decode('utf-8')
            except Exception as e:
                logger.warning(f"Failed to retrieve spark code from R2: {e}")

        return json.dumps({
            "spark_id": str(spark.id),
            "title": spark.title,
            "framework": spark.framework,
            "version": spark.version,
            "code": code,
            "dependencies": spark.dependencies or [],
            "metadata": {
                "created_at": spark.created_at.isoformat() if spark.created_at else None,
                "updated_at": spark.updated_at.isoformat() if spark.updated_at else None,
                "code_length": len(code) if code else 0,
            }
        })

    except Exception as e:
        logger.exception(f"Error retrieving spark: {e}")
        return json.dumps({"error": f"Failed to retrieve spark: {str(e)}"})


# ============================================================================
# DOCUMENT ACCESS
# ============================================================================

@tool(args_schema=GetDocumentInput)
def get_document(document_id: str, max_chars: int = 50000) -> str:
    """
    Retrieve the full content of a knowledge base document.

    Use this when you need to:
    - Read the complete text of a document (not just search results)
    - Analyze or summarize an entire document
    - Reference specific sections that semantic search might miss

    For searching within documents, use query_knowledge_base instead.
    Use this tool when you need the full document content.

    Args:
        document_id: The UUID or filename of the document
        max_chars: Maximum characters to return (default 50000)

    Returns:
        Document content and metadata
    """
    user_context = KNOWLEDGE_BASE_USER_CONTEXT.get()

    if not user_context:
        return json.dumps({"error": "No user context available"})

    user = user_context.get('user')
    if not user:
        return json.dumps({"error": "User not authenticated"})

    try:
        from knowledge_base.models import KnowledgeDocument, KnowledgeChunk

        # Try to find by ID first, then by filename
        document = None
        try:
            from uuid import UUID
            UUID(document_id)  # Validate UUID format
            document = KnowledgeDocument.objects.filter(
                id=document_id,
                user=user
            ).first()
        except (ValueError, TypeError):
            # Not a UUID, try filename
            document = KnowledgeDocument.objects.filter(
                filename__iexact=document_id,
                user=user
            ).first()

        if not document:
            return json.dumps({
                "error": f"Document not found: {document_id}",
                "hint": "Use list_knowledge_base_documents to find available documents"
            })

        if document.status != 'ready':
            return json.dumps({
                "error": f"Document is not ready (status: {document.status})",
                "hint": "The document may still be processing"
            })

        # Get all chunks for this document, ordered by index
        chunks = KnowledgeChunk.objects.filter(
            document=document
        ).order_by('chunk_index')

        # Reconstruct full content from chunks
        full_content = '\n\n'.join(chunk.content for chunk in chunks)

        # Truncate if necessary
        truncated = False
        if len(full_content) > max_chars:
            full_content = full_content[:max_chars]
            truncated = True

        return json.dumps({
            "document_id": str(document.id),
            "filename": document.filename,
            "document_type": document.document_type,
            "content": full_content,
            "truncated": truncated,
            "metadata": {
                "total_chars": len(full_content),
                "chunk_count": chunks.count(),
                "file_size_bytes": document.file_size_bytes,
                "uploaded_at": document.uploaded_at.isoformat() if document.uploaded_at else None,
            }
        })

    except Exception as e:
        logger.exception(f"Error retrieving document: {e}")
        return json.dumps({"error": f"Failed to retrieve document: {str(e)}"})


# ============================================================================
# WORKSPACE INTEGRATION
# ============================================================================

class ExportAssetInput(BaseModel):
    """Input schema for export_asset tool."""
    asset_id: str = Field(
        description="The UUID of the asset (image/video) to export"
    )
    format: str = Field(
        default="url",
        description="Export format: 'url' for permanent download URL, 'base64' for data URL (images <100KB only)"
    )


@tool(args_schema=ExportAssetInput)
def export_asset(asset_id: str, format: str = "url") -> str:
    """
    Export an asset for use in code, web pages, or external applications.

    Use this when you need to:
    - Get a permanent URL for an image/video to use in HTML, markdown, or code
    - Embed a small image as a base64 data URL in a component
    - Share an asset with a downloadable link

    The permanent URL format is: /api/workspaces/assets/{asset_id}/download/
    This URL requires authentication and works within the application.

    For public sharing, the presigned URL (valid for 1 hour) can be used externally.

    Args:
        asset_id: The UUID of the asset
        format: 'url' for download URLs, 'base64' for inline data (small images only)

    Returns:
        URLs and/or base64 data for the asset
    """
    user_context = KNOWLEDGE_BASE_USER_CONTEXT.get()

    if not user_context:
        return json.dumps({"error": "No user context available"})

    user = user_context.get('user')
    if not user:
        return json.dumps({"error": "User not authenticated"})

    try:
        from workspaces.models import Asset
        from workspaces.services.asset_storage import get_asset_storage_service

        # Find the asset
        asset = Asset.objects.filter(
            id=asset_id,
            user=user
        ).first()

        if not asset:
            return json.dumps({
                "error": f"Asset not found with ID: {asset_id}",
                "hint": "Use list_generated_images or list_generated_videos to find available assets"
            })

        storage_service = get_asset_storage_service()

        # Determine asset type
        is_video = asset.mime_type and asset.mime_type.startswith('video/')
        asset_type = 'video' if is_video else 'image'

        # Build response with URLs
        result = {
            "asset_id": str(asset.id),
            "asset_type": asset_type,
            "filename": asset.filename,
            "mime_type": asset.mime_type,
            "permanent_url": f"/api/workspaces/assets/{asset.id}/download/",
            "size_bytes": asset.size_bytes,
        }

        # Add dimensions for images
        if asset.width and asset.height:
            result["width"] = asset.width
            result["height"] = asset.height

        # Generate presigned URL for external access
        presigned_url = storage_service.get_presigned_url(asset, expiration=3600)
        if presigned_url:
            result["presigned_url"] = presigned_url
            result["presigned_expires_in"] = "1 hour"

        # Handle base64 format for small images
        if format == "base64" and not is_video:
            if asset.size_bytes and asset.size_bytes > 100 * 1024:
                result["base64_error"] = f"Image too large for base64 ({asset.size_bytes} bytes > 100KB limit)"
            else:
                content = storage_service.retrieve_asset(asset)
                if content:
                    b64_data = base64.b64encode(content).decode('utf-8')
                    result["data_url"] = f"data:{asset.mime_type};base64,{b64_data}"
                    result["base64_size"] = len(b64_data)

        # Usage hint
        if asset_type == 'image':
            result["usage_html"] = f'<img src="{result["permanent_url"]}" alt="{asset.filename}" />'
            result["usage_markdown"] = f'![{asset.filename}]({result["permanent_url"]})'
        else:
            result["usage_html"] = f'<video src="{result["permanent_url"]}" controls></video>'

        return json.dumps(result)

    except Exception as e:
        logger.exception(f"Error exporting asset: {e}")
        return json.dumps({"error": f"Failed to export asset: {str(e)}"})


class SaveAssetToWorkspaceInput(BaseModel):
    """Input schema for save_asset_to_workspace tool."""
    asset_id: str = Field(
        description="The UUID of the asset (image) to save to workspace"
    )
    path: str = Field(
        description="Destination path in the workspace (e.g., 'public/images/logo.png')"
    )


@tool(args_schema=SaveAssetToWorkspaceInput)
async def save_asset_to_workspace(asset_id: str, path: str) -> str:
    """
    Save an image asset to the workspace filesystem.

    Use this when you need to:
    - Add a generated image to a project's public assets folder
    - Save an uploaded image to the workspace for use in code
    - Make an image file available in the project structure

    LIMITATIONS:
    - Only works for images under 1MB (base64 encoding constraint)
    - Videos are not supported (too large for workspace storage)
    - The file is written as binary data

    Args:
        asset_id: The UUID of the image asset
        path: Destination path in the workspace (e.g., 'public/images/logo.png')

    Returns:
        Success status and file path
    """
    user_context = KNOWLEDGE_BASE_USER_CONTEXT.get()

    if not user_context:
        return json.dumps({"error": "No user context available"})

    user = user_context.get('user')
    if not user:
        return json.dumps({"error": "User not authenticated"})

    try:
        from asgiref.sync import sync_to_async
        from workspaces.models import Asset
        from workspaces.services.asset_storage import get_asset_storage_service
        from .langchain_file_tools import _get_context

        # Get file tools context for workspace access
        file_context = _get_context()
        if not file_context:
            return json.dumps({
                "error": "Workspace not available",
                "hint": "File tools must be enabled for this feature"
            })

        # Find the asset (wrap ORM call in sync_to_async)
        @sync_to_async
        def get_asset():
            return Asset.objects.filter(
                id=asset_id,
                user=user
            ).first()

        asset = await get_asset()

        if not asset:
            return json.dumps({
                "error": f"Asset not found with ID: {asset_id}",
                "hint": "Use list_generated_images to find available images"
            })

        # Check if it's a video (not supported due to size)
        if asset.mime_type and asset.mime_type.startswith('video/'):
            return json.dumps({
                "error": "Videos cannot be saved to workspace (too large)",
                "hint": "Use export_asset to get a URL for the video instead"
            })

        # Get presigned URL for the asset (same approach as sparks)
        @sync_to_async
        def get_presigned_url():
            storage_service = get_asset_storage_service()
            return storage_service.get_presigned_url(asset, expiration=3600)

        presigned_url = await get_presigned_url()

        if not presigned_url:
            return json.dumps({
                "error": "Failed to get download URL for asset",
                "hint": "Use export_asset to get a URL instead"
            })

        # Use execute_code to download the file directly in the sandbox via curl
        # curl works better than urllib through the egress proxy
        download_code = f'''import os
import subprocess

# Ensure directory exists
dir_path = os.path.dirname("{path}")
if dir_path:
    os.makedirs(dir_path, exist_ok=True)

# Download from presigned URL using curl (works through egress proxy)
result = subprocess.run(
    ["curl", "-s", "-o", "{path}", "{presigned_url}"],
    capture_output=True,
    text=True
)

# Verify file exists
if os.path.exists("{path}"):
    size = os.path.getsize("{path}")
    print(f"Downloaded {{size}} bytes to {path}")
else:
    print(f"ERROR: Download failed - {{result.stderr}}")
'''

        result = await file_context._make_request("/execute", {
            "code": download_code,
            "language": "python",
            "timeout": 60
        })

        # Check execution result
        output = result.get("output", "")
        if "Downloaded" in output and "bytes to" in output:
            return json.dumps({
                "success": True,
                "path": path,
                "filename": asset.filename,
                "size_bytes": asset.size_bytes,
                "message": f"Image saved to workspace at {path}"
            })
        else:
            error = result.get("error") or output or "Download failed"
            return json.dumps({
                "success": False,
                "error": error,
                "hint": "Use export_asset to get a URL instead",
                "permanent_url": f"/api/workspaces/assets/{asset.id}/download/"
            })

    except Exception as e:
        logger.exception(f"Error saving asset to workspace: {e}")
        return json.dumps({"error": f"Failed to save asset: {str(e)}"})


# ============================================================================
# EXPORT ALL ASSET TOOLS
# ============================================================================

ASSET_TOOLS = [
    get_image,
    get_video,
    get_spark,
    get_document,
    export_asset,
    save_asset_to_workspace,
]
