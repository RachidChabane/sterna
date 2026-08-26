"""
Spark Tools for LangChain.

Provides tools for creating interactive React components (Sparks) that render
in the chat interface. Similar to Claude.ai artifacts.

Sparks are self-contained React components that can visualize data, create
interactive UI elements, charts, games, and more.
"""

import base64
import json
import logging
import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Tuple

import httpx
from asgiref.sync import sync_to_async
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from sterna.middleware.request_id import request_id_headers

logger = logging.getLogger(__name__)

# Shared maps for generated document frameworks (PDF/DOCX/XLSX)
GENERATED_DOC_EXTENSIONS = {'pdf': 'pdf', 'docx': 'docx', 'xlsx': 'xlsx'}
GENERATED_DOC_MIME_TYPES = {
    'pdf': 'application/pdf',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}


def _get_asset_url(asset) -> str:
    """
    Get URL for an asset, preferring presigned URL for R2 assets.

    Presigned URLs allow sandboxed iframes to access assets without
    authentication. They expire after 1 hour (3600 seconds).
    """
    if asset.storage_type == 'r2' and asset.r2_key:
        try:
            from workspaces.services import get_asset_storage_service
            storage = get_asset_storage_service()
            presigned_url = storage.get_presigned_url(asset, expiration=3600)
            if presigned_url:
                return presigned_url
        except Exception as e:
            logger.warning(f"[SparkTool] Failed to get presigned URL for asset {asset.id}: {e}")

    # Fallback to authenticated URL
    return f'/api/workspaces/assets/{asset.id}/download/'


# Context variable for passing user/chat info to spark tools
SPARK_TOOL_CONTEXT: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    'spark_tool_context', default=None
)


def set_spark_tool_context(context: Dict[str, Any]) -> None:
    """Set the spark tool context for the current execution."""
    SPARK_TOOL_CONTEXT.set(context)


def get_spark_tool_context() -> Optional[Dict[str, Any]]:
    """Get the current spark tool context."""
    return SPARK_TOOL_CONTEXT.get()


async def _check_spark_generation_gate(user_id) -> Optional[str]:
    """Run feature_name='spark_generation' pre-flight on user_id.

    Returns ``None`` when the gate passes. Returns a JSON-encoded error
    string when denied — the LLM sees a structured error and should
    not retry the tool.
    """
    if not user_id:
        return None
    try:
        from decimal import Decimal

        from asgiref.sync import sync_to_async
        from usage_quota.billing.service import get_billing_service
        from usage_quota.exceptions import (
            FeatureNotAvailableException,
            QuotaExceededException,
        )
        from usage_quota.models import FeatureType, ServiceType
        if TYPE_CHECKING:
            from authentication.models import User
        else:
            from django.contrib.auth import get_user_model
            User = get_user_model()
        user = await sync_to_async(User.objects.get)(id=user_id)
        try:
            await sync_to_async(get_billing_service().check_quota)(
                user=user,
                service=ServiceType.OPENROUTER,
                estimated_cost=Decimal('0'),
                feature=FeatureType.CHAT,
                feature_name='spark_generation',
            )
        except (FeatureNotAvailableException, QuotaExceededException) as exc:
            return json.dumps({
                "success": False,
                "status": "error",
                "error_type": exc.code,
                "message": exc.message,
                **exc.to_response_dict(),
            })
    except Exception:
        logger.error("spark_generation_tier_gate_error", exc_info=True)
    return None


