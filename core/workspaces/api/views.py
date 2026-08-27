"""
Workspace API views for orchestrator integration.

The orchestrator calls these endpoints to save/restore workspace files
during container lifecycle events.

Storage is handled by the WorkspaceStorageService which automatically
routes files to the appropriate backend:
- Small files (<256KB): PostgreSQL inline
- Large files (>=256KB): Cloudflare R2
"""
import base64
import hashlib
import logging
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from authentication.models import User
from workspaces.models import Workspace, WorkspaceFile, SyncState, Asset, AssetShareLink
from workspaces.services.workspace_storage import get_storage_service
from workspaces.services.asset_storage import get_asset_storage_service
from workspaces.utils import apply_watermark
from security import require_service_auth
from .serializers import (
    WorkspaceSerializer,
    AssetSerializer,
    AssetUploadSerializer,
    GalleryAssetSerializer,
    AssetShareLinkSerializer,
    CreateShareLinkSerializer,
    ShareLinkListSerializer,
)

logger = logging.getLogger(__name__)

# Get the storage service singletons
storage_service = get_storage_service()
asset_storage_service = get_asset_storage_service()


@api_view(['POST'])
@permission_classes([AllowAny])  # Auth handled by @require_service_auth
@require_service_auth
def save_workspace(request: Request) -> Response:
    """
    Save workspace files from orchestrator.

    Expected payload:
    {
        "user_id": "uuid",
        "chat_id": "uuid",
        "files": [
            {
                "path": "src/main.py",
                "content_base64": "...",
                "size": 1234,
                "sha256": "...",
                "mime_type": "text/x-python"
            }
        ]
    }
    """
    start = datetime.now()
    errors = []
    files_synced = 0
    bytes_synced = 0
    files_deleted = 0

    try:
        user_id = UUID(request.data.get('user_id'))
        chat_id = UUID(request.data.get('chat_id'))
        files = request.data.get('files', [])
    except (ValueError, TypeError) as e:
        return Response(
            {'error': f'Invalid request: {e}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Verify user exists
        if not User.objects.filter(id=user_id).exists():
            return Response(
                {'error': f'User {user_id} not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get or create workspace
        workspace, created = Workspace.objects.get_or_create(
            user_id=user_id,
            chat_id=chat_id,
        )
        if created:
            logger.info(f"Created workspace for user={user_id}, chat={chat_id}")

        # Get or create sync state
        sync_state, _ = SyncState.objects.get_or_create(workspace=workspace)
        sync_state.status = SyncState.STATUS_SYNCING
        sync_state.direction = SyncState.DIRECTION_SAVE
        sync_state.started_at = datetime.now()
        sync_state.save()

        # Get existing files for diff
        existing_files = {f.path: f for f in workspace.files.all()}
        incoming_paths = {f.get('path') for f in files if f.get('path')}

        # Delete files that are no longer present
        for path, existing_file in existing_files.items():
            if path not in incoming_paths:
                try:
                    # If R2 storage, we'd delete from R2 here
                    # For now, just delete from DB
                    existing_file.delete()
                    files_deleted += 1
                except Exception as e:
                    errors.append(f"Delete {path}: {str(e)}")

        # Save incoming files
        for file_data in files:
            try:
                path = file_data.get('path')
                content_b64 = file_data.get('content_base64')
                sha256 = file_data.get('sha256', '')
                mime_type = file_data.get('mime_type')

                if not path or not content_b64:
                    errors.append("Missing path or content for file")
                    continue

                # Check if file unchanged
                existing = existing_files.get(path)
                if existing and existing.sha256_hash == sha256:
                    continue  # Skip unchanged

                # Decode content
                try:
                    content = base64.b64decode(content_b64)
                except Exception:
                    errors.append(f"{path}: Invalid base64 content")
                    continue

                # Verify hash if provided
                if sha256:
                    computed_hash = hashlib.sha256(content).hexdigest()
                    if computed_hash != sha256:
                        errors.append(f"{path}: Hash mismatch")
                        continue

                # Use storage service to determine storage type and store content
                storage_result = storage_service.store_file(
                    user_id=str(user_id),
                    chat_id=str(chat_id),
                    content=content,
                    content_hash=sha256,
                    mime_type=mime_type,
                )

                storage_type = storage_result.storage_type
                file_content = storage_result.content
                r2_bucket = storage_result.r2_bucket
                r2_key = storage_result.r2_key

                if storage_type == WorkspaceFile.STORAGE_R2:
                    logger.info(f"Stored large file in R2: {path} ({len(content)} bytes)")

                # Upsert file
                WorkspaceFile.objects.update_or_create(
                    workspace=workspace,
                    path=path,
                    defaults={
                        'filename': path.split('/')[-1],
                        'mime_type': mime_type,
                        'size_bytes': len(content),
                        'sha256_hash': sha256 or hashlib.sha256(content).hexdigest(),
                        'storage_type': storage_type,
                        'content': file_content,
                        'r2_bucket': r2_bucket,
                        'r2_key': r2_key,
                    }
                )

                files_synced += 1
                bytes_synced += len(content)

            except Exception as e:
                errors.append(f"{file_data.get('path', 'unknown')}: {str(e)}")
                logger.error(f"Error saving file: {e}")

        # Update workspace stats
        workspace.update_stats()

        # Update sync state
        sync_state.status = SyncState.STATUS_IDLE if not errors else SyncState.STATUS_ERROR
        sync_state.files_synced = files_synced
        sync_state.bytes_synced = bytes_synced
        sync_state.completed_at = datetime.now()
        sync_state.error_message = '; '.join(errors) if errors else None
        sync_state.save()

    except Exception as e:
        logger.error(f"Workspace save failed: {e}")
        errors.append(str(e))

    duration = int((datetime.now() - start).total_seconds() * 1000)

    result = {
        'success': len(errors) == 0,
        'files_synced': files_synced,
        'bytes_synced': bytes_synced,
        'files_deleted': files_deleted,
        'errors': errors,
        'duration_ms': duration,
    }

    logger.info(
        f"Workspace save: user={user_id}, chat={chat_id}, "
        f"synced={files_synced}, deleted={files_deleted}, "
        f"bytes={bytes_synced}, errors={len(errors)}, duration={duration}ms"
    )

    return Response(result, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])  # Auth handled by @require_service_auth
@require_service_auth
def restore_workspace(request: Request, user_id: str, chat_id: str) -> Response:
    """
    Restore workspace files for orchestrator.

    Returns all files with their content (base64 encoded).
    """
    start = datetime.now()

    try:
        user_uuid = UUID(user_id)
        chat_uuid = UUID(chat_id)
    except ValueError:
        return Response(
            {'error': 'Invalid UUID format'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        workspace = Workspace.objects.filter(
            user_id=user_uuid,
            chat_id=chat_uuid
        ).first()

        if not workspace:
            # No workspace yet - return empty
            return Response({
                'success': True,
                'files': [],
                'duration_ms': 0,
            })

        # Update sync state
        sync_state, _ = SyncState.objects.get_or_create(workspace=workspace)
        sync_state.status = SyncState.STATUS_SYNCING
        sync_state.direction = SyncState.DIRECTION_RESTORE
        sync_state.started_at = datetime.now()
        sync_state.save()

        # Get all files
        files = []
        total_bytes = 0

        for wf in workspace.files.all():
            try:
                # Use storage service to retrieve content
                content = storage_service.retrieve_file(wf)

                if content:
                    files.append({
                        'path': wf.path,
                        'content_base64': base64.b64encode(content).decode('utf-8'),
                        'size': wf.size_bytes,
                        'sha256': wf.sha256_hash,
                        'mime_type': wf.mime_type,
                    })
                    total_bytes += wf.size_bytes

            except Exception as e:
                logger.error(f"Error restoring file {wf.path}: {e}")

        # Update workspace
        workspace.last_accessed_at = datetime.now()
        workspace.save(update_fields=['last_accessed_at'])

        # Update sync state
        sync_state.status = SyncState.STATUS_IDLE
        sync_state.files_synced = len(files)
        sync_state.bytes_synced = total_bytes
        sync_state.completed_at = datetime.now()
        sync_state.save()

        duration = int((datetime.now() - start).total_seconds() * 1000)

        logger.info(
            f"Workspace restore: user={user_id}, chat={chat_id}, "
            f"files={len(files)}, bytes={total_bytes}, duration={duration}ms"
        )

        return Response({
            'success': True,
            'files': files,
            'duration_ms': duration,
        })

    except Exception as e:
        logger.error(f"Workspace restore failed: {e}")
        return Response(
            {'success': False, 'error': str(e), 'files': [], 'duration_ms': 0},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([AllowAny])  # Auth handled by @require_service_auth
@require_service_auth
def workspace_info(request: Request, user_id: str, chat_id: str) -> Response:
    """Get workspace information."""
    try:
        user_uuid = UUID(user_id)
        chat_uuid = UUID(chat_id)
    except ValueError:
        return Response(
            {'error': 'Invalid UUID format'},
            status=status.HTTP_400_BAD_REQUEST
        )

    workspace = Workspace.objects.filter(
        user_id=user_uuid,
        chat_id=chat_uuid
    ).prefetch_related('files').first()

    if not workspace:
        return Response({'exists': False})

    serializer = WorkspaceSerializer(workspace)
    data = serializer.data
    data['exists'] = True

    return Response(data)


@api_view(['DELETE'])
@permission_classes([AllowAny])  # Auth handled by @require_service_auth
@require_service_auth
def delete_workspace(request: Request, user_id: str, chat_id: str) -> Response:
    """Delete a workspace and all its files."""
    try:
        user_uuid = UUID(user_id)
        chat_uuid = UUID(chat_id)
    except ValueError:
        return Response(
            {'error': 'Invalid UUID format'},
            status=status.HTTP_400_BAD_REQUEST
        )

    deleted, _ = Workspace.objects.filter(
        user_id=user_uuid,
        chat_id=chat_uuid
    ).delete()

    return Response({'deleted': deleted > 0})


@api_view(['GET'])
@permission_classes([AllowAny])  # Auth handled by @require_service_auth
@require_service_auth
def list_user_workspaces(request: Request, user_id: str) -> Response:
    """List all workspaces for a user."""
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        return Response(
            {'error': 'Invalid UUID format'},
            status=status.HTTP_400_BAD_REQUEST
        )

    workspaces = Workspace.objects.filter(user_id=user_uuid).order_by('-last_accessed_at')

    return Response({
        'workspaces': [
            {
                'id': str(w.id),
                'chat_id': str(w.chat_id),
                'name': w.name,
                'file_count': w.file_count,
                'total_size_bytes': w.total_size_bytes,
                'last_accessed_at': w.last_accessed_at.isoformat(),
            }
            for w in workspaces
        ]
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def storage_health(request: Request) -> Response:
    """
    Health check endpoint for storage backends.

    Unauthenticated callers get only the overall ok/degraded status —
    bucket names, endpoint URLs and backend error messages disclose
    infrastructure layout. Full per-backend details require an admin
    (staff) user, matching DRF's IsAdminUser semantics.
    """
    # Check R2 connection
    success, message = storage_service.check_r2_connection()
    overall = 'ok' if success else 'degraded'

    is_admin = bool(
        request.user
        and request.user.is_authenticated
        and cast(User, request.user).is_staff
    )
    if not is_admin:
        return Response({'overall': overall})

    health = {
        'postgresql': {
            'status': 'ok',
            'message': 'PostgreSQL is always available for inline storage',
        },
        'r2': {
            'status': 'ok' if success else 'unavailable',
            'message': message,
            'configured': storage_service.config.r2_enabled,
            'bucket': storage_service.config.bucket_name if storage_service.config.r2_enabled else None,
            'endpoint': storage_service.config.effective_endpoint_url if storage_service.config.r2_enabled else None,
        },
        'overall': overall,
        'inline_threshold_bytes': storage_service.config.inline_threshold,
    }

    return Response(health)


# ─────────────────────────────────────────────────────────
# Asset API Endpoints (for conversation attachments)
# ─────────────────────────────────────────────────────────

@api_view(['POST'])
def upload_asset(request: Request) -> Response:
    """
    Upload a new asset (conversation attachment).

    Security measures:
    1. File size validation in serializer (per asset type limits)
    2. Magic byte validation to verify actual file content
    3. Image sanitization to strip EXIF metadata and prevent polyglot attacks
    4. Filename sanitization to prevent path traversal/header injection

    Expected payload:
    {
        "chat_id": "uuid",
        "message_id": "uuid" (optional),
        "filename": "image.png",
        "mime_type": "image/png",
        "asset_type": "image",
        "content_base64": "...",
        "width": 800 (optional),
        "height": 600 (optional)
    }

    Returns:
    {
        "success": true,
        "asset": { ...asset metadata... }
    }
    """
    # Import security utilities
    from security import (
        validate_file_type,
        sanitize_image,
        get_image_format_from_mime,
        ALLOWED_IMAGE_TYPES,
        ALLOWED_VIDEO_TYPES,
    )

    serializer = AssetUploadSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {'success': False, 'error': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    data = serializer.validated_data
    user = cast(User, request.user)

    try:
        # Decode base64 content
        try:
            content = base64.b64decode(data['content_base64'])
        except Exception:
            return Response(
                {'success': False, 'error': 'Invalid base64 content'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Security: Validate actual file content using magic bytes
        # Don't trust the claimed mime_type from the client
        claimed_mime = data['mime_type']
        filename = data['filename']
        asset_type = data['asset_type']

        detected_mime, detected_category = validate_file_type(
            content,
            claimed_mime_type=claimed_mime,
            filename=filename,
        )

        # Verify the detected type is allowed
        if detected_mime is None:
            # Unknown file type - check if it's a text file or other allowed type
            # For safety, only allow explicitly detected types
            logger.warning(
                f"Unknown file type: claimed={claimed_mime}, filename={filename}, "
                f"bytes={content[:16].hex() if content else 'empty'}"
            )
            # Allow the upload but log warning - some generated content may not have standard headers
            detected_mime = claimed_mime
            detected_category = 'file'

        # For images: Validate against allowed types and sanitize
        final_content = content
        final_mime = detected_mime or claimed_mime

        if detected_category == 'image' or asset_type in (Asset.TYPE_IMAGE, Asset.TYPE_GENERATED):
            if detected_mime and detected_mime not in ALLOWED_IMAGE_TYPES:
                return Response(
                    {'success': False, 'error': f'Image type not allowed: {detected_mime}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Sanitize image: re-encode to strip metadata and validate
            if detected_mime in ALLOWED_IMAGE_TYPES:
                try:
                    target_format = get_image_format_from_mime(detected_mime)
                    final_content, final_mime = sanitize_image(
                        content,
                        target_format=target_format,
                        max_dimension=4096,  # Allow larger images than avatars
                        quality=100,  # Preserve quality for user uploads
                    )
                    logger.debug(f"Image sanitized: {len(content)} -> {len(final_content)} bytes")
                except ValueError as e:
                    return Response(
                        {'success': False, 'error': f'Invalid image: {e}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

        # For videos: Just validate type (no sanitization - too expensive)
        elif detected_category == 'video' or asset_type == Asset.TYPE_VIDEO:
            if detected_mime and detected_mime not in ALLOWED_VIDEO_TYPES:
                return Response(
                    {'success': False, 'error': f'Video type not allowed: {detected_mime}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        content_size = len(final_content)
        sha256_hash = hashlib.sha256(final_content).hexdigest()

        # Check for duplicate (same content in same chat)
        existing = asset_storage_service.check_duplicate(
            sha256_hash=sha256_hash,
            user_id=str(user.id),
            chat_id=str(data['chat_id']),
        )
        if existing:
            # Return existing asset instead of creating duplicate
            logger.info(f"Asset deduplication hit: {sha256_hash[:12]}...")
            return Response({
                'success': True,
                'asset': AssetSerializer(existing, context={'request': request}).data,
                'deduplicated': True,
            })

        # Create asset record first to get ID
        asset = Asset(
            user=user,
            chat_id=data['chat_id'],
            message_id=data.get('message_id'),
            asset_type=asset_type,
            filename=filename,  # Already sanitized by serializer
            mime_type=final_mime,  # Use detected/sanitized mime type
            size_bytes=content_size,
            sha256_hash=sha256_hash,
            width=data.get('width'),
            height=data.get('height'),
            duration_seconds=data.get('duration_seconds'),
            generation_prompt=data.get('generation_prompt'),
            generation_model=data.get('generation_model'),
        )
        asset.save()

        # Store content using tiered storage
        storage_result = asset_storage_service.store_asset(
            user_id=str(user.id),
            chat_id=str(data['chat_id']),
            asset_id=str(asset.id),
            content=final_content,  # Use sanitized content
            mime_type=final_mime,
        )

        # Update asset with storage details
        asset.storage_type = storage_result.storage_type
        asset.r2_bucket = storage_result.r2_bucket
        asset.r2_key = storage_result.r2_key
        if storage_result.storage_type == Asset.STORAGE_INLINE:
            asset.content = storage_result.content
        asset.save()

        logger.info(
            f"Asset uploaded: id={asset.id}, type={asset.asset_type}, "
            f"size={content_size}, storage={storage_result.storage_type}, "
            f"mime={final_mime}"
        )

        return Response({
            'success': True,
            'asset': AssetSerializer(asset, context={'request': request}).data,
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.error(f"Asset upload failed: {e}")
        return Response(
            {'success': False, 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
def download_asset(request: Request, asset_id: str) -> Response | HttpResponse:
    """
    Download asset content.

    For small assets or inline storage: Returns the binary content directly.
    For large assets in R2 (especially videos): Returns a presigned URL for redirect.

    Query params:
        redirect: If 'true', redirect to presigned URL (default for videos)
        direct: If 'true', always stream through server (no redirect)
        watermark: If 'true', apply watermark to images
        watermark_position: Position for watermark (bottom-right, bottom-left, top-right, top-left)
    """
    try:
        asset_uuid = UUID(asset_id)
    except ValueError:
        return Response(
            {'error': 'Invalid asset ID format'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Get asset (must belong to requesting user)
    asset = Asset.objects.filter(
        id=asset_uuid,
        user=request.user,
    ).first()

    if not asset:
        return Response(
            {'error': 'Asset not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Check watermark settings from query params
    watermark_enabled = request.query_params.get('watermark', '').lower() == 'true'
    watermark_position = request.query_params.get('watermark_position', 'bottom-right')
    if watermark_position not in ['bottom-right', 'bottom-left', 'top-right', 'top-left']:
        watermark_position = 'bottom-right'

    # Check if client wants direct streaming (no redirect)
    force_direct = request.query_params.get('direct', '').lower() == 'true'

    # Only redirect to presigned URL for videos (they're large and benefit from direct R2 streaming)
    # Images should be streamed through server to avoid CORS issues with axios blob fetch
    # Also don't redirect if watermark is requested (need to process through server)
    is_video = asset.mime_type and asset.mime_type.startswith('video/')
    is_image = asset.mime_type and asset.mime_type.startswith('image/')
    use_presigned = (
        not force_direct and
        not (watermark_enabled and is_image) and  # Don't redirect if watermark needed
        asset.storage_type == Asset.STORAGE_R2 and
        is_video  # Only videos - images stream through server to avoid CORS
    )

    if use_presigned:
        presigned_url = asset_storage_service.get_presigned_url(asset)
        if presigned_url:
            logger.info(f"Redirecting to presigned URL for asset {asset_id}")
            return HttpResponseRedirect(presigned_url)
        # Fall through to direct streaming if presigned URL fails
        logger.warning(f"Presigned URL failed for asset {asset_id}, falling back to direct")

    # Retrieve and stream content directly
    content = asset_storage_service.retrieve_asset(asset)
    if content is None:
        return Response(
            {'error': 'Failed to retrieve asset content'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    # Apply watermark to images if requested
    output_content = content
    output_mime_type = asset.mime_type
    if watermark_enabled and is_image:
        try:
            watermarked = apply_watermark(content, watermark_position)
            if watermarked:
                output_content = watermarked
                # Watermarked images are always PNG
                output_mime_type = 'image/png'
        except Exception as e:
            logger.warning(f"Failed to apply watermark to download: {e}")
            # Fall back to original content

    # Return binary response
    response = HttpResponse(output_content, content_type=output_mime_type)
    response['Content-Disposition'] = f'inline; filename="{asset.filename}"'
    response['Content-Length'] = len(output_content)

    # Add range support header for videos (browser video player compatibility)
    if is_video:
        response['Accept-Ranges'] = 'bytes'

    return response


@api_view(['GET'])
def get_asset(request: Request, asset_id: str) -> Response:
    """
    Get asset metadata (without content).
    """
    try:
        asset_uuid = UUID(asset_id)
    except ValueError:
        return Response(
            {'error': 'Invalid asset ID format'},
            status=status.HTTP_400_BAD_REQUEST
        )

    asset = Asset.objects.filter(
        id=asset_uuid,
        user=request.user,
    ).first()

    if not asset:
        return Response(
            {'error': 'Asset not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    return Response(AssetSerializer(asset, context={'request': request}).data)


@api_view(['GET'])
def get_asset_presigned_url(request: Request, asset_id: str) -> Response:
    """
    Get a presigned URL for direct access to an asset.

    This is useful for video players that need a direct URL to the media file.
    The URL expires after the specified duration (default 1 hour).

    Query params:
        expiration: URL expiration in seconds (default 3600, max 86400)

    Returns:
        {
            "presigned_url": "https://...",
            "expires_in": 3600,
            "mime_type": "video/mp4",
            "filename": "video.mp4"
        }
    """
    try:
        asset_uuid = UUID(asset_id)
    except ValueError:
        return Response(
            {'error': 'Invalid asset ID format'},
            status=status.HTTP_400_BAD_REQUEST
        )

    asset = Asset.objects.filter(
        id=asset_uuid,
        user=request.user,
    ).first()

    if not asset:
        return Response(
            {'error': 'Asset not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Parse expiration from query params
    try:
        expiration = int(request.query_params.get('expiration', 3600))
        expiration = min(max(expiration, 60), 86400)  # Between 1 min and 24 hours
    except (ValueError, TypeError):
        expiration = 3600

    # Only R2-stored assets support presigned URLs
    if asset.storage_type != Asset.STORAGE_R2:
        return Response(
            {'error': 'Presigned URLs only available for R2-stored assets'},
            status=status.HTTP_400_BAD_REQUEST
        )

    presigned_url = asset_storage_service.get_presigned_url(asset, expiration=expiration)
    if not presigned_url:
        return Response(
            {'error': 'Failed to generate presigned URL'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return Response({
        'presigned_url': presigned_url,
        'expires_in': expiration,
        'mime_type': asset.mime_type,
        'filename': asset.filename,
        'size_bytes': asset.size_bytes,
    })


@api_view(['DELETE'])
def delete_asset(request: Request, asset_id: str) -> Response:
    """
    Delete an asset.
    """
    try:
        asset_uuid = UUID(asset_id)
    except ValueError:
        return Response(
            {'error': 'Invalid asset ID format'},
            status=status.HTTP_400_BAD_REQUEST
        )

    asset = Asset.objects.filter(
        id=asset_uuid,
        user=request.user,
    ).first()

    if not asset:
        return Response(
            {'error': 'Asset not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Delete from R2 if applicable
    asset_storage_service.delete_asset(asset)

    # Delete from database
    asset.delete()

    logger.info(f"Asset deleted: {asset_id}")

    return Response({'success': True, 'deleted': True})


@api_view(['GET'])
def list_chat_assets(request: Request, chat_id: str) -> Response:
    """
    List all assets in a chat.
    """
    try:
        chat_uuid = UUID(chat_id)
    except ValueError:
        return Response(
            {'error': 'Invalid chat ID format'},
            status=status.HTTP_400_BAD_REQUEST
        )

    assets = Asset.objects.filter(
        chat_id=chat_uuid,
        user=request.user,
    ).order_by('-created_at')

    return Response({
        'assets': AssetSerializer(assets, many=True, context={'request': request}).data,
        'count': assets.count(),
    })


@api_view(['GET'])
def list_message_assets(request: Request, message_id: str) -> Response:
    """
    List all assets attached to a specific message.
    """
    try:
        message_uuid = UUID(message_id)
    except ValueError:
        return Response(
            {'error': 'Invalid message ID format'},
            status=status.HTTP_400_BAD_REQUEST
        )

    assets = Asset.objects.filter(
        message_id=message_uuid,
        user=request.user,
    ).order_by('created_at')

    return Response({
        'assets': AssetSerializer(assets, many=True, context={'request': request}).data,
        'count': assets.count(),
    })


@api_view(['GET'])
def list_user_generated_images(request: Request) -> Response:
    """
    List all AI-generated images for the current user across all conversations.

    Query parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 24, max: 100)
    - ordering: Sort order (default: -created_at)

    Returns paginated list of generated images with conversation context.
    """
    # Parse query parameters
    try:
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 24)), 100)
    except (ValueError, TypeError):
        page = 1
        page_size = 24

    ordering = request.query_params.get('ordering', '-created_at')
    if ordering not in ['-created_at', 'created_at', '-size_bytes', 'size_bytes']:
        ordering = '-created_at'

    search = request.query_params.get('search', '').strip()

    # Query generated images (both 'generated' type and images with generation_prompt)
    # Exclude videos - they're stored in /assets/videos/ directory in R2
    from django.db.models import Q
    assets = Asset.objects.filter(
        user=request.user,
    ).filter(
        Q(asset_type=Asset.TYPE_GENERATED) |
        (Q(asset_type=Asset.TYPE_IMAGE) & Q(generation_prompt__isnull=False))
    ).exclude(
        r2_key__contains='/assets/videos/'
    ).select_related('chat').order_by(ordering)

    if search:
        assets = assets.filter(
            Q(generation_prompt__icontains=search) |
            Q(generation_model__icontains=search)
        )

    # Pagination
    total_count = assets.count()
    offset = (page - 1) * page_size
    paginated_assets = assets[offset:offset + page_size]

    # Build pagination URLs
    base_url = request.build_absolute_uri(request.path)
    next_url = None
    previous_url = None

    if offset + page_size < total_count:
        next_url = f"{base_url}?page={page + 1}&page_size={page_size}"
    if page > 1:
        previous_url = f"{base_url}?page={page - 1}&page_size={page_size}"

    return Response({
        'count': total_count,
        'next': next_url,
        'previous': previous_url,
        'results': GalleryAssetSerializer(
            paginated_assets,
            many=True,
            context={'request': request}
        ).data,
    })


@api_view(['GET'])
def list_user_generated_videos(request: Request) -> Response:
    """
    List all AI-generated videos for the current user across all conversations.

    Query parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 24, max: 100)
    - ordering: Sort order (default: -created_at)

    Returns paginated list of generated videos with conversation context.
    """
    # Parse query parameters
    try:
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 24)), 100)
    except (ValueError, TypeError):
        page = 1
        page_size = 24

    ordering = request.query_params.get('ordering', '-created_at')
    if ordering not in ['-created_at', 'created_at', '-size_bytes', 'size_bytes', '-duration_seconds', 'duration_seconds']:
        ordering = '-created_at'

    search = request.query_params.get('search', '').strip()

    # Query generated videos (video type with generation_prompt)
    from django.db.models import Q
    assets = Asset.objects.filter(
        user=request.user,
        mime_type__startswith='video/',
        generation_prompt__isnull=False,
    ).select_related('chat').order_by(ordering)

    if search:
        assets = assets.filter(
            Q(generation_prompt__icontains=search) |
            Q(generation_model__icontains=search)
        )

    # Pagination
    total_count = assets.count()
    offset = (page - 1) * page_size
    paginated_assets = assets[offset:offset + page_size]

    # Build pagination URLs
    base_url = request.build_absolute_uri(request.path)
    next_url = None
    previous_url = None

    if offset + page_size < total_count:
        next_url = f"{base_url}?page={page + 1}&page_size={page_size}"
    if page > 1:
        previous_url = f"{base_url}?page={page - 1}&page_size={page_size}"

    return Response({
        'count': total_count,
        'next': next_url,
        'previous': previous_url,
        'results': GalleryAssetSerializer(
            paginated_assets,
            many=True,
            context={'request': request}
        ).data,
    })


# ─────────────────────────────────────────────────────────
# Share Link Management (Authenticated)
# ─────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_share_link(request: Request, asset_id: str) -> Response:
    """
    Create a public share link for an asset.

    The user must own the asset. Returns the share URL and metadata.

    Rate limited to prevent abuse (inherits from UserRateThrottle).
    """
    from django.utils import timezone

    try:
        asset_uuid = UUID(asset_id)
    except ValueError:
        return Response(
            {'error': 'Invalid asset ID format'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Validate asset ownership
    asset = Asset.objects.filter(
        id=asset_uuid,
        user=request.user,
    ).first()

    if not asset:
        return Response(
            {'error': 'Asset not found or access denied'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Validate request data
    serializer = CreateShareLinkSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {'error': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    data = serializer.validated_data

    # Calculate expiration
    expires_at = None
    if data.get('expires_in_hours'):
        expires_at = timezone.now() + timedelta(hours=data['expires_in_hours'])

    # Generate secure token
    token = AssetShareLink.generate_token()

    # Create share link with watermark settings
    share_link = AssetShareLink.objects.create(
        asset=asset,
        created_by=request.user,
        token=token,
        expires_at=expires_at,
        custom_title=data.get('custom_title', ''),
        watermark_enabled=data.get('watermark_enabled', True),
        watermark_position=data.get('watermark_position', 'bottom-right'),
    )

    logger.info(
        f"Share link created: asset={asset_id}, token={token[:8]}..., "
        f"user={cast(User, request.user).id}, expires={expires_at}"
    )

    return Response(
        AssetShareLinkSerializer(share_link, context={'request': request}).data,
        status=status.HTTP_201_CREATED
    )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def revoke_share_link(request: Request, token: str) -> Response:
    """
    Revoke (soft delete) a share link.

    The user must be the creator of the share link.
    """
    share_link = AssetShareLink.objects.filter(
        token=token,
        created_by=request.user,
    ).first()

    if not share_link:
        return Response(
            {'error': 'Share link not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Soft delete
    share_link.is_active = False
    share_link.save(update_fields=['is_active', 'updated_at'])

    logger.info(f"Share link revoked: token={token[:8]}..., user={cast(User, request.user).id}")

    return Response({'success': True, 'revoked': True})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_share_links(request: Request) -> Response:
    """
    List all share links created by the current user.

    Supports filtering by:
    - active: true/false (default: all)
    - asset_id: specific asset

    Supports pagination via page/page_size.
    """
    queryset = AssetShareLink.objects.filter(
        created_by=request.user
    ).select_related('asset')

    # Optional filters
    active_filter = request.query_params.get('active')
    if active_filter == 'true':
        queryset = queryset.filter(is_active=True)
    elif active_filter == 'false':
        queryset = queryset.filter(is_active=False)

    asset_id = request.query_params.get('asset_id')
    if asset_id:
        try:
            queryset = queryset.filter(asset_id=UUID(asset_id))
        except ValueError:
            pass  # Ignore invalid UUID

    # Pagination
    try:
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 20)), 100)
    except ValueError:
        page, page_size = 1, 20

    total_count = queryset.count()
    offset = (page - 1) * page_size
    paginated = queryset[offset:offset + page_size]

    return Response({
        'count': total_count,
        'page': page,
        'page_size': page_size,
        'results': ShareLinkListSerializer(
            paginated,
            many=True,
            context={'request': request}
        ).data,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_asset_share_links(request: Request, asset_id: str) -> Response:
    """
    Get all share links for a specific asset.

    User must own the asset.
    """
    try:
        asset_uuid = UUID(asset_id)
    except ValueError:
        return Response(
            {'error': 'Invalid asset ID format'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Validate ownership
    if not Asset.objects.filter(id=asset_uuid, user=request.user).exists():
        return Response(
            {'error': 'Asset not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    share_links = AssetShareLink.objects.filter(
        asset_id=asset_uuid,
        is_active=True,
    ).order_by('-created_at')

    return Response({
        'share_links': AssetShareLinkSerializer(
            share_links,
            many=True,
            context={'request': request}
        ).data,
    })


# ─────────────────────────────────────────────────────────
# Public Share Endpoints (No Auth Required)
# ─────────────────────────────────────────────────────────

def is_social_media_crawler(user_agent: str) -> bool:
    """Check if the request is from a social media crawler."""
    crawler_patterns = [
        'twitterbot', 'facebookexternalhit', 'linkedinbot',
        'slackbot', 'discordbot', 'telegrambot', 'whatsapp',
        'pinterest', 'redditbot', 'googlebot', 'bingbot',
    ]
    user_agent_lower = (user_agent or '').lower()
    return any(pattern in user_agent_lower for pattern in crawler_patterns)


@api_view(['GET'])
@permission_classes([AllowAny])
def public_share_view(request: Request, token: str) -> Response | HttpResponse:
    """
    Public share page for viewing shared assets.

    Returns an HTML page with:
    - Open Graph meta tags for rich social previews
    - Twitter Card meta tags
    - Embedded image/video viewer
    - Attribution to the AI model used

    For social media crawlers, returns minimal HTML with OG tags.
    For browsers, returns full interactive page.
    """
    from django.template.loader import render_to_string

    share_link = AssetShareLink.objects.filter(
        token=token,
        is_active=True,
    ).select_related('asset', 'asset__thumbnail').first()

    if not share_link:
        return HttpResponse(
            render_to_string('share/not_found.html'),
            status=404,
            content_type='text/html'
        )

    # Check expiration
    if share_link.is_expired:
        return HttpResponse(
            render_to_string('share/expired.html'),
            status=410,  # Gone
            content_type='text/html'
        )

    # Increment view count (atomic)
    share_link.increment_view_count()

    asset = share_link.asset

    # Build URLs
    base_url = getattr(settings, 'SITE_URL', 'http://localhost:8000').rstrip('/')
    raw_url = f"{base_url}/share/{token}/raw/"
    share_url = f"{base_url}/share/{token}/"

    # Prepare context
    title = share_link.custom_title or asset.generation_prompt or 'AI-Generated Content'
    title_truncated = title[:60] + '...' if len(title) > 60 else title

    description = f"Created with {asset.generation_model or 'AI'}"
    if asset.generation_prompt and not share_link.custom_title:
        description = asset.generation_prompt[:200]

    # Determine OG type
    og_type = 'video.other' if asset.asset_type == 'video' else 'image'

    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')

    context = {
        'title': title_truncated,
        'description': description,
        'og_type': og_type,
        'asset_url': raw_url,
        'share_url': share_url,
        'frontend_url': frontend_url,
        'asset': asset,
        'share_link': share_link,
        'is_video': asset.asset_type == 'video' or (
            asset.mime_type and asset.mime_type.startswith('video/')
        ),
        'is_image': asset.asset_type in ('image', 'generated') or (
            asset.mime_type and asset.mime_type.startswith('image/')
        ),
        'width': asset.width,
        'height': asset.height,
        'mime_type': asset.mime_type,
        'created_at': asset.created_at,
    }

    # For crawlers, return minimal HTML with OG tags
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    if is_social_media_crawler(user_agent):
        return HttpResponse(
            render_to_string('share/crawler.html', context),
            content_type='text/html'
        )

    # For browsers, return full page
    return HttpResponse(
        render_to_string('share/view.html', context),
        content_type='text/html'
    )


@api_view(['GET'])
@permission_classes([AllowAny])
def public_share_raw(request: Request, token: str) -> Response | HttpResponse:
    """
    Direct asset access for shared links.

    Used by:
    - Social media crawlers fetching the og:image/og:video
    - Embedded players
    - Direct download/view

    Returns the actual binary content with appropriate headers.
    For images with watermark enabled, applies the watermark before serving.
    """
    share_link = AssetShareLink.objects.filter(
        token=token,
        is_active=True,
    ).select_related('asset').first()

    if not share_link:
        return HttpResponse(status=404)

    if share_link.is_expired:
        return HttpResponse(status=410)  # Gone

    asset = share_link.asset

    # Check if this is an image that needs watermarking
    is_image = asset.mime_type and asset.mime_type.startswith('image/')
    needs_watermark = is_image and share_link.watermark_enabled

    # For videos or images without watermark, redirect to R2 presigned URL
    if not needs_watermark and asset.storage_type == Asset.STORAGE_R2:
        presigned_url = asset_storage_service.get_presigned_url(
            asset,
            expiration=3600  # 1 hour
        )
        if presigned_url:
            return HttpResponseRedirect(presigned_url)

    # Fetch the asset content
    content = asset_storage_service.retrieve_asset(asset)
    if content is None:
        return HttpResponse(status=500)

    # Apply watermark to images if enabled
    if needs_watermark:
        try:
            watermarked = apply_watermark(
                content,
                position=share_link.watermark_position,
                text='Sterna',
                opacity=0.6
            )
            content = watermarked or content
            # Watermarked images are always JPEG; otherwise keep the original type
            mime_type = 'image/jpeg' if watermarked else asset.mime_type
        except Exception as e:
            logger.warning(f"Failed to apply watermark: {e}")
            # Fall back to original content
            mime_type = asset.mime_type
    else:
        mime_type = asset.mime_type

    response = HttpResponse(content, content_type=mime_type)
    response['Content-Disposition'] = f'inline; filename="{asset.filename}"'
    response['Content-Length'] = len(content)
    response['Cache-Control'] = 'public, max-age=86400'  # Cache for 24 hours

    # Video support
    if mime_type and mime_type.startswith('video/'):
        response['Accept-Ranges'] = 'bytes'

    return response
