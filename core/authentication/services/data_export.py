"""Per-user data exporters used by export_user_data Celery task.

Each function returns a JSON-serializable dict; the orchestrator writes
{category}.json into the zip. The signature is uniform so the registry
in DATA_EXPORTERS works.
"""

import logging
from decimal import Decimal
from uuid import UUID

logger = logging.getLogger(__name__)


def _serializable(value):
    """Recursively coerce UUIDs, Decimals, datetimes to JSON-safe types."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serializable(v) for v in value]
    return value


def export_profile(user) -> dict:
    # BYOK status lives in export_byok_settings — do not duplicate here.
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "avatar_url": user.avatar_url or "",
        "is_verified": user.is_verified,
        "is_active": user.is_active,
        "date_joined": user.date_joined.isoformat(),
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "preferred_image_model": user.preferred_image_model,
        "preferred_video_model": user.preferred_video_model,
    }


def export_conversations(user) -> dict:
    from conversations.models import Conversation

    rows = [
        {
            "id": str(c.id),
            "name": c.name,
            "is_archived": c.is_archived,
            "is_pinned": c.is_pinned,
            "consigliere_session_id": c.consigliere_session_id,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in Conversation.objects.filter(user=user).iterator()
    ]
    return {"conversations": rows, "count": len(rows)}


def export_chats(user) -> dict:
    from conversations.models import Chat

    rows = [
        {
            "id": str(ch.id),
            "conversation_id": str(ch.conversation_id),
            "model_id": ch.model_id,
            "model_provider": ch.model_provider,
            "parameters": ch.parameters,
            "position": ch.position,
            "instructions": ch.instructions,
            "created_at": ch.created_at.isoformat(),
        }
        for ch in Chat.objects.filter(conversation__user=user).iterator()
    ]
    return {"chats": rows, "count": len(rows)}


def export_messages(user) -> dict:
    from conversations.models import Message

    rows = []
    qs = Message.objects.filter(
        chat__conversation__user=user
    ).iterator(chunk_size=500)
    for m in qs:
        rows.append({
            "id": str(m.id),
            "chat_id": str(m.chat_id),
            "role": m.role,
            "content": _serializable(m.content),
            "sequence": m.sequence,
            "model_id": m.model_id,
            "model_provider": m.model_provider,
            "tool_calls": _serializable(m.tool_calls),
            "tool_call_id": m.tool_call_id,
            "prompt_tokens": m.prompt_tokens,
            "completion_tokens": m.completion_tokens,
            "cost": float(m.cost) if m.cost else None,
            "created_at": m.created_at.isoformat(),
        })
    return {"messages": rows, "count": len(rows)}


def export_sparks(user) -> dict:
    from sparks.models import Spark

    rows = [
        {
            "id": str(s.id),
            "title": s.title,
            "framework": s.framework,
            "version": s.version,
            "parent_id": str(s.parent_id) if s.parent_id else None,
            "storage_type": s.storage_type,
            "code_inline": (
                s.code if s.storage_type == Spark.StorageType.INLINE else None
            ),
            "code_in_r2": s.storage_type == Spark.StorageType.R2,
            "created_at": s.created_at.isoformat(),
        }
        for s in Spark.objects.filter(user=user).iterator()
    ]
    return {"sparks": rows, "count": len(rows)}


def export_voice_rooms(user) -> dict:
    from voice_rooms.models import VoiceRoom

    rows = [
        {
            "id": str(r.id),
            "name": r.name,
            "description": r.description,
            "language": r.language,
            "is_active": r.is_active,
            "created_at": r.created_at.isoformat(),
        }
        for r in VoiceRoom.objects.filter(user=user).iterator()
    ]
    return {"voice_rooms": rows, "count": len(rows)}


def export_kb_documents(user) -> dict:
    from knowledge_base.models import KnowledgeDocument

    rows = [
        {
            "id": str(d.id),
            "filename": d.filename,
            "original_filename": d.original_filename,
            "document_type": d.document_type,
            "mime_type": d.mime_type,
            "file_size_bytes": d.file_size_bytes,
            "status": d.status,
            "chunk_count": d.chunk_count,
            "uploaded_at": d.uploaded_at.isoformat(),
        }
        for d in KnowledgeDocument.objects.filter(user=user).iterator()
    ]
    return {"documents": rows, "count": len(rows)}


def export_kb_chunks(user) -> dict:
    """Chunks WITHOUT embeddings — embeddings are non-recoverable derived data."""
    from knowledge_base.models import KnowledgeChunk

    rows = []
    qs = KnowledgeChunk.objects.filter(user=user).only(
        "id",
        "document_id",
        "content",
        "chunk_index",
        "page_number",
        "embedding_model",
        "token_count",
        "created_at",
    ).iterator(chunk_size=500)
    for ch in qs:
        rows.append({
            "id": str(ch.id),
            "document_id": str(ch.document_id),
            "content": ch.content,
            "chunk_index": ch.chunk_index,
            "page_number": ch.page_number,
            "embedding_model": ch.embedding_model,
            "token_count": ch.token_count,
            "created_at": ch.created_at.isoformat(),
        })
    return {
        "chunks": rows,
        "count": len(rows),
        "_note": "Embeddings are derived data and not included.",
    }


def export_mcp_connectors(user) -> dict:
    """MCP servers WITHOUT auth_config / env_vars / oauth secrets."""
    from mcp.models import MCPServer

    rows = []
    for s in MCPServer.objects.filter(user=user).iterator():
        rows.append({
            "id": str(s.id),
            "name": s.name,
            "description": s.description,
            "transport_type": s.transport_type,
            "url": s.url,
            "remote_url": s.remote_url,
            "npm_package": s.npm_package,
            "category": s.category,
            "is_active": s.is_active,
            "allowed_domains": s.allowed_domains,
            "created_at": s.created_at.isoformat(),
            "_redacted": [
                "auth_config",
                "env_vars",
                "oauth_client_secret",
                "oauth_access_token",
                "oauth_refresh_token",
                "oauth_pkce_verifier",
            ],
        })
    return {"connectors": rows, "count": len(rows)}


def export_usage_logs(user) -> dict:
    from usage_quota.models import UsageLog

    rows = []
    for log in UsageLog.objects.filter(user=user).iterator(chunk_size=1000):
        rows.append({
            "id": str(log.id),
            "service": log.service,
            "feature": log.feature,
            "model_id": log.model_id,
            "prompt_tokens": log.prompt_tokens,
            "completion_tokens": log.completion_tokens,
            "cost_usd": float(log.cost_usd),
            "timestamp": log.timestamp.isoformat(),
        })
    return {"usage_logs": rows, "count": len(rows)}


def export_subscriptions(user) -> dict:
    from usage_quota.models import UserSubscription

    try:
        sub = UserSubscription.objects.select_related("plan").get(user=user)
    except UserSubscription.DoesNotExist:
        return {"subscription": None}
    return {
        "subscription": {
            "plan_name": sub.plan.name,
            "is_active": sub.is_active,
            "weekly_window_start": (
                sub.weekly_window_start.isoformat()
                if sub.weekly_window_start else None
            ),
            "session_window_start": (
                sub.session_window_start.isoformat()
                if sub.session_window_start else None
            ),
            "custom_weekly_limit_usd": (
                float(sub.custom_weekly_limit_usd)
                if sub.custom_weekly_limit_usd is not None else None
            ),
            "custom_session_limit_usd": (
                float(sub.custom_session_limit_usd)
                if sub.custom_session_limit_usd is not None else None
            ),
            "created_at": sub.created_at.isoformat(),
        }
    }


def export_byok_settings(user) -> dict:
    return {
        "byok_configured": bool(user.openrouter_api_key),
        "openrouter_key_provisioned_at": (
            user.openrouter_key_provisioned_at.isoformat()
            if user.openrouter_key_provisioned_at else None
        ),
        "openrouter_api_key": (
            "[redacted; revoke and recreate to access]"
            if user.openrouter_api_key else None
        ),
    }


def export_audit_log(user) -> dict:
    from audit_logging.models import AuditLog

    rows = []
    for log in AuditLog.objects.filter(user=user).iterator(chunk_size=500):
        rows.append({
            "id": str(log.id),
            "timestamp": log.timestamp.isoformat(),
            "action": log.action,
            "action_category": log.action_category,
            "resource_str": log.resource_str,
            "success": log.success,
            "request_id": log.request_id,
            "session_id": log.session_id,
        })
    return {"audit_logs": rows, "count": len(rows)}


DATA_EXPORTERS = [
    ("user_profile", export_profile),
    ("conversations", export_conversations),
    ("chats", export_chats),
    ("messages", export_messages),
    ("sparks", export_sparks),
    ("voice_rooms", export_voice_rooms),
    ("kb_documents", export_kb_documents),
    ("kb_chunks", export_kb_chunks),
    ("mcp_connectors", export_mcp_connectors),
    ("usage_logs", export_usage_logs),
    ("subscriptions", export_subscriptions),
    ("byok_settings", export_byok_settings),
    ("audit_log", export_audit_log),
]