class CreateSparkInput(BaseModel):
    """Input schema for creating a spark."""
    title: str = Field(
        ...,
        description="A clear, descriptive title for the spark (e.g., 'Sales Dashboard', 'Interactive Counter', 'Data Visualization')"
    )
    code: str = Field(
        ...,
        description=(
            "The spark content. For react/html/svg: component code. For markdown/mermaid/csv/ics: raw content. "
            "For pdf/docx: Python code that generates the document. "
            "For xlsx: Python code using openpyxl that generates a spreadsheet. "
            "React sparks must export a default function component with Tailwind CSS styling."
        )
    )
    framework: Literal["react", "html", "svg", "markdown", "mermaid", "pdf", "docx", "xlsx", "ics", "csv"] = Field(
        "react",
        description=(
            "Content type: 'react' (default), 'html', 'svg' for interactive components; "
            "'markdown' for formatted text; 'mermaid' for diagrams; "
            "'csv' for tabular data; 'ics' for calendar events; "
            "'pdf'/'docx' for generated documents (Python code); "
            "'xlsx' for Excel spreadsheets (Python code using openpyxl)"
        )
    )
    asset_ids: Optional[List[str]] = Field(
        None,
        description=(
            "List of asset IDs (images/videos) to include in the spark. "
            "These assets will be available in the spark code via window.__SPARK_ASSETS__[assetId]. "
            "Get asset IDs from generate_image, generate_video, or list_generated_images/videos tools."
        )
    )


class UpdateSparkInput(BaseModel):
    """Input schema for updating a spark."""
    spark_id: str = Field(
        ...,
        description="The ID of the spark to update (from a previous create_spark response)"
    )
    code: str = Field(
        ...,
        description="The complete updated React component code"
    )
    title: Optional[str] = Field(
        None,
        description="Optional new title for the spark"
    )
    asset_ids: Optional[List[str]] = Field(
        None,
        description=(
            "List of asset IDs to associate with this spark version. "
            "If not provided, assets from the previous version are preserved."
        )
    )


def _detect_dependencies(code: str) -> list:
    """Detect which libraries a spark uses based on code analysis."""
    import re
    dependencies = []

    # Check for Recharts usage
    recharts_patterns = [
        r'Recharts\.',
        r'\b(LineChart|BarChart|PieChart|AreaChart|RadarChart|ComposedChart)\b',
        r'\b(XAxis|YAxis|Tooltip|Legend|Line|Bar|Pie|Area|Cell|ResponsiveContainer)\b',
    ]
    for pattern in recharts_patterns:
        if re.search(pattern, code):
            dependencies.append('recharts')
            break

    # Check for Lucide icons
    lucide_patterns = [
        r'lucideReact\.',
        r'lucide-react',
        r'\bLucide\w+\b',
    ]
    for pattern in lucide_patterns:
        if re.search(pattern, code):
            dependencies.append('lucide-react')
            break

    return list(set(dependencies))


