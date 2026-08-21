"""
Base classes and dataclasses for video generation providers.

This module defines the abstract interface that all video providers must implement,
as well as common data structures for video generation inputs and results.

Supports multiple input types:
- Text-to-video (text prompt only)
- Image-to-video (image input)
- Video-to-video (video input for transformation/upscaling)
- Image+Audio (character animation)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional, List


# =============================================================================
# Exceptions
# =============================================================================


class VideoProviderError(Exception):
    """Base exception for video provider errors."""

    def __init__(self, message: str, error_type: str = "provider_error"):
        super().__init__(message)
        self.error_type = error_type


class RateLimitError(VideoProviderError):
    """Raised when the provider rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, "rate_limit")


class QuotaExhaustedError(VideoProviderError):
    """Raised when the user's quota is exhausted."""

    def __init__(self, message: str = "Quota exhausted"):
        super().__init__(message, "quota_exhausted")


class GenerationTimeoutError(VideoProviderError):
    """Raised when video generation times out."""

    def __init__(self, message: str = "Generation timed out"):
        super().__init__(message, "timeout")


class InvalidPromptError(VideoProviderError):
    """Raised when the prompt is invalid or rejected."""

    def __init__(self, message: str = "Invalid prompt"):
        super().__init__(message, "invalid_prompt")


class ContentPolicyError(VideoProviderError):
    """Raised when content violates provider policies."""

    def __init__(self, message: str = "Content policy violation"):
        super().__init__(message, "content_policy")


class InvalidInputError(VideoProviderError):
    """Raised when input doesn't match required type for the model."""

    def __init__(self, message: str = "Invalid input for model"):
        super().__init__(message, "invalid_input")


# =============================================================================
# Enums
# =============================================================================


class VideoStatus(Enum):
    """Status of a video generation job."""

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class VideoInputType(Enum):
    """Types of input a video model can accept."""

    TEXT = "text"  # Text prompt only
    IMAGE = "image"  # Image required (image-to-video)
    VIDEO = "video"  # Video required (upscaling, transformation)
    IMAGE_VIDEO = "image_video"  # Either image or video
    TEXT_IMAGE = "text_image"  # Text + optional image
    IMAGE_AUDIO = "image_audio"  # Image + audio (character animation)


# =============================================================================
# Input Dataclass
# =============================================================================


@dataclass
class VideoGenerationInput:
    """
    Unified input structure for all video generation types.

    Follows Interface Segregation - only populate fields needed for the operation.

    Examples:
        # Text-to-video
        input = VideoGenerationInput(prompt="A sunset over the ocean")

        # Image-to-video
        input = VideoGenerationInput(
            image_url="https://...",
            prompt="Animate this image with gentle motion"
        )

        # Video upscaling
        input = VideoGenerationInput(video_url="https://...")

        # Character animation (Act Two)
        input = VideoGenerationInput(
            image_url="https://...",
            audio_url="https://..."
        )
    """

    # Text input (for text-to-video, guidance for image-to-video)
    prompt: Optional[str] = None

    # Image input (for image-to-video, character animation)
    image_url: Optional[str] = None
    image_bytes: Optional[bytes] = None

    # Video input (for video-to-video, upscaling)
    video_url: Optional[str] = None
    video_bytes: Optional[bytes] = None

    # Audio input (for character animation)
    audio_url: Optional[str] = None
    audio_bytes: Optional[bytes] = None

    # Common parameters
    duration: Optional[int] = None
    resolution: Optional[str] = None
    aspect_ratio: Optional[str] = None
    fps: int = 24

    # Model-specific options
    generate_audio: bool = False
    style: Optional[str] = None
    seed: Optional[int] = None

    def validate_for_input_type(self, input_type: VideoInputType) -> None:
        """
        Validate that required inputs are present for the operation type.

        Args:
            input_type: The VideoInputType enum value

        Raises:
            InvalidInputError: If required inputs are missing
        """
        if input_type == VideoInputType.TEXT:
            if not self.prompt:
                raise InvalidInputError("Text prompt is required for text-to-video generation")

        elif input_type == VideoInputType.IMAGE:
            if not (self.image_url or self.image_bytes):
                raise InvalidInputError("Image is required for image-to-video generation")

        elif input_type == VideoInputType.VIDEO:
            if not (self.video_url or self.video_bytes):
                raise InvalidInputError("Video is required for video processing/upscaling")

        elif input_type == VideoInputType.IMAGE_VIDEO:
            has_image = self.image_url or self.image_bytes
            has_video = self.video_url or self.video_bytes
            if not (has_image or has_video):
                raise InvalidInputError("Either image or video is required for this model")

        elif input_type == VideoInputType.TEXT_IMAGE:
            if not self.prompt:
                raise InvalidInputError("Text prompt is required (image is optional)")

        elif input_type == VideoInputType.IMAGE_AUDIO:
            if not (self.image_url or self.image_bytes):
                raise InvalidInputError("Image is required for character animation")
            if not (self.audio_url or self.audio_bytes):
                raise InvalidInputError("Audio is required for character animation")

    def has_image(self) -> bool:
        """Check if image input is provided."""
        return bool(self.image_url or self.image_bytes)

    def has_video(self) -> bool:
        """Check if video input is provided."""
        return bool(self.video_url or self.video_bytes)

    def has_audio(self) -> bool:
        """Check if audio input is provided."""
        return bool(self.audio_url or self.audio_bytes)


