"""
File Version API Views

REST endpoints for file version history, content retrieval, and comparison.
Includes internal service endpoints for orchestrator integration.
"""

import base64
import logging
from uuid import UUID

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from workspaces.models import Workspace, FileVersion
from workspaces.services.file_version_service import get_file_version_service
from security import require_service_auth

logger = logging.getLogger(__name__)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def file_history(request, chat_id: str):
    """
    Get version history for a specific file.

    Query params:
        path: File path (required)
        limit: Max versions to return (default 50)

    Returns:
        List of versions with metadata
    """
    path = request.query_params.get('path')
    if not path:
        return Response({'error': 'path parameter required'}, status=status.HTTP_400_BAD_REQUEST)

    limit = int(request.query_params.get('limit', 50))

    workspace = get_object_or_404(Workspace, chat_id=chat_id, user=request.user)
    service = get_file_version_service()
    versions = service.get_file_history(workspace, path, limit=limit)

    return Response({
        'path': path,
        'total_versions': len(versions),
        'versions': [{
            'id': str(v.id),
            'version_number': v.version_number,
            'source_type': v.source_type,
            'source_type_display': v.get_source_type_display(),
            'source_message_id': str(v.source_message_id) if v.source_message_id else None,
            'source_job_id': v.source_job_id or None,
            'source_tool_name': v.source_tool_name or None,
            'size_bytes': v.size_bytes,
            'is_deleted': v.is_deleted,
            'is_binary': v.is_binary,
            'mime_type': v.mime_type,
            'created_at': v.created_at.isoformat(),
            'created_by': {
                'id': str(v.created_by.id),
                'username': v.created_by.username,
            } if v.created_by else None,
        } for v in versions]
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def version_content(request, version_id: str):
    """
    Get content of a specific version.

    Returns:
        Content as text and metadata
    """
    service = get_file_version_service()
    version = service.get_version(version_id)

    if not version:
        return Response({'error': 'Version not found'}, status=status.HTTP_404_NOT_FOUND)

    # Verify user owns the workspace
    if version.workspace.user != request.user:
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    if version.is_binary:
        return Response({
            'version_id': str(version.id),
            'path': version.path,
            'version_number': version.version_number,
            'is_binary': True,
            'size_bytes': version.size_bytes,
            'mime_type': version.mime_type,
            'content': None,
        })

    try:
        content = service.get_version_content(version)
        content_str = content.decode('utf-8', errors='replace')
    except Exception as e:
        logger.error(f"Failed to retrieve version content: {e}")
        return Response({'error': 'Failed to retrieve content'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        'version_id': str(version.id),
        'path': version.path,
        'version_number': version.version_number,
        'is_binary': False,
        'size_bytes': version.size_bytes,
        'mime_type': version.mime_type,
        'content': content_str,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def compare_versions(request):
    """
    Compare two versions of a file.

    Query params:
        a: Version ID for original (older version)
        b: Version ID for modified (newer version)

    Returns:
        Both versions' content for diff display
    """
    version_a_id = request.query_params.get('a')
    version_b_id = request.query_params.get('b')

    if not version_a_id or not version_b_id:
        return Response(
            {'error': 'Both "a" and "b" version IDs required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    service = get_file_version_service()

    version_a = service.get_version(version_a_id)
    version_b = service.get_version(version_b_id)

    if not version_a or not version_b:
        return Response({'error': 'Version not found'}, status=status.HTTP_404_NOT_FOUND)

    # Verify user owns both workspaces
    if version_a.workspace.user != request.user or version_b.workspace.user != request.user:
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    try:
        result = service.compare_versions(version_a, version_b)
    except Exception as e:
        logger.error(f"Failed to compare versions: {e}")
        return Response({'error': 'Failed to compare versions'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    return Response({
        'path': version_a.path,
        'version_a': {
            'id': result.version_a.id,
            'version_number': result.version_a.version_number,
            'source_type': result.version_a.source_type,
            'source_type_display': result.version_a.source_type_display,
            'created_at': result.version_a.created_at,
        },
        'version_b': {
            'id': result.version_b.id,
            'version_number': result.version_b.version_number,
            'source_type': result.version_b.source_type,
            'source_type_display': result.version_b.source_type_display,
            'created_at': result.version_b.created_at,
        },
        'is_binary': result.is_binary,
        'original_content': result.original_content.decode('utf-8', errors='replace') if result.original_content else None,
        'modified_content': result.modified_content.decode('utf-8', errors='replace') if result.modified_content else None,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def workspace_timeline(request, chat_id: str):
    """
    Get timeline of all changes in workspace.

    Query params:
        source_type: Filter by source type (optional)
        limit: Max entries (default 100)

    Returns:
        List of all file versions, newest first
    """
    source_type = request.query_params.get('source_type')
    limit = int(request.query_params.get('limit', 100))

    workspace = get_object_or_404(Workspace, chat_id=chat_id, user=request.user)
    service = get_file_version_service()

    versions = service.get_workspace_timeline(
        workspace,
        source_type=source_type,
        limit=limit,
    )

    return Response({
        'chat_id': chat_id,
        'total_entries': len(versions),
        'timeline': [{
            'id': str(v.id),
            'path': v.path,
            'filename': v.path.split('/')[-1],
            'version_number': v.version_number,
            'source_type': v.source_type,
            'source_type_display': v.get_source_type_display(),
            'source_job_id': v.source_job_id or None,
            'source_tool_name': v.source_tool_name or None,
            'size_bytes': v.size_bytes,
            'is_deleted': v.is_deleted,
            'is_binary': v.is_binary,
            'created_at': v.created_at.isoformat(),
        } for v in versions]
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def message_file_changes(request, message_id: str):
    """
    Get all file changes from a specific message (e.g., Coding Agent execution).

    Returns:
        List of file versions created by this message, grouped by file
    """
    from conversations.models import Message

    message = get_object_or_404(Message, id=message_id)

    # Verify user owns the conversation
    if message.chat.conversation.user != request.user:
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    service = get_file_version_service()
    versions = service.get_message_file_changes(message)

    # Group by file and determine change type
    files = {}
    for v in versions:
        if v.path not in files:
            files[v.path] = {
                'path': v.path,
                'filename': v.path.split('/')[-1],
                'versions': [],
                'change_type': 'created' if v.version_number == 1 else 'modified',
                'is_binary': v.is_binary,
            }
        files[v.path]['versions'].append({
            'id': str(v.id),
            'version_number': v.version_number,
            'is_deleted': v.is_deleted,
            'size_bytes': v.size_bytes,
            'created_at': v.created_at.isoformat(),
        })
        if v.is_deleted:
            files[v.path]['change_type'] = 'deleted'

    return Response({
        'message_id': message_id,
        'files': list(files.values()),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def job_file_changes(request, job_id: str):
    """
    Get all file changes from a Coding Agent job.

    Returns:
        List of file versions created by this job, grouped by file
    """
    service = get_file_version_service()
    versions = service.get_job_file_changes(job_id)

    if not versions:
        return Response({
            'job_id': job_id,
            'files': [],
        })

    # Verify user owns the workspace (check first version)
    first_version = versions[0]
    if first_version.workspace.user != request.user:
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    # Group by file
    files = {}
    for v in versions:
        if v.path not in files:
            # Determine change_type from source_tool_name (set by coding agent runner)
            # 'Write' = new file, 'Edit' = modified file
            if v.source_tool_name == 'Edit':
                change_type = 'modified'
            elif v.source_tool_name == 'Write':
                change_type = 'created'
            else:
                # Fallback to version_number check
                change_type = 'created' if v.version_number == 1 else 'modified'

            files[v.path] = {
                'path': v.path,
                'filename': v.path.split('/')[-1],
                'versions': [],
                'change_type': change_type,
                'is_binary': v.is_binary,
            }
        files[v.path]['versions'].append({
            'id': str(v.id),
            'version_number': v.version_number,
            'is_deleted': v.is_deleted,
            'size_bytes': v.size_bytes,
            'created_at': v.created_at.isoformat(),
        })
        if v.is_deleted:
            files[v.path]['change_type'] = 'deleted'

    return Response({
        'job_id': job_id,
        'files': list(files.values()),
    })


# ─────────────────────────────────────────────────────────
# Internal Service Endpoints (called by orchestrator)
# ─────────────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])  # Auth handled by @require_service_auth
@require_service_auth
def create_version(request):
    """
    Create a file version (called by orchestrator after file operations).

    This endpoint enables immediate versioning for file tool operations,
    without waiting for workspace sync.

    Expected payload:
    {
        "user_id": "uuid",
        "chat_id": "uuid",
        "path": "src/main.py",
        "content_base64": "...",
        "source_type": "file_tool",
        "source_message_id": "uuid" (optional),
        "source_job_id": "job_123" (optional),
        "source_tool_name": "Write" (optional),
        "is_deleted": false (optional)
    }

    Returns:
    {
        "success": true,
        "version": { ...version metadata... }
    }
    """
    from conversations.models import Message

    try:
        user_id = UUID(request.data.get('user_id'))
        chat_id = UUID(request.data.get('chat_id'))
        path = request.data.get('path')
        content_b64 = request.data.get('content_base64', '')
        source_type = request.data.get('source_type', 'file_tool')
        source_message_id = request.data.get('source_message_id')
        source_job_id = request.data.get('source_job_id', '')
        source_tool_name = request.data.get('source_tool_name', '')
        is_deleted = request.data.get('is_deleted', False)
    except (ValueError, TypeError) as e:
        return Response(
            {'success': False, 'error': f'Invalid request: {e}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not path:
        return Response(
            {'success': False, 'error': 'Path is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Validate source_type
    valid_source_types = [choice[0] for choice in FileVersion.SourceType.choices]
    if source_type not in valid_source_types:
        source_type = 'file_tool'

    try:
        # Get or create workspace
        workspace, _ = Workspace.objects.get_or_create(
            user_id=user_id,
            chat_id=chat_id,
        )

        # Decode content
        try:
            content = base64.b64decode(content_b64) if content_b64 else b''
        except Exception:
            return Response(
                {'success': False, 'error': 'Invalid base64 content'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get source message if provided
        source_message = None
        if source_message_id:
            try:
                source_message = Message.objects.get(id=UUID(source_message_id))
            except (ValueError, Message.DoesNotExist):
                pass

        # Create version
        service = get_file_version_service()
        if is_deleted:
            version = service.create_deletion_tombstone(
                workspace=workspace,
                path=path,
                source_type=source_type,
                source_message=source_message,
                source_job_id=source_job_id,
            )
        else:
            version = service.create_version(
                workspace=workspace,
                path=path,
                content=content,
                source_type=source_type,
                source_message=source_message,
                source_job_id=source_job_id,
                source_tool_name=source_tool_name,
            )

        logger.info(
            f"[create_version] Created v{version.version_number} for {path} "
            f"(chat={chat_id}, source={source_type})"
        )

        return Response({
            'success': True,
            'version': {
                'id': str(version.id),
                'version_number': version.version_number,
                'path': version.path,
                'source_type': version.source_type,
                'size_bytes': version.size_bytes,
                'is_deleted': version.is_deleted,
            }
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.error(f"[create_version] Error: {e}")
        return Response(
            {'success': False, 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])  # Auth handled by @require_service_auth
@require_service_auth
def create_versions_batch(request):
    """
    Create multiple file versions in a batch (used during workspace sync).

    Expected payload:
    {
        "user_id": "uuid",
        "chat_id": "uuid",
        "source_type": "coding_agent",
        "source_job_id": "cc_abc123" (optional),
        "files": [
            {
                "path": "src/main.py",
                "content_base64": "...",
                "source_tool_name": "Write" (optional),
                "is_deleted": false (optional)
            }
        ]
    }
    """
    try:
        user_id = UUID(request.data.get('user_id'))
        chat_id = UUID(request.data.get('chat_id'))
        source_type = request.data.get('source_type', 'file_tool')
        source_job_id = request.data.get('source_job_id', '')
        files = request.data.get('files', [])
    except (ValueError, TypeError) as e:
        return Response(
            {'success': False, 'error': f'Invalid request: {e}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not files:
        return Response({'success': True, 'versions_created': 0})

    try:
        # Get or create workspace
        workspace, _ = Workspace.objects.get_or_create(
            user_id=user_id,
            chat_id=chat_id,
        )

        service = get_file_version_service()
        versions_created = 0
        errors = []

        for file_data in files:
            try:
                path = file_data.get('path')
                content_b64 = file_data.get('content_base64', '')
                tool_name = file_data.get('source_tool_name', '')
                is_deleted = file_data.get('is_deleted', False)

                if not path:
                    continue

                content = base64.b64decode(content_b64) if content_b64 else b''

                if is_deleted:
                    service.create_deletion_tombstone(
                        workspace=workspace,
                        path=path,
                        source_type=source_type,
                        source_job_id=source_job_id,
                    )
                else:
                    service.create_version(
                        workspace=workspace,
                        path=path,
                        content=content,
                        source_type=source_type,
                        source_job_id=source_job_id,
                        source_tool_name=tool_name,
                    )
                versions_created += 1

            except Exception as e:
                errors.append(f"{file_data.get('path', 'unknown')}: {str(e)}")

        logger.info(
            f"[create_versions_batch] Created {versions_created} versions for chat={chat_id}"
        )

        return Response({
            'success': len(errors) == 0,
            'versions_created': versions_created,
            'errors': errors,
        })

    except Exception as e:
        logger.error(f"[create_versions_batch] Error: {e}")
        return Response(
            {'success': False, 'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