async def _execute_generated_document(
    context: Dict[str, Any],
    code: str,
    framework: str,
) -> Tuple[Optional[bytes], Optional[str]]:
    """Execute PDF/DOCX/XLSX generation code in sandbox, return binary content or error."""
    ext = GENERATED_DOC_EXTENSIONS[framework]
    output_filename = f'spark_output.{ext}'
    chat_id = str(context.get("chat_id", ""))
    # Write output inside /workspace/chat-{chat_id}/ so the artifact collector finds it
    output_path = f'/workspace/chat-{chat_id}/{output_filename}'

    # Prepend OUTPUT_PATH (since _run_exec doesn't pass custom env vars)
    wrapped_code = (
        f"import os\n"
        f"os.environ['OUTPUT_PATH'] = '{output_path}'\n"
        f"{code}"
    )

    orchestrator_url = "http://orchestrator:8003"
    auth_token = context.get("auth_token")
    headers = request_id_headers({"Authorization": f"Bearer {auth_token}"} if auth_token else {})

    async with httpx.AsyncClient(timeout=45.0) as client:
        # 1. Execute code in sandbox
        try:
            resp = await client.post(f"{orchestrator_url}/execute", json={
                "code": wrapped_code,
                "language": "python",
                "timeout": 30,
                "user_id": str(context.get("user_id", "")),
                "conversation_id": str(context.get("conversation_id", "")),
                "chat_id": str(context.get("chat_id", "")),
                "sync_mode": True,
            }, headers=headers)
        except httpx.HTTPError as e:
            logger.error(f"[SparkTool] Sandbox execution request failed: {e}")
            return None, f"Sandbox execution request failed: {e}"

        result = resp.json()
        if result.get("exit_code") != 0:
            error_msg = result.get("error") or result.get("output") or "Unknown execution error"
            logger.warning(f"[SparkTool] Sandbox execution failed (exit_code={result.get('exit_code')}): {error_msg}")
            return None, error_msg

        # 2. Check artifacts (orchestrator auto-collects .pdf files from container)
        artifacts = result.get("artifacts", [])
        doc_artifact = next(
            (a for a in artifacts if a.get("filename", "").endswith(f'.{ext}')),
            None,
        )

        if doc_artifact and doc_artifact.get("url"):
            try:
                artifact_resp = await client.get(
                    f"{orchestrator_url}{doc_artifact['url']}",
                    headers=headers,
                )
                if artifact_resp.status_code == 200 and len(artifact_resp.content) > 0:
                    logger.info(f"[SparkTool] Retrieved {ext} via artifact URL ({len(artifact_resp.content)} bytes)")
                    return artifact_resp.content, None
            except httpx.HTTPError as e:
                logger.warning(f"[SparkTool] Artifact retrieval failed, trying /fs/read: {e}")

        # 3. Fallback: read via /fs/read (handles binary via base64)
        try:
            read_resp = await client.post(f"{orchestrator_url}/fs/read", json={
                "user_id": str(context.get("user_id", "")),
                "conversation_id": str(context.get("conversation_id", "")),
                "chat_id": str(context.get("chat_id", "")),
                "sync_mode": True,
                "path": output_path,
            }, headers=headers)

            read_result = read_resp.json()
            if read_result.get("success") and read_result.get("content"):
                content_bytes = base64.b64decode(read_result["content"])
                if len(content_bytes) > 0:
                    logger.info(f"[SparkTool] Retrieved {ext} via /fs/read ({len(content_bytes)} bytes)")
                    return content_bytes, None
        except Exception as e:
            logger.warning(f"[SparkTool] /fs/read fallback failed: {e}")

        return None, "Output file not found after execution"


def _upload_generated_to_r2(user_id: str, chat_id: str, spark_id: str, content: bytes, framework: str) -> Optional[str]:
    """Upload generated document binary to R2. Returns r2_key or None."""
    ext = GENERATED_DOC_EXTENSIONS[framework]
    r2_key = f"{user_id}/chats/{chat_id}/sparks/{spark_id}/output.{ext}"

    try:
        from workspaces.services.workspace_storage import WorkspaceStorageService
        storage = WorkspaceStorageService()
        success = storage._upload_to_r2(r2_key, content, GENERATED_DOC_MIME_TYPES.get(framework))
        if success:
            logger.info(f"[SparkTool] Uploaded generated {ext} to R2: {r2_key}")
            return r2_key
        logger.error(f"[SparkTool] R2 upload failed for {r2_key}")
    except Exception as e:
        logger.error(f"[SparkTool] R2 upload error: {e}")
    return None


def _delete_r2_key(r2_key: str) -> None:
    """Delete an R2 object by key. Soft failure — logs but doesn't raise."""
    if not r2_key:
        return
    try:
        from workspaces.services.workspace_storage import WorkspaceStorageService
        storage = WorkspaceStorageService()
        storage._delete_from_r2(r2_key)
        logger.info(f"[SparkTool] Deleted R2 key: {r2_key}")
    except Exception as e:
        logger.warning(f"[SparkTool] Failed to delete R2 key {r2_key}: {e}")


