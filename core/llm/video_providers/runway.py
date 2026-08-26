"""
Runway video generation provider.

Supports all Runway API models:
- Text-to-video: veo3.1, veo3.1_fast, veo3
- Image-to-video: gen4_turbo
- Image/Video-to-video: gen4_aleph
- Video upscaling: upscale_v1
- Character animation: act_two

API Documentation: https://docs.dev.runwayml.com/
"""

import asyncio
import logging
import time
from decimal import Decimal
from typing import Dict, List, Optional, Any

import httpx
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

logger = logging.getLogger(__name__)


# =============================================================================
# Runway API Configuration
# =============================================================================

RUNWAY_BASE_URL = "https://api.dev.runwayml.com/v1"
RUNWAY_API_VERSION = "2024-11-06"

# Model to endpoint mapping
MODEL_ENDPOINTS: Dict[str, str] = {
    # Text-to-video models
    "veo3.1_fast": "/text_to_video",
    "veo3.1": "/text_to_video",
    "veo3": "/text_to_video",
    # Image-to-video models
    "gen4_turbo": "/image_to_video",
    # Video-to-video models
    "gen4_aleph": "/video_to_video",
    # Character animation (Act Two)
    "act_two": "/character_performance",
}

# Model to input type mapping
MODEL_INPUT_TYPES: Dict[str, VideoInputType] = {
    "veo3.1_fast": VideoInputType.TEXT,
    "veo3.1": VideoInputType.TEXT,
    "veo3": VideoInputType.TEXT,
    "gen4_turbo": VideoInputType.IMAGE,
    "gen4_aleph": VideoInputType.VIDEO,
    "act_two": VideoInputType.IMAGE_AUDIO,
}

# Default model
DEFAULT_MODEL = "veo3.1_fast"


