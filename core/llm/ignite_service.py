"""
Ignite Spark Deploy Service

Deploy an existing Next.js project from the sandbox workspace to Vercel.
No AI involved — just tar + upload. The coding agent scaffolding now happens
through the normal chat flow via prompt injection.
"""
import base64
import logging
from typing import Any, Dict, Optional

import httpx
from asgiref.sync import sync_to_async

from sterna.middleware.request_id import request_id_headers

logger = logging.getLogger(__name__)

VERCEL_DEPLOY_URL = "https://claude-skills-deploy.vercel.com/api/deploy"
MAX_TARBALL_BYTES = 52_428_800  # 50MB


async def _orchestrator_bash(
    orchestrator_url: str,
    auth_token: str,
    user_id: str,
    conversation_id: str,
    chat_id: str,
    command: str,
) -> Dict[str, Any]:
    """Run bash command in sandbox via orchestrator /fs/bash endpoint."""
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{orchestrator_url}/fs/bash",
            json={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "chat_id": chat_id,
                "command": command,
            },
            headers=request_id_headers({"Authorization": f"Bearer {auth_token}"}),
        )
        resp.raise_for_status()
        return resp.json()


async def _orchestrator_read_file(
    orchestrator_url: str,
    auth_token: str,
    user_id: str,
    conversation_id: str,
    chat_id: str,
    path: str,
) -> bytes:
    """Read file from sandbox via orchestrator /fs/read endpoint. Returns raw bytes."""
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{orchestrator_url}/fs/read",
            json={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "chat_id": chat_id,
                "path": path,
            },
            headers=request_id_headers({"Authorization": f"Bearer {auth_token}"}),
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", "")
        if data.get("is_binary"):
            return base64.b64decode(content)
        return content.encode("utf-8")


# ---------------------------------------------------------------------------
# Sync ORM helpers (wrapped for async usage)
# ---------------------------------------------------------------------------

def _get_spark(spark_id: str):
    from sparks.models import Spark
    return Spark.objects.get(id=spark_id)


def _get_deployment(deployment_id: str):
    from sparks.models import SparkDeployment
    return SparkDeployment.objects.get(id=deployment_id)


def _create_deployment(spark, user_id, deployment_id=None):
    from sparks.models import SparkDeployment
    kwargs = {"spark": spark, "user_id": user_id}
    if deployment_id:
        kwargs["id"] = deployment_id
    return SparkDeployment.objects.create(**kwargs)


def _find_active_deployment(spark, user_id):
    from sparks.models import SparkDeployment
    return SparkDeployment.objects.filter(
        spark=spark, user_id=user_id,
        status__in=["pending", "deploying"],
    ).first()


def _save_deployment(deployment, fields=None):
    if fields:
        deployment.save(update_fields=fields)
    else:
        deployment.save()


def _fail_deployment(deployment_id, error_message):
    """Fail a deployment by ID (safe for exception handlers where obj may be stale)."""
    from sparks.models import SparkDeployment
    SparkDeployment.objects.filter(id=deployment_id).exclude(
        status__in=["deployed", "failed"]
    ).update(status="failed", error_message=error_message)


# ---------------------------------------------------------------------------
# Main async deploy flow
# ---------------------------------------------------------------------------