@tool("create_spark", args_schema=CreateSparkInput)
async def create_spark(
    title: str,
    code: str,
    framework: str = "react",
    asset_ids: Optional[List[str]] = None,
) -> str:
    """
    Create an interactive React component (Spark) that renders live in the chat.

    Use this tool when the user asks you to:
    - Create an interactive visualization, chart, or dashboard
    - Build a small interactive app, game, or tool
    - Generate a UI component they can interact with
    - Create something visual that benefits from live rendering
    - Display generated images or videos in an interactive component

    Guidelines for creating sparks:
    - Write complete, self-contained React components
    - Export a default function component
    - Use Tailwind CSS for all styling (no external CSS)
    - Use React hooks (useState, useEffect, useMemo, useCallback) for interactivity
    - For charts, use Recharts (LineChart, BarChart, PieChart, etc.)
    - For icons, use Lucide React (imported as lucideReact.IconName)
    - Keep components focused and performant
    - Include sample data if needed for demonstration

    Using images/videos in sparks:
    - Pass asset_ids from generate_image, generate_video, or list tools
    - Access assets in code via: window.__SPARK_ASSETS__['asset-id-here']
    - Each asset provides: {url, type, filename, width, height}
    - Example: <img src={window.__SPARK_ASSETS__['abc-123'].url} />

    Example component with image:
    ```
    export default function ImageGallery() {
      const assets = window.__SPARK_ASSETS__ || {};
      const imageIds = Object.keys(assets).filter(id => assets[id].type === 'image');

      return (
        <div className="grid grid-cols-2 gap-4 p-4">
          {imageIds.map(id => (
            <img key={id} src={assets[id].url} alt={assets[id].filename}
                 className="rounded-lg shadow-md" />
          ))}
        </div>
      );
    }
    ```

    The spark will be rendered immediately in the chat for the user to interact with.
    """
    context = get_spark_tool_context()
    if not context:
        logger.warning("[SparkTool] No context set, proceeding without tracking")
        context = {}

    user_id = context.get("user_id")
    chat_id = context.get("chat_id")
    message_id = context.get("message_id")

    gate_denial = await _check_spark_generation_gate(user_id)
    if gate_denial is not None:
        return gate_denial

    logger.info(f"[SparkTool] Creating spark: title={title}, framework={framework}, code_len={len(code)}")

    try:
        # Detect dependencies from code
        dependencies = _detect_dependencies(code)

        # Create spark in database
        from sparks.models import Spark
        from conversations.models import Chat, Message
        from workspaces.models import Asset

        @sync_to_async
        def create_spark_record():
            spark = Spark(
                id=uuid.uuid4(),
                user_id=user_id,
                title=title,
                framework=framework,
                dependencies=dependencies,
                version=1,
            )

            # Link to chat and message if available
            if chat_id:
                try:
                    spark.chat = Chat.objects.get(id=chat_id)
                except Chat.DoesNotExist:
                    logger.warning(f"[SparkTool] Chat {chat_id} not found")

            if message_id:
                try:
                    spark.message = Message.objects.get(id=message_id)
                except Message.DoesNotExist:
                    logger.warning(f"[SparkTool] Message {message_id} not found")

            # Save code (handles inline vs R2 storage automatically)
            spark.save_code(code)
            spark.save()

            # Associate assets with the spark (ManyToMany requires save first)
            associated_assets = []
            if asset_ids:
                for aid in asset_ids:
                    try:
                        asset = Asset.objects.get(id=aid, user_id=user_id)
                        spark.assets.add(asset)
                        associated_assets.append({
                            'id': str(asset.id),
                            'type': 'video' if asset.mime_type and asset.mime_type.startswith('video/') else 'image',
                            'filename': asset.filename,
                            'url': _get_asset_url(asset),
                            'width': asset.width,
                            'height': asset.height,
                        })
                        logger.info(f"[SparkTool] Associated asset {aid} with spark {spark.id}")
                    except Asset.DoesNotExist:
                        logger.warning(f"[SparkTool] Asset {aid} not found for user {user_id}")

            return spark, associated_assets

        spark, associated_assets = await create_spark_record()

        logger.info(f"[SparkTool] Created spark {spark.id}: {title} with {len(associated_assets)} assets")

        # Execute generated document (PDF/DOCX) in sandbox
        download_url = None
        execution_error = None
        if framework in ('pdf', 'docx', 'xlsx') and context.get("auth_token"):
            logger.info(f"[SparkTool] Executing {framework} generation for spark {spark.id}")
            doc_content, exec_err = await _execute_generated_document(context, code, framework)
            if doc_content:
                r2_key = await sync_to_async(_upload_generated_to_r2)(
                    str(user_id), str(chat_id), str(spark.id), doc_content, framework,
                )
                if r2_key:
                    @sync_to_async
                    def _save_r2_key():
                        spark.generated_r2_key = r2_key
                        spark.save(update_fields=['generated_r2_key'])
                    await _save_r2_key()
                    download_url = f"/api/sparks/{spark.id}/download/"
                    logger.info(f"[SparkTool] {framework.upper()} generated and uploaded for spark {spark.id}")
                else:
                    execution_error = "Document generated but R2 upload failed"
            else:
                execution_error = exec_err
                logger.warning(f"[SparkTool] {framework.upper()} execution failed for spark {spark.id}: {exec_err}")

        response_spark = {
            "id": str(spark.id),
            "title": title,
            "framework": framework,
            "code": code,
            "version": 1,
            "dependencies": dependencies,
            "assets": associated_assets,
            "download_url": download_url,
        }
        if execution_error:
            response_spark["execution_error"] = execution_error

        return json.dumps({
            "status": "success",
            "message": f"Spark '{title}' created successfully with ID {spark.id}. Use this ID for any future updates.",
            "spark": response_spark,
        })

    except Exception as e:
        logger.exception(f"[SparkTool] Failed to create spark: {e}")
        return json.dumps({
            "status": "error",
            "error_type": "creation_failed",
            "message": f"Failed to create spark: {str(e)}",
        })