# =============================================================================
# Result Dataclass
# =============================================================================


@dataclass
class VideoGenerationResult:
    """Result of a video generation request."""

    status: VideoStatus
    video_bytes: Optional[bytes] = None
    mime_type: str = "video/mp4"
    width: int = 0
    height: int = 0
    duration_seconds: float = 0.0
    fps: int = 24
    file_size_bytes: int = 0
    cost_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    generation_time_ms: int = 0
    provider: str = ""
    model: str = ""
    job_id: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    # Output URL (for providers that return a URL instead of bytes)
    output_url: Optional[str] = None

    def is_complete(self) -> bool:
        """Check if the video generation is complete."""
        return self.status == VideoStatus.COMPLETED

    def is_failed(self) -> bool:
        """Check if the video generation failed."""
        return self.status == VideoStatus.FAILED

    def is_pending(self) -> bool:
        """Check if the video generation is still pending."""
        return self.status in (VideoStatus.QUEUED, VideoStatus.IN_PROGRESS)


# =============================================================================
# Base Provider Class
# =============================================================================


class BaseVideoProvider(ABC):
    """
    Abstract base class for video generation providers.

    All video providers must implement this interface to ensure
    consistent behavior across different providers (OpenAI, Runway, etc.).

    The interface supports multiple input types through the VideoGenerationInput
    dataclass, allowing providers to handle text-to-video, image-to-video,
    video upscaling, and character animation.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'openai', 'runway')."""
        pass

    @property
    @abstractmethod
    def supported_input_types(self) -> List[VideoInputType]:
        """Return list of input types this provider supports."""
        pass

    @abstractmethod
    async def generate(
        self,
        model_id: str,
        input_data: VideoGenerationInput,
    ) -> VideoGenerationResult:
        """
        Start a video generation job.

        Args:
            model_id: The model identifier (e.g., 'veo3.1_fast', 'gen4_turbo')
            input_data: Unified input structure with all necessary data

        Returns:
            VideoGenerationResult with job_id and initial status

        Raises:
            InvalidInputError: If input doesn't match model requirements
            VideoProviderError: If generation fails to start
        """
        pass

    @abstractmethod
    async def check_status(self, job_id: str) -> VideoGenerationResult:
        """
        Check the status of a video generation job.

        Args:
            job_id: The job ID returned from generate()

        Returns:
            VideoGenerationResult with current status and metadata
        """
        pass

    @abstractmethod
    async def download(self, job_id: str) -> bytes:
        """
        Download the completed video.

        Args:
            job_id: The job ID of a completed generation

        Returns:
            Video content as bytes

        Raises:
            VideoProviderError: If the job is not completed or download fails
        """
        pass

    async def poll_until_complete(
        self,
        job_id: str,
        timeout_seconds: Optional[int] = None,
        poll_interval: Optional[int] = None,
    ) -> VideoGenerationResult:
        """
        Poll until video generation completes or times out.

        This is a convenience method that repeatedly checks status
        until the job is complete, failed, or times out.

        Args:
            job_id: The job ID to poll
            timeout_seconds: Maximum time to wait (default: 600 seconds)
            poll_interval: Time between polls (default: 5 seconds)

        Returns:
            VideoGenerationResult with final status

        Raises:
            GenerationTimeoutError: If the job times out
        """
        import asyncio
        import time

        # Default timeouts
        timeout = timeout_seconds or 600  # 10 minutes
        interval = poll_interval or 5  # 5 seconds

        start = time.time()

        while time.time() - start < timeout:
            result = await self.check_status(job_id)

            if result.is_complete() or result.is_failed():
                return result

            await asyncio.sleep(interval)

        raise GenerationTimeoutError(
            f"Video generation timed out after {timeout} seconds"
        )

    async def close(self) -> None:
        """
        Cleanup provider resources (HTTP clients, etc.).

        Subclasses should override this if they have resources to cleanup.
        """
        pass

    # =========================================================================
    # Legacy interface support (for backward compatibility)
    # =========================================================================

    async def generate_legacy(
        self,
        prompt: str,
        duration: int,
        resolution: str,
        model: str,
        style: Optional[str] = None,
        fps: int = 24,
    ) -> VideoGenerationResult:
        """
        Legacy generate method for backward compatibility.

        Converts old-style parameters to new VideoGenerationInput.

        DEPRECATED: Use generate() with VideoGenerationInput instead.
        """
        input_data = VideoGenerationInput(
            prompt=prompt,
            duration=duration,
            resolution=resolution,
            fps=fps,
            style=style,
        )
        return await self.generate(model, input_data)

    def calculate_cost(self, model: str, duration_seconds: float) -> Decimal:
        """
        Calculate the cost for video generation using database pricing.

        Args:
            model: Model ID (short or canonical)
            duration_seconds: Video duration

        Returns:
            Cost in USD as Decimal
        """
        from llm.models import VideoModelCatalog

        # Try to get model from database
        model_config = VideoModelCatalog.get_by_model_id(model)
        if not model_config:
            # Try canonical ID
            model_config = VideoModelCatalog.get_by_canonical_id(model)

        if model_config:
            return model_config.calculate_cost(duration_seconds=duration_seconds)

        # Fallback: return zero (caller should handle)
        return Decimal("0")