async def deploy_spark_to_vercel(
    spark_id: str,
    user_id: str,
    auth_token: str,
    orchestrator_url: str,
    chat_id: str,
    conversation_id: str,
    deployment_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Deploy an existing Next.js project from the sandbox workspace to Vercel.

    Expects a project at /workspace/chat-{chat_id}/spark-app-{spark_id}/ with package.json.
    No AI involved — just tar + upload.

    Returns: {success, deployment_id, preview_url, claim_url, error}
    """
    # 1. Fetch spark, validate framework
    try:
        spark = await sync_to_async(_get_spark)(spark_id)
    except Exception:
        return {"success": False, "error": "Spark not found"}

    if spark.framework != "react":
        return {"success": False, "error": "Only React sparks can be deployed"}

    # 2. Get or create deployment record
    if deployment_id:
        try:
            deployment = await sync_to_async(_get_deployment)(deployment_id)
        except Exception:
            deployment = await sync_to_async(_create_deployment)(spark, user_id, deployment_id)
    else:
        active = await sync_to_async(_find_active_deployment)(spark, user_id)
        if active:
            return {
                "success": False,
                "error": "Deployment already in progress",
                "deployment_id": str(active.id),
            }
        deployment = await sync_to_async(_create_deployment)(spark, user_id)

    deploy_id = str(deployment.id)
    project_dir = f"/workspace/chat-{chat_id}/spark-app-{spark_id}"
    tarball_path = f"/workspace/chat-{chat_id}/spark-app-{spark_id}.tar.gz"

    try:
        # 3. Verify project exists
        verify = await _orchestrator_bash(
            orchestrator_url, auth_token, user_id, conversation_id, chat_id,
            f"test -f {project_dir}/package.json && echo 'OK' || echo 'MISSING'",
        )
        if "OK" not in verify.get("output", ""):
            deployment.status = "failed"
            deployment.error_message = "No project found. Click Ignite first to create the project."
            await sync_to_async(_save_deployment)(deployment, ["status", "error_message", "updated_at"])
            return {
                "success": False,
                "error": deployment.error_message,
                "deployment_id": deploy_id,
            }

        # 4. Create tarball
        deployment.status = "deploying"
        await sync_to_async(_save_deployment)(deployment, ["status", "updated_at"])

        tar_result = await _orchestrator_bash(
            orchestrator_url, auth_token, user_id, conversation_id, chat_id,
            f"tar -czf {tarball_path} -C {project_dir} --exclude=node_modules --exclude=.git --exclude=.next .",
        )
        if tar_result.get("exit_code", 1) != 0:
            deployment.status = "failed"
            deployment.error_message = f"Tar failed: {tar_result.get('output', '')[:200]}"
            await sync_to_async(_save_deployment)(deployment, ["status", "error_message", "updated_at"])
            return {
                "success": False,
                "error": deployment.error_message,
                "deployment_id": deploy_id,
            }

        # 5. Size guard
        size_result = await _orchestrator_bash(
            orchestrator_url, auth_token, user_id, conversation_id, chat_id,
            f"stat -c%s {tarball_path} 2>/dev/null || stat -f%z {tarball_path}",
        )
        try:
            size = int(size_result.get("output", "0").strip())
        except (ValueError, TypeError):
            size = 0
        if size > MAX_TARBALL_BYTES:
            deployment.status = "failed"
            deployment.error_message = "Project too large for deployment (max 50MB)"
            await sync_to_async(_save_deployment)(deployment, ["status", "error_message", "updated_at"])
            return {
                "success": False,
                "error": deployment.error_message,
                "deployment_id": deploy_id,
            }

        # 6. Read tarball (path must be relative to chat workspace for /fs/read)
        tarball_relative = f"spark-app-{spark_id}.tar.gz"
        tarball_bytes = await _orchestrator_read_file(
            orchestrator_url, auth_token, user_id, conversation_id, chat_id,
            tarball_relative,
        )

        # 7. Deploy to Vercel
        logger.info(
            f"[Deploy] Uploading tarball to Vercel: {len(tarball_bytes)} bytes, "
            f"first 4 bytes: {tarball_bytes[:4].hex()}"
        )

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                VERCEL_DEPLOY_URL,
                files={"file": ("project.tar.gz", tarball_bytes, "application/gzip")},
                data={"framework": "nextjs"},
            )
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")
            deploy_result = resp.json()

        # 8. Save result
        deployment.preview_url = deploy_result.get("previewUrl", "")
        deployment.claim_url = deploy_result.get("claimUrl", "")
        deployment.deployment_id = deploy_result.get("deploymentId", "")
        deployment.project_id = deploy_result.get("projectId", "")
        deployment.status = "deployed"
        await sync_to_async(_save_deployment)(deployment)

        logger.info(
            f"[Deploy] Spark {spark_id} deployed: preview={deployment.preview_url}"
        )

        return {
            "success": True,
            "deployment_id": deploy_id,
            "preview_url": deployment.preview_url,
            "claim_url": deployment.claim_url,
        }

    except Exception as e:
        logger.exception(f"[Deploy] Failed for spark {spark_id}")
        deployment.status = "failed"
        deployment.error_message = f"Deployment failed: {e}"
        try:
            await sync_to_async(_save_deployment)(deployment, ["status", "error_message", "updated_at"])
        except Exception:
            await sync_to_async(_fail_deployment)(deploy_id, str(e))
        return {
            "success": False,
            "error": str(e),
            "deployment_id": deploy_id,
        }