@tool("update_spark", args_schema=UpdateSparkInput)
async def update_spark(
    spark_id: str,
    code: str,
    title: Optional[str] = None,
    asset_ids: Optional[List[str]] = None,
) -> str:
    """
    Update an existing spark with new code.

    Use this tool when the user asks you to:
    - Modify or fix an existing spark
    - Add new features to a spark
    - Change the appearance or behavior of a spark
    - Add or change images/videos in the spark

    This creates a new version of the spark while preserving the history.

    Args:
        spark_id: The ID of the spark to update (from create_spark response)
        code: The complete updated component code
        title: Optional new title for the spark
        asset_ids: Optional list of asset IDs to associate (replaces previous assets if provided)
    """
    context = get_spark_tool_context()
    if not context:
        context = {}

    user_id = context.get("user_id")

    gate_denial = await _check_spark_generation_gate(user_id)
    if gate_denial is not None:
        return gate_denial

    logger.info(f"[SparkTool] Updating spark: id={spark_id}, user_id={user_id}")

    try:
        from sparks.models import Spark
        from workspaces.models import Asset

        @sync_to_async
        def update_spark_record():
            # Find the original spark
            try:
                original = Spark.objects.get(id=spark_id, user_id=user_id)
            except Spark.DoesNotExist:
                # Check if spark exists but belongs to different user (for better error message)
                exists_any = Spark.objects.filter(id=spark_id).exists()
                if exists_any:
                    logger.warning(f"[SparkTool] Spark {spark_id} exists but user_id mismatch")
                    return None, None, None, "Spark access denied"
                else:
                    logger.warning(f"[SparkTool] Spark {spark_id} does not exist")
                    return None, None, None, f"Spark with ID {spark_id} not found"

            # Get old code for diffing
            old_code = original.get_code()

            # Detect dependencies from new code
            dependencies = _detect_dependencies(code)

            # Create new version
            new_spark = Spark(
                id=uuid.uuid4(),
                user_id=user_id,
                chat=original.chat,
                message=original.message,
                title=title or original.title,
                framework=original.framework,
                dependencies=dependencies,
                version=original.version + 1,
                parent=original,
            )

            new_spark.save_code(code)
            new_spark.save()

            # Handle assets: use new list if provided, otherwise copy from original
            associated_assets = []
            if asset_ids is not None:
                # Use the new asset list
                for aid in asset_ids:
                    try:
                        asset = Asset.objects.get(id=aid, user_id=user_id)
                        new_spark.assets.add(asset)
                        associated_assets.append({
                            'id': str(asset.id),
                            'type': 'video' if asset.mime_type and asset.mime_type.startswith('video/') else 'image',
                            'filename': asset.filename,
                            'url': _get_asset_url(asset),
                            'width': asset.width,
                            'height': asset.height,
                        })
                    except Asset.DoesNotExist:
                        logger.warning(f"[SparkTool] Asset {aid} not found for user {user_id}")
            else:
                # Copy assets from original spark
                for asset in original.assets.all():
                    new_spark.assets.add(asset)
                    associated_assets.append({
                        'id': str(asset.id),
                        'type': 'video' if asset.mime_type and asset.mime_type.startswith('video/') else 'image',
                        'filename': asset.filename,
                        'url': _get_asset_url(asset),
                        'width': asset.width,
                        'height': asset.height,
                    })

            return new_spark, old_code, associated_assets, None

        spark, old_code, associated_assets, error = await update_spark_record()

        if error:
            return json.dumps({
                "status": "error",
                "error_type": "not_found",
                "message": f"{error}. Please check the conversation history for the correct spark ID from the create_spark response.",
            })

        logger.info(f"[SparkTool] Updated spark {spark_id} -> {spark.id} (v{spark.version}) with {len(associated_assets)} assets")

        # Re-execute generated document (PDF/DOCX) on code update
        download_url = None
        execution_error = None
        if spark.framework in ('pdf', 'docx', 'xlsx') and context.get("auth_token"):
            logger.info(f"[SparkTool] Re-executing {spark.framework} generation for updated spark {spark.id}")

            # Clean up old R2 key from parent if present
            @sync_to_async
            def _get_parent_r2_key():
                from sparks.models import Spark as SparkModel
                try:
                    parent = SparkModel.objects.get(id=spark_id)
                    return parent.generated_r2_key
                except SparkModel.DoesNotExist:
                    return ''
            old_r2_key = await _get_parent_r2_key()
            if old_r2_key:
                await sync_to_async(_delete_r2_key)(old_r2_key)

            doc_content, exec_err = await _execute_generated_document(context, code, spark.framework)
            if doc_content:
                chat_id = context.get("chat_id", "")
                r2_key = await sync_to_async(_upload_generated_to_r2)(
                    str(user_id), str(chat_id), str(spark.id), doc_content, spark.framework,
                )
                if r2_key:
                    @sync_to_async
                    def _save_r2_key():
                        spark.generated_r2_key = r2_key
                        spark.save(update_fields=['generated_r2_key'])
                    await _save_r2_key()
                    download_url = f"/api/sparks/{spark.id}/download/"
                else:
                    execution_error = "Document generated but R2 upload failed"
            else:
                execution_error = exec_err
                logger.warning(f"[SparkTool] {spark.framework.upper()} re-execution failed: {exec_err}")

        response_spark = {
            "id": str(spark.id),
            "title": spark.title,
            "framework": spark.framework,
            "code": code,
            "version": spark.version,
            "previous_version_id": spark_id,
            "old_code": old_code,
            "assets": associated_assets,
            "download_url": download_url,
        }
        if execution_error:
            response_spark["execution_error"] = execution_error

        return json.dumps({
            "status": "success",
            "message": f"Spark updated to version {spark.version} and is now displayed to the user.",
            "spark": response_spark,
        })

    except Exception as e:
        logger.exception(f"[SparkTool] Failed to update spark: {e}")
        return json.dumps({
            "status": "error",
            "error_type": "update_failed",
            "message": f"Failed to update spark: {str(e)}",
        })


# Export all tools
SPARK_TOOLS = [
    create_spark,
    update_spark,
]
