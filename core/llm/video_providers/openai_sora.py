"""
OpenAI Sora video generation provider.

This provider implements the OpenAI Video API for Sora and Sora Pro models.
API Documentation: https://platform.openai.com/docs/guides/video-generation

Model configuration is fetched from the database (VideoModelCatalog).
"""

import asyncio
import logging
import time
from typing import List, Optional

import httpx
from asgiref.sync import sync_to_async
from django.conf import settings

from .base import (
    BaseVideoProvider,
    ContentPolicyError,
    GenerationTimeoutError,
    InvalidInputError,
    InvalidPromptError,
    RateLimitError,
    VideoGenerationInput,
    VideoGenerationResult,
    VideoInputType,
    VideoProviderError,
    VideoStatus,
)
from .constants import OPENAI_API_CONFIG

logger = logging.getLogger(__name__)


class OpenAISoraProvider(BaseVideoProvider):
    """
    OpenAI Sora video generation provider.

    Supports text-to-video generation with sora-2 (standard) and sora-2-pro models.
    Uses async HTTP client for non-blocking operations.

    Model configuration is fetched from the database (VideoModelCatalog).
    """

    # Default values (can be overridden by database config)
    DEFAULT_DURATION = 4
    DEFAULT_FPS = 24
    DEFAULT_RESOLUTION = "1280x720"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the OpenAI Sora provider.

        Args:
            api_key: OpenAI API key (defaults to settings.OPENAI_API_KEY)
        """
        self.api_key = api_key or getattr(settings, "OPENAI_API_KEY", "")
        self.config = OPENAI_API_CONFIG
        self._client: Optional[httpx.AsyncClient] = None
        # Cache for job metadata (duration, size) - used as fallback if API doesn't return it
        self._job_metadata: dict[str, dict] = {}

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "openai"

    @property
    def supported_input_types(self) -> List[VideoInputType]:
        """OpenAI Sora only supports text-to-video generation."""
        return [VideoInputType.TEXT]

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(
                    connect=self.config.connect_timeout_seconds,
                    read=self.config.read_timeout_seconds,
                    write=30.0,
                    pool=30.0,
                ),
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def generate(
        self,
        model_id: str,
        input_data: VideoGenerationInput,
    ) -> VideoGenerationResult:
        """
        Start a video generation job.

        Args:
            model_id: The model identifier (e.g., 'sora-2', 'sora-2-pro')
            input_data: Unified input structure with prompt and parameters

        Returns:
            VideoGenerationResult with job_id and initial status

        Raises:
            InvalidInputError: If input doesn't match model requirements
            VideoProviderError: If generation fails to start
        """
        from llm.models import VideoModelCatalog

        # Validate input type - OpenAI Sora only supports text-to-video
        input_data.validate_for_input_type(VideoInputType.TEXT)

        # Get model config from database (wrapped for async context)
        model_config = await sync_to_async(VideoModelCatalog.get_by_model_id)(model_id)
        if not model_config:
            raise InvalidInputError(f"Unknown model: {model_id}")

        # Extract and validate parameters
        prompt = input_data.prompt
        duration = input_data.duration or self.DEFAULT_DURATION

        # Get valid durations from model capabilities
        capabilities = model_config.capabilities or {}
        valid_durations = capabilities.get("valid_durations", [4, 8, 12])
        max_duration = capabilities.get("max_duration", 12)

        # Clamp duration to model's max
        duration = min(duration, max_duration)

        # Round to nearest valid duration
        closest_duration = min(valid_durations, key=lambda x: abs(x - duration))
        seconds_str = str(closest_duration)

        # Build resolution string
        if input_data.resolution:
            resolution = input_data.resolution
        else:
            # Default resolution based on model
            resolution = self.DEFAULT_RESOLUTION

        # Build request payload using correct API parameter names
        # Note: OpenAI uses 'seconds' (string) and 'size', not 'duration' and 'resolution'
        payload = {
            "model": model_id,
            "prompt": prompt,
            "seconds": seconds_str,
            "size": resolution,
        }

        logger.info(
            f"[OpenAI Sora] Starting video generation: model={model_id}, "
            f"duration={closest_duration}s, resolution={resolution}"
        )

        try:
            client = await self._get_client()

            logger.info(f"[OpenAI Sora] POST {self.config.videos_endpoint} with payload: {payload}")
            response = await client.post(self.config.videos_endpoint, json=payload)

            logger.info(f"[OpenAI Sora] Response status: {response.status_code}")
            logger.info(f"[OpenAI Sora] Response body: {response.text[:500]}")

            if response.status_code == 429:
                logger.warning("[OpenAI Sora] Rate limit exceeded")
                raise RateLimitError("OpenAI rate limit exceeded")

            if response.status_code == 403:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", "Forbidden")
                logger.error(f"[OpenAI Sora] 403 Forbidden: {error_msg}")
                raise VideoProviderError(f"Access denied: {error_msg}")

            if response.status_code == 400:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", "Bad request")
                if "content_policy" in error_msg.lower():
                    raise ContentPolicyError(error_msg)
                raise InvalidPromptError(error_msg)

            response.raise_for_status()
            data = response.json()

            job_id = data["id"]
            logger.info(f"[OpenAI Sora] Job created: {job_id}")

            # Cache the request parameters for use as fallback when checking status
            self._job_metadata[job_id] = {
                "seconds": closest_duration,
                "size": resolution,
            }

            return VideoGenerationResult(
                status=VideoStatus(data.get("status", "queued")),
                job_id=job_id,
                provider=self.provider_name,
                model=model_id,
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"[OpenAI Sora] HTTP error: {e}")
            raise VideoProviderError(f"HTTP error: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"[OpenAI Sora] Request error: {e}")
            raise VideoProviderError(f"Request failed: {str(e)}")

    async def check_status(self, job_id: str) -> VideoGenerationResult:
        """
        Check the status of a video generation job.

        Args:
            job_id: The job ID to check

        Returns:
            VideoGenerationResult with current status
        """
        try:
            client = await self._get_client()
            response = await client.get(f"{self.config.videos_endpoint}/{job_id}")

            if response.status_code == 404:
                return VideoGenerationResult(
                    status=VideoStatus.FAILED,
                    job_id=job_id,
                    provider=self.provider_name,
                    error_message="Job not found",
                    error_code="not_found",
                )

            response.raise_for_status()
            data = response.json()

            # Debug: log the full response to understand structure
            logger.info(f"[OpenAI Sora] Status response for {job_id}: {data}")

            status_str = data.get("status", "in_progress")

            # Map OpenAI status to our enum
            status_map = {
                "queued": VideoStatus.QUEUED,
                "in_progress": VideoStatus.IN_PROGRESS,
                "processing": VideoStatus.IN_PROGRESS,
                "completed": VideoStatus.COMPLETED,
                "succeeded": VideoStatus.COMPLETED,
                "failed": VideoStatus.FAILED,
                "error": VideoStatus.FAILED,
            }
            status = status_map.get(status_str, VideoStatus.IN_PROGRESS)

            result = VideoGenerationResult(
                status=status,
                job_id=job_id,
                provider=self.provider_name,
                model=data.get("model", "sora-2"),
            )

            if status == VideoStatus.COMPLETED:
                # Get cached metadata from generate() as fallback
                cached = self._job_metadata.get(job_id, {})

                # Handle different field names from OpenAI API
                # Duration can be 'duration' (int) or 'seconds' (string)
                duration = data.get("duration") or data.get("seconds") or cached.get("seconds")
                if duration:
                    result.duration_seconds = int(duration) if isinstance(duration, str) else duration
                else:
                    result.duration_seconds = 0

                # Dimensions can be 'width'/'height' or parsed from 'size' (e.g. "1280x720")
                size_str = data.get("size") or cached.get("size", "")
                if data.get("width") and data.get("height"):
                    result.width = data.get("width")
                    result.height = data.get("height")
                elif size_str and "x" in size_str:
                    try:
                        w, h = size_str.split("x")
                        result.width = int(w)
                        result.height = int(h)
                    except (ValueError, AttributeError):
                        result.width = 0
                        result.height = 0
                else:
                    result.width = 0
                    result.height = 0

                result.fps = data.get("fps", self.DEFAULT_FPS)
                logger.info(
                    f"[OpenAI Sora] Job {job_id} completed: "
                    f"{result.width}x{result.height}, {result.duration_seconds}s"
                )

                # Clean up cached metadata
                self._job_metadata.pop(job_id, None)
            elif status == VideoStatus.FAILED:
                error_info = data.get("error", {})
                result.error_message = error_info.get("message", "Unknown error")
                result.error_code = error_info.get("code", "unknown")
                logger.error(
                    f"[OpenAI Sora] Job {job_id} failed: {result.error_message}"
                )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"[OpenAI Sora] Status check failed: {e}")
            raise VideoProviderError(f"Status check failed: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"[OpenAI Sora] Request error checking status: {e}")
            raise VideoProviderError(f"Request failed: {str(e)}")

    async def download(self, job_id: str) -> bytes:
        """
        Download the completed video.

        Args:
            job_id: The job ID of a completed generation

        Returns:
            Video content as bytes
        """
        logger.info(f"[OpenAI Sora] Downloading video for job {job_id}")

        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.config.videos_endpoint}/{job_id}/content"
            )

            if response.status_code == 404:
                raise VideoProviderError("Video not found or not ready")

            if response.status_code == 202:
                raise VideoProviderError("Video is still processing")

            response.raise_for_status()

            content = response.content
            logger.info(
                f"[OpenAI Sora] Downloaded {len(content)} bytes for job {job_id}"
            )

            return content

        except httpx.HTTPStatusError as e:
            logger.error(f"[OpenAI Sora] Download failed: {e}")
            raise VideoProviderError(f"Download failed: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"[OpenAI Sora] Request error during download: {e}")
            raise VideoProviderError(f"Download request failed: {str(e)}")

    async def poll_until_complete(
        self,
        job_id: str,
        timeout_seconds: Optional[int] = None,
        poll_interval: Optional[int] = None,
    ) -> VideoGenerationResult:
        """
        Poll until video generation completes or times out.

        Args:
            job_id: The job ID to poll
            timeout_seconds: Maximum time to wait (uses config default if None)
            poll_interval: Time between polls (uses config default if None)

        Returns:
            VideoGenerationResult with final status

        Raises:
            GenerationTimeoutError: If the job times out
        """
        timeout = timeout_seconds or self.config.max_poll_timeout_seconds
        interval = poll_interval or self.config.poll_interval_seconds

        start = time.time()
        poll_count = 0

        logger.info(
            f"[OpenAI Sora] Polling job {job_id} "
            f"(timeout={timeout}s, interval={interval}s)"
        )

        while time.time() - start < timeout:
            poll_count += 1
            result = await self.check_status(job_id)

            if result.is_complete():
                logger.info(
                    f"[OpenAI Sora] Job {job_id} completed after {poll_count} polls"
                )
                return result

            if result.is_failed():
                logger.warning(
                    f"[OpenAI Sora] Job {job_id} failed after {poll_count} polls: "
                    f"{result.error_message}"
                )
                return result

            elapsed = time.time() - start
            logger.debug(
                f"[OpenAI Sora] Job {job_id} still {result.status.value} "
                f"({elapsed:.1f}s elapsed, poll #{poll_count})"
            )

            await asyncio.sleep(interval)

        elapsed = time.time() - start
        logger.error(
            f"[OpenAI Sora] Job {job_id} timed out after {elapsed:.1f}s "
            f"({poll_count} polls)"
        )
        raise GenerationTimeoutError(
            f"Video generation timed out after {timeout} seconds"
        )

    # Note: calculate_cost is inherited from BaseVideoProvider and uses database pricing