class RunwayProvider(BaseVideoProvider):
    """
    Runway video generation provider.

    Supports all Runway models with different input types:
    - Text-to-video (veo3.1, veo3.1_fast, veo3)
    - Image-to-video (gen4_turbo)
    - Image/Video-to-video (gen4_aleph)
    - Video upscaling (upscale_v1)
    - Character animation (act_two)

    Uses async HTTP client for non-blocking operations.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the Runway provider.

        Args:
            api_key: Runway API key (defaults to settings.RUNWAY_API_KEY)
        """
        self.api_key = api_key or getattr(settings, "RUNWAY_API_KEY", "")
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "runway"

    @property
    def supported_input_types(self) -> List[VideoInputType]:
        """Return list of input types this provider supports."""
        return [
            VideoInputType.TEXT,
            VideoInputType.IMAGE,
            VideoInputType.VIDEO,
            VideoInputType.IMAGE_AUDIO,
        ]

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=RUNWAY_BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "X-Runway-Version": RUNWAY_API_VERSION,
                },
                timeout=httpx.Timeout(
                    connect=30.0,
                    read=300.0,
                    write=60.0,
                    pool=30.0,
                ),
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _get_endpoint_for_model(self, model_id: str) -> str:
        """Get the API endpoint for a model."""
        endpoint = MODEL_ENDPOINTS.get(model_id)
        if not endpoint:
            raise ValueError(f"Unknown Runway model: {model_id}")
        return endpoint

    def _get_input_type_for_model(self, model_id: str) -> VideoInputType:
        """Get the required input type for a model."""
        input_type = MODEL_INPUT_TYPES.get(model_id)
        if not input_type:
            raise ValueError(f"Unknown Runway model: {model_id}")
        return input_type

    def _build_payload(
        self,
        model_id: str,
        input_data: VideoGenerationInput,
    ) -> Dict[str, Any]:
        """
        Build the API payload based on model and input type.

        Args:
            model_id: The Runway model ID
            input_data: Unified input structure

        Returns:
            API payload dictionary
        """
        endpoint = self._get_endpoint_for_model(model_id)

        if endpoint == "/text_to_video":
            # Text-to-video payload
            payload: Dict[str, Any] = {
                "model": model_id,
                "promptText": input_data.prompt,
            }

            # Add duration (Veo supports 4, 6, or 8 seconds)
            if input_data.duration:
                requested_duration = input_data.duration
                valid_durations = [4, 6, 8]
                duration = min(valid_durations, key=lambda x: abs(x - requested_duration))
                payload["duration"] = duration

            # Add aspect ratio
            if input_data.aspect_ratio:
                ratio_map = {
                    "16:9": "1280:720",
                    "9:16": "720:1280",
                    "1:1": "960:960",
                    "4:3": "1104:832",
                    "3:4": "832:1104",
                }
                payload["ratio"] = ratio_map.get(input_data.aspect_ratio, "1280:720")
            elif input_data.resolution:
                # Parse resolution to ratio format
                try:
                    width, height = map(int, input_data.resolution.split("x"))
                    payload["ratio"] = f"{width}:{height}"
                except ValueError:
                    payload["ratio"] = "1280:720"
            else:
                payload["ratio"] = "1280:720"

            # Optional audio generation (veo3.1 only)
            if input_data.generate_audio and model_id == "veo3.1":
                payload["audio"] = True

            return payload

        elif endpoint == "/image_to_video":
            # Image-to-video payload
            # API docs: https://docs.dev.runwayml.com/api/
            # Supported models: gen4_turbo, veo3.1, gen3a_turbo, veo3.1_fast, veo3
            payload = {
                "model": model_id,
            }

            # Add image input (required)
            if input_data.image_url:
                payload["promptImage"] = input_data.image_url
            elif input_data.image_bytes:
                raise InvalidInputError("Direct image bytes not supported, use image_url")
            else:
                raise InvalidInputError("Image URL is required for image-to-video")

            # Optional text prompt for guidance
            if input_data.prompt:
                payload["promptText"] = input_data.prompt

            # Add duration (gen4_turbo supports 5 or 10 seconds)
            if input_data.duration:
                requested_duration = input_data.duration
                valid_durations = [5, 10]
                duration = min(valid_durations, key=lambda x: abs(x - requested_duration))
                payload["duration"] = duration
            else:
                payload["duration"] = 5

            # Add aspect ratio (required)
            ratio_map = {
                "16:9": "1280:720",
                "9:16": "720:1280",
                "1:1": "960:960",
                "4:3": "1104:832",
                "3:4": "832:1104",
            }
            payload["ratio"] = ratio_map.get(input_data.aspect_ratio, "1280:720") if input_data.aspect_ratio else "1280:720"

            return payload

        elif endpoint == "/video_to_video":
            # Video-to-video payload (gen4_aleph)
            # API docs: https://docs.dev.runwayml.com/api/
            payload = {
                "model": model_id,
            }

            # Video input (required)
            if input_data.video_url:
                payload["videoUri"] = input_data.video_url
            elif input_data.video_bytes:
                raise InvalidInputError("Direct video bytes not supported, use video_url")
            else:
                raise InvalidInputError("Video URL is required for video-to-video")

            # Text prompt (required)
            if input_data.prompt:
                payload["promptText"] = input_data.prompt
            else:
                payload["promptText"] = "Transform this video"

            # Optional image references
            if input_data.image_url:
                payload["references"] = [{
                    "type": "image",
                    "uri": input_data.image_url,
                }]

            return payload

        elif endpoint == "/character_performance":
            # Character animation (Act Two) payload
            # API docs: https://docs.dev.runwayml.com/api/
            payload = {
                "model": model_id,
            }

            # Character input (image or video)
            if input_data.image_url:
                # Determine if it's a video or image based on URL/mime
                is_video_char = any(ext in input_data.image_url.lower() for ext in ['.mp4', '.webm', '.mov', 'video/'])
                payload["character"] = {
                    "type": "video" if is_video_char else "image",
                    "uri": input_data.image_url,
                }
            elif input_data.image_bytes:
                raise InvalidInputError("Direct image bytes not supported, use image_url")
            else:
                raise InvalidInputError("Character image/video URL is required for character animation")

            # Reference performance input (must be a video)
            # The reference can come from audio_url (legacy) or video_url
            reference_url = input_data.audio_url or input_data.video_url
            if reference_url:
                payload["reference"] = {
                    "type": "video",
                    "uri": reference_url,
                }
            else:
                raise InvalidInputError(
                    "Reference video URL is required for character animation. "
                    "Provide a video of a person performing (3-30 seconds)."
                )

            # Optional parameters
            if input_data.aspect_ratio:
                ratio_map = {
                    "16:9": "1280:720",
                    "9:16": "720:1280",
                    "1:1": "960:960",
                    "4:3": "1104:832",
                    "3:4": "832:1104",
                }
                payload["ratio"] = ratio_map.get(input_data.aspect_ratio, "1280:720")

            return payload

        raise ValueError(f"Unknown endpoint: {endpoint}")

    async def generate(
        self,
        model_id: str,
        input_data: VideoGenerationInput,
    ) -> VideoGenerationResult:
        """
        Start a video generation job.

        Args:
            model_id: The Runway model ID
            input_data: Unified input structure

        Returns:
            VideoGenerationResult with job_id and initial status
        """
        # Get and validate input type for model
        required_input_type = self._get_input_type_for_model(model_id)
        input_data.validate_for_input_type(required_input_type)

        # Get endpoint
        endpoint = self._get_endpoint_for_model(model_id)

        # Build payload
        payload = self._build_payload(model_id, input_data)

        logger.info(
            f"[Runway] Starting generation: model={model_id}, "
            f"endpoint={endpoint}, input_type={required_input_type.value}"
        )
        logger.debug(f"[Runway] Payload: {payload}")

        try:
            client = await self._get_client()
            response = await client.post(endpoint, json=payload)

            logger.info(f"[Runway] Response status: {response.status_code}")

            if response.status_code == 429:
                logger.warning("[Runway] Rate limit exceeded")
                raise RateLimitError("Runway rate limit exceeded")

            if response.status_code == 401:
                error_data = response.json()
                error_msg = error_data.get("error", "Unauthorized")
                logger.error(f"[Runway] 401 Unauthorized: {error_msg}")
                raise VideoProviderError(f"Authentication failed: {error_msg}")

            if response.status_code == 400:
                error_data = response.json()
                error_msg = error_data.get("error", "Bad request")
                logger.error(f"[Runway] 400 Bad Request: {error_msg}")

                if "content" in error_msg.lower() or "policy" in error_msg.lower():
                    raise ContentPolicyError(error_msg)
                if "prompt" in error_msg.lower():
                    raise InvalidPromptError(error_msg)
                raise InvalidInputError(error_msg)

            response.raise_for_status()
            data = response.json()

            job_id = data.get("id")
            logger.info(f"[Runway] Job created: {job_id}")

            return VideoGenerationResult(
                status=VideoStatus.QUEUED,
                job_id=job_id,
                provider=self.provider_name,
                model=model_id,
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"[Runway] HTTP error: {e}")
            raise VideoProviderError(f"HTTP error: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"[Runway] Request error: {e}")
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
            response = await client.get(f"/tasks/{job_id}")

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

            status_str = data.get("status", "PENDING")
            logger.info(f"[Runway] Job {job_id} status: {status_str}")

            # Map Runway status to our enum
            status_map = {
                "PENDING": VideoStatus.QUEUED,
                "RUNNING": VideoStatus.IN_PROGRESS,
                "THROTTLED": VideoStatus.QUEUED,  # Waiting in queue
                "SUCCEEDED": VideoStatus.COMPLETED,
                "FAILED": VideoStatus.FAILED,
                "CANCELLED": VideoStatus.FAILED,
            }
            status = status_map.get(status_str, VideoStatus.IN_PROGRESS)

            # Get model from task options
            model = data.get("options", {}).get("model", DEFAULT_MODEL)

            result = VideoGenerationResult(
                status=status,
                job_id=job_id,
                provider=self.provider_name,
                model=model,
            )

            if status == VideoStatus.COMPLETED:
                # Get output metadata
                output = data.get("output", [])
                if output:
                    result.output_url = output[0] if isinstance(output, list) else output

                # Get dimensions from options or defaults
                options = data.get("options", {})
                ratio = options.get("ratio", "1280:720")
                try:
                    width, height = map(int, ratio.replace(":", "x").split("x"))
                except (ValueError, AttributeError):
                    width, height = 1280, 720

                result.width = width
                result.height = height
                result.duration_seconds = options.get("duration", 4)
                result.fps = 24

                logger.info(
                    f"[Runway] Job {job_id} completed: "
                    f"{result.width}x{result.height}, {result.duration_seconds}s"
                )

            elif status == VideoStatus.FAILED:
                failure = data.get("failure", {})
                # Handle both string and dict failure formats from Runway API
                if isinstance(failure, str):
                    result.error_message = failure
                    result.error_code = "unknown"
                elif isinstance(failure, dict):
                    result.error_message = failure.get("reason", "Unknown error")
                    result.error_code = failure.get("code", "unknown")
                else:
                    result.error_message = str(failure) if failure else "Unknown error"
                    result.error_code = "unknown"
                logger.error(f"[Runway] Job {job_id} failed: {result.error_message}")

            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"[Runway] Status check failed: {e}")
            raise VideoProviderError(f"Status check failed: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"[Runway] Request error checking status: {e}")
            raise VideoProviderError(f"Request failed: {str(e)}")

    async def download(self, job_id: str) -> bytes:
        """
        Download the completed video.

        Args:
            job_id: The job ID of a completed generation

        Returns:
            Video content as bytes
        """
        logger.info(f"[Runway] Downloading video for job {job_id}")

        try:
            client = await self._get_client()

            # First get the task to get the output URL
            response = await client.get(f"/tasks/{job_id}")

            if response.status_code == 404:
                raise VideoProviderError("Video not found")

            response.raise_for_status()
            data = response.json()

            if data.get("status") != "SUCCEEDED":
                raise VideoProviderError("Video is not ready for download")

            # Get the output URL
            output = data.get("output", [])
            if not output:
                raise VideoProviderError("No video output available")

            video_url = output[0] if isinstance(output, list) else output

            # Download the video from the URL
            async with httpx.AsyncClient(timeout=300.0) as download_client:
                video_response = await download_client.get(video_url)
                video_response.raise_for_status()
                content = video_response.content

            logger.info(f"[Runway] Downloaded {len(content)} bytes for job {job_id}")

            return content

        except httpx.HTTPStatusError as e:
            logger.error(f"[Runway] Download failed: {e}")
            raise VideoProviderError(f"Download failed: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"[Runway] Request error during download: {e}")
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
            timeout_seconds: Maximum time to wait (default: 600s)
            poll_interval: Time between polls (default: 5s)

        Returns:
            VideoGenerationResult with final status

        Raises:
            GenerationTimeoutError: If the job times out
        """
        timeout = timeout_seconds or 600
        interval = poll_interval or 5

        start = time.time()
        poll_count = 0

        logger.info(
            f"[Runway] Polling job {job_id} (timeout={timeout}s, interval={interval}s)"
        )

        while time.time() - start < timeout:
            poll_count += 1
            result = await self.check_status(job_id)

            if result.is_complete():
                logger.info(f"[Runway] Job {job_id} completed after {poll_count} polls")
                return result

            if result.is_failed():
                logger.warning(
                    f"[Runway] Job {job_id} failed after {poll_count} polls: "
                    f"{result.error_message}"
                )
                return result

            elapsed = time.time() - start
            logger.info(
                f"[Runway] Job {job_id} still {result.status.value} "
                f"({elapsed:.1f}s elapsed, poll #{poll_count})"
            )

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                logger.warning(f"[Runway] Job {job_id} polling cancelled during sleep")
                raise

        elapsed = time.time() - start
        logger.error(
            f"[Runway] Job {job_id} timed out after {elapsed:.1f}s ({poll_count} polls)"
        )
        raise GenerationTimeoutError(
            f"Video generation timed out after {timeout} seconds"
        )

    def calculate_cost(self, model: str, duration_seconds: float) -> Decimal:
        """
        Calculate the cost for video generation using database pricing.

        Args:
            model: Model ID
            duration_seconds: Video duration

        Returns:
            Cost in USD as Decimal
        """
        # Use base class implementation which looks up from database
        return super().calculate_cost(model, duration_seconds)
