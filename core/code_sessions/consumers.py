"""WebSocket consumer for real-time job status updates.

This module provides a WebSocket consumer that allows clients to subscribe
to job updates and receive real-time progress notifications.
"""

import logging
from typing import Set

from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer  # type: ignore[import-untyped]
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


class CodeJobConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for code job status updates.

    Protocol:
    - Client connects with JWT token via query string
    - Client sends: {"action": "subscribe", "job_id": "..."}
    - Client sends: {"action": "unsubscribe", "job_id": "..."}
    - Server sends: {"type": "job_status", "job_id": "...", "status": "...", ...}

    Channel Groups:
    - job_{job_id}: Group for each job, receives status updates
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.subscribed_jobs: Set[str] = set()

    async def connect(self):
        """Handle WebSocket connection."""
        # Get user from scope (set by JWT middleware)
        self.user = self.scope.get("user")

        # Reject unauthenticated connections
        if not self.user or isinstance(self.user, AnonymousUser):
            logger.warning("Rejected unauthenticated WebSocket connection")
            await self.close(code=4001)
            return

        # Accept the connection
        await self.accept()

        logger.info(f"Code job WebSocket connected: user={self.user.id}")

        # Send connection confirmation
        await self.send_json({
            "type": "connected",
            "user_id": str(self.user.id),
        })

    async def disconnect(self, close_code):
        """Handle WebSocket disconnect."""
        # Leave all job groups
        for job_id in self.subscribed_jobs:
            await self.channel_layer.group_discard(
                f"job_{job_id}",
                self.channel_name,
            )

        logger.info(
            f"Code job WebSocket disconnected: user={self.user.id if self.user else 'unknown'}, "
            f"code={close_code}, subscriptions={len(self.subscribed_jobs)}"
        )

        self.subscribed_jobs.clear()

    async def receive_json(self, content):
        """Handle incoming JSON messages.

        Supported actions:
        - subscribe: Subscribe to job updates
        - unsubscribe: Unsubscribe from job updates
        """
        action = content.get("action")

        if action == "subscribe":
            job_id = content.get("job_id")
            if job_id:
                await self.subscribe_to_job(job_id)
            else:
                await self.send_json({
                    "type": "error",
                    "message": "Missing job_id",
                })

        elif action == "unsubscribe":
            job_id = content.get("job_id")
            if job_id:
                await self.unsubscribe_from_job(job_id)
            else:
                await self.send_json({
                    "type": "error",
                    "message": "Missing job_id",
                })

        elif action == "ping":
            # Keepalive ping
            await self.send_json({"type": "pong"})

        else:
            await self.send_json({
                "type": "error",
                "message": f"Unknown action: {action}",
            })

    async def subscribe_to_job(self, job_id: str):
        """Subscribe to updates for a job.

        Verifies that the user owns the job before subscribing.

        Args:
            job_id: UUID of the job to subscribe to
        """
        # Verify user owns this job
        if not await self._check_job_ownership(job_id):
            await self.send_json({
                "type": "error",
                "message": "Access denied to job",
                "job_id": job_id,
            })
            return

        # Add to channel group
        group_name = f"job_{job_id}"
        await self.channel_layer.group_add(group_name, self.channel_name)
        self.subscribed_jobs.add(job_id)

        logger.debug(f"User {self.user.id} subscribed to job {job_id}")

        # Send confirmation
        await self.send_json({
            "type": "subscribed",
            "job_id": job_id,
        })

        # Send current job status
        await self._send_current_job_status(job_id)

    async def unsubscribe_from_job(self, job_id: str):
        """Unsubscribe from job updates.

        Args:
            job_id: UUID of the job to unsubscribe from
        """
        group_name = f"job_{job_id}"
        await self.channel_layer.group_discard(group_name, self.channel_name)
        self.subscribed_jobs.discard(job_id)

        logger.debug(f"User {self.user.id} unsubscribed from job {job_id}")

        await self.send_json({
            "type": "unsubscribed",
            "job_id": job_id,
        })

    @sync_to_async
    def _check_job_ownership(self, job_id: str) -> bool:
        """Check if the current user owns the job.

        Args:
            job_id: UUID of the job

        Returns:
            bool: True if user owns the job
        """
        from .models import CodeJob

        return CodeJob.objects.filter(
            id=job_id,
            session__user=self.user,
        ).exists()

    @sync_to_async
    def _get_job_status(self, job_id: str) -> dict | None:
        """Get current status of a job.

        Args:
            job_id: UUID of the job

        Returns:
            dict | None: Job status data or None if not found
        """
        from .models import CodeJob

        try:
            job = CodeJob.objects.get(id=job_id)
            return {
                "job_id": str(job.id),
                "status": job.status,
                "progress": job.progress,
                "message": job.progress_message,
                "result": job.result,
                "files_modified": job.files_modified,
                "error_message": job.error_message,
                "steps": job.steps,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            }
        except CodeJob.DoesNotExist:
            return None

    async def _send_current_job_status(self, job_id: str):
        """Send current job status to the client.

        Args:
            job_id: UUID of the job
        """
        status_data = await self._get_job_status(job_id)
        if status_data:
            await self.send_json({
                "type": "job_status",
                **status_data,
            })

    # ==================== Channel Layer Event Handlers ====================

    async def job_status_update(self, event):
        """Handle job status update from channel layer.

        This method is called when a task sends an update via:
        channel_layer.group_send(f"job_{job_id}", {"type": "job_status_update", ...})

        Args:
            event: Event data containing job status information
        """
        # Forward the update to the WebSocket client
        await self.send_json({
            "type": "job_status",
            "job_id": event.get("job_id"),
            "status": event.get("status"),
            "progress": event.get("progress"),
            "message": event.get("message"),
            "timestamp": event.get("timestamp"),
            "result": event.get("result"),
            "files_modified": event.get("files_modified"),
            "error_message": event.get("error_message"),
            "steps": event.get("steps"),
        })

    async def job_step_event(self, event):
        """Handle step events from channel layer (text, tool_executing, tool_executed).

        This method is called when a task sends a step event via:
        channel_layer.group_send(f"job_{job_id}", {"type": "job_step_event", ...})

        Args:
            event: Event data containing step information
        """
        step_type = event.get("step_type")

        # Forward the step event to the WebSocket client
        await self.send_json({
            "type": "job_step",
            "job_id": event.get("job_id"),
            "step_type": step_type,
            "timestamp": event.get("timestamp"),
            # Text step fields
            "content": event.get("content"),
            "iteration": event.get("iteration"),
            # Tool execution fields
            "tool_call_id": event.get("tool_call_id"),
            "tool_name": event.get("tool_name"),
            "arguments": event.get("arguments"),
            "result": event.get("result"),
            "success": event.get("success"),
        })
