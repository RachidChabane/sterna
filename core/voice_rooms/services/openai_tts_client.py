"""OpenAI Text-to-Speech streaming client for real-time voice synthesis.

Uses OpenAI's TTS API with HTTP streaming for low-latency audio generation.
Compatible with the same interface as ElevenLabsTTSClient for easy swapping.
"""

import asyncio
import base64
import logging
from typing import Callable, Dict, Optional, Awaitable, TYPE_CHECKING

import httpx
from django.conf import settings

if TYPE_CHECKING:
    from authentication.models import User

from voice_rooms.constants import (
    TTS_HTTP_TIMEOUT_SEC,
    TTS_AUDIO_SILENCE_TIMEOUT_SEC,
)

logger = logging.getLogger(__name__)


class OpenAITTSClient:
    """
    Real-time text-to-speech using OpenAI's streaming TTS API.

    Features:
    - HTTP streaming for low latency
    - Multiple concurrent voice connections (simulated via sequential requests)
    - Compatible interface with ElevenLabsTTSClient
    - Supports all OpenAI voices: alloy, echo, fable, onyx, nova, shimmer
    """

    OPENAI_TTS_URL = "https://api.openai.com/v1/audio/speech"

    # OpenAI voice IDs
    VALID_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]

    # OpenAI TTS models
    VALID_MODELS = ["tts-1", "tts-1-hd"]

    def __init__(
        self,
        on_audio: Optional[Callable[[str, str, int], Awaitable[None]]] = None,
        on_error: Optional[Callable[[str, str], Awaitable[None]]] = None,
        on_audio_complete: Optional[Callable[[str], Awaitable[None]]] = None,
        on_alignment: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        user: Optional['User'] = None,
        session_id: Optional[str] = None,
    ):
        """
        Initialize the OpenAI TTS client.

        Args:
            on_audio: Callback for audio chunks (voice_id, base64_audio, sequence)
            on_error: Callback for errors (voice_id, error_message)
            on_audio_complete: Callback when audio generation is complete (voice_id)
            on_alignment: Callback for word timing alignment (voice_id, alignment_data)
                          Note: OpenAI doesn't provide native timing, so we estimate it
            user: User for quota tracking (optional)
            session_id: Session ID for quota tracking (optional)
        """
        self.api_key = getattr(settings, 'OPENAI_API_KEY', None)
        self.on_audio = on_audio
        self.on_error = on_error
        self.on_audio_complete = on_audio_complete
        self.on_alignment = on_alignment
        self._user = user
        self._session_id = session_id

        self._http_client: Optional[httpx.AsyncClient] = None
        self._voices: Dict[str, dict] = {}  # Connected voices with settings
        self._text_buffers: Dict[str, str] = {}  # Buffered text per voice
        self._generation_tasks: Dict[str, asyncio.Task] = {}  # Running TTS tasks
        self._completion_events: Dict[str, asyncio.Event] = {}
        self._muted: Dict[str, bool] = {}
        self._sequence: Dict[str, int] = {}
        self._total_chars: Dict[str, int] = {}  # Track chars per voice for quota

    def _deduct_tts_usage(self, character_count: int, model_id: str = "") -> None:
        """Deduct TTS usage from quota system."""
        if not self._user:
            return

        try:
            from usage_quota.billing.service import get_billing_service
            from usage_quota.billing.operations import BillableOperation
            from usage_quota.services import get_cost_calculator
            from usage_quota.models import ServiceType, FeatureType

            cost_calculator = get_cost_calculator()

            # Calculate cost
            cost_usd = cost_calculator.calculate_openai_tts_cost(
                character_count=character_count,
                model_id=model_id,
            )

            op = BillableOperation(
                service=ServiceType.OPENAI_TTS,
                feature=FeatureType.VOICE_ROOM,
                model_id=model_id,
                character_count=character_count,
                cost_usd=cost_usd,
                session_id=self._session_id or '',
            )
            # OpenAI TTS is always platform-billed; route through BillingService
            # so the guard catches accidental BYOK calls.
            get_billing_service().record_usage(
                self._user, op, billing_origin='platform',
            )

            logger.info(f"OpenAI TTS usage recorded: {character_count} chars, ${cost_usd:.6f}")

        except Exception as e:
            logger.error(f"Failed to deduct OpenAI TTS usage: {e}")
            # Queue for retry to ensure usage is eventually recorded
            try:
                from usage_quota.tasks import queue_failed_deduction
                from usage_quota.services import get_cost_calculator
                from usage_quota.models import ServiceType, FeatureType

                cost_calculator = get_cost_calculator()
                cost_usd = cost_calculator.calculate_openai_tts_cost(
                    character_count=character_count,
                    model_id=model_id,
                )

                queue_failed_deduction(
                    user_id=str(self._user.id),
                    service=ServiceType.OPENAI_TTS,
                    cost_usd=str(cost_usd),
                    feature=FeatureType.VOICE_ROOM,
                    session_id=self._session_id or '',
                    model_id=model_id,
                    character_count=character_count,
                )
            except Exception as queue_error:
                logger.error(f"Failed to queue OpenAI TTS usage for retry: {queue_error}")

    async def _check_tts_quota(self, estimated_chars: int = 1000, model_id: str = "") -> bool:
        """
        Pre-check quota before TTS operations.

        Args:
            estimated_chars: Estimated character count for the operation
            model_id: TTS model ID for cost calculation

        Returns:
            True if quota is available, False otherwise

        Raises:
            QuotaExceededException if quota is exceeded
        """
        if not self._user:
            return True

        try:
            from usage_quota.services import get_quota_service, get_cost_calculator
            from usage_quota.models import ServiceType, FeatureType
            from usage_quota.exceptions import QuotaExceededException

            quota_service = get_quota_service()
            cost_calculator = get_cost_calculator()

            # Estimate cost
            estimated_cost = cost_calculator.calculate_openai_tts_cost(
                character_count=estimated_chars,
                model_id=model_id,
            )

            # Check quota (async) — feature_name routes through tier
            # cascading guard (flag + per-feature count + USD).
            check_result = await quota_service.acheck_quota(
                user=self._user,
                service=ServiceType.OPENAI_TTS,
                estimated_cost_usd=estimated_cost,
                feature=FeatureType.VOICE_ROOM,
                session_id=self._session_id,
                feature_name='voice_tts',
            )

            if not check_result.allowed:
                logger.warning(f"OpenAI TTS quota exceeded for user {self._user.id}: {check_result.reason}")
                from usage_quota.messages import format_quota_error_message

                limit_type = check_result.reason or "weekly"
                window_end = (
                    check_result.session_window_end if limit_type == "session"
                    else check_result.weekly_window_end
                )
                raise QuotaExceededException(
                    message=format_quota_error_message(limit_type, window_end),
                    limit_usd=check_result.weekly_limit_usd,
                    used_usd=check_result.weekly_used_usd,
                    remaining_usd=check_result.remaining_weekly_usd,
                )

            return True

        except Exception as e:
            # Re-raise quota exceptions
            from usage_quota.exceptions import QuotaExceededException
            if isinstance(e, QuotaExceededException):
                raise
            # Log but don't block on other errors
            logger.error(f"Failed to check OpenAI TTS quota: {e}")
            return True

    async def initialize(self) -> None:
        """Initialize HTTP client for API calls."""
        self._http_client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(TTS_HTTP_TIMEOUT_SEC, connect=10.0),
        )
        logger.info("OpenAI TTS client initialized")

    async def cleanup(self) -> None:
        """Cleanup all connections and pending tasks."""
        # Cancel all running generation tasks
        for voice_id, task in list(self._generation_tasks.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._generation_tasks.clear()
        self._voices.clear()
        self._text_buffers.clear()
        self._completion_events.clear()
        self._muted.clear()
        self._sequence.clear()

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        logger.info("OpenAI TTS client cleaned up")

    async def connect_voice(
        self,
        voice_id: str,
        voice_settings: Optional[object] = None,  # VoiceSettings from elevenlabs_tts
        model: Optional[str] = None,
    ) -> bool:
        """
        Register a voice for TTS generation.

        OpenAI doesn't use persistent connections like ElevenLabs WebSocket,
        but we maintain compatibility by tracking voice configurations.

        Args:
            voice_id: OpenAI voice ID (alloy, echo, fable, onyx, nova, shimmer)
            voice_settings: Voice settings (speed is the only OpenAI-supported setting)
            model: TTS model to use (tts-1 or tts-1-hd)

        Returns:
            True if voice is valid and registered
        """
        if not self.api_key:
            logger.error("OpenAI API key not configured")
            if self.on_error:
                await self.on_error(voice_id, "OpenAI API key not configured")
            return False

        # Validate voice
        if voice_id not in self.VALID_VOICES:
            logger.error(f"Invalid OpenAI voice: {voice_id}. Valid: {self.VALID_VOICES}")
            if self.on_error:
                await self.on_error(voice_id, f"Invalid voice: {voice_id}")
            return False

        # Validate and default model
        model = model or "tts-1"
        if model not in self.VALID_MODELS:
            logger.warning(f"Invalid OpenAI TTS model: {model}, using tts-1")
            model = "tts-1"

        # Extract speed from voice_settings if provided
        speed = 1.0
        if voice_settings and hasattr(voice_settings, 'speed'):
            speed = voice_settings.speed
        elif voice_settings and isinstance(voice_settings, dict):
            speed = voice_settings.get('speed', 1.0)

        # Clamp speed to OpenAI's valid range
        speed = max(0.25, min(4.0, speed))

        # Pre-check quota before registering voice (estimate ~2000 chars for a typical session)
        try:
            await self._check_tts_quota(estimated_chars=2000, model_id=model)
        except Exception as e:
            logger.error(f"Quota pre-check failed for voice {voice_id}: {e}")
            if self.on_error:
                error_msg = str(e) if hasattr(e, 'message') else "Quota exceeded"
                await self.on_error(voice_id, error_msg)
            return False

        self._voices[voice_id] = {
            "model": model,
            "speed": speed,
        }
        self._text_buffers[voice_id] = ""
        self._sequence[voice_id] = 0
        self._muted[voice_id] = False

        logger.info(f"Connecting to OpenAI TTS for voice {voice_id}...")
        logger.info(f"OpenAI TTS voice registered: {voice_id} (model={model}, speed={speed})")
        return True

    async def disconnect_voice(self, voice_id: str) -> None:
        """Disconnect/unregister a voice."""
        # Cancel any running task for this voice
        if voice_id in self._generation_tasks:
            task = self._generation_tasks[voice_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self._generation_tasks[voice_id]

        self._voices.pop(voice_id, None)
        self._text_buffers.pop(voice_id, None)
        self._sequence.pop(voice_id, None)
        self._muted.pop(voice_id, None)
        self._completion_events.pop(voice_id, None)

        logger.info(f"OpenAI TTS voice disconnected: {voice_id}")

    async def send_text(self, voice_id: str, text: str) -> None:
        """
        Buffer text to be synthesized.

        Unlike ElevenLabs which streams text in, OpenAI TTS needs complete
        sentences for best results. We buffer text and generate on flush.

        Args:
            voice_id: Voice to use
            text: Text chunk to synthesize
        """
        if voice_id not in self._voices:
            logger.warning(f"Voice {voice_id} not connected")
            return

        # Clear muted flag when sending new text
        if self._muted.get(voice_id):
            self._muted[voice_id] = False
            logger.info(f"TTS unmuted for voice {voice_id}")

        # Buffer the text
        self._text_buffers[voice_id] = self._text_buffers.get(voice_id, "") + text
        logger.debug(f"TTS buffered {len(text)} chars for voice {voice_id}")

    async def flush(self, voice_id: str) -> None:
        """
        Flush the text buffer and generate audio.

        This triggers the actual TTS API call with all buffered text.
        """
        if voice_id not in self._voices:
            return

        text = self._text_buffers.get(voice_id, "").strip()
        if not text:
            # Nothing to generate
            if self.on_audio_complete:
                await self.on_audio_complete(voice_id)
            return

        # Clear the buffer
        self._text_buffers[voice_id] = ""

        # Create completion event
        self._completion_events[voice_id] = asyncio.Event()

        # Start generation in background
        task = asyncio.create_task(self._generate_audio(voice_id, text))
        self._generation_tasks[voice_id] = task

    def _estimate_alignment(self, text: str, audio_bytes: int, speed: float = 1.0) -> dict:
        """
        Estimate character-level alignment for live transcript.

        Uses MP3 file size to estimate duration, then distributes timing
        across characters. Accounts for pauses after punctuation.
        Format matches ElevenLabs for compatibility.

        Args:
            text: The text being synthesized
            audio_bytes: Size of MP3 audio in bytes
            speed: TTS speed multiplier (0.25 to 4.0)

        Returns:
            Alignment data with chars, charStartTimesMs, charDurationsMs, estimated flag
        """
        # Estimate duration from MP3 size
        # OpenAI TTS uses variable bitrate, ~165kbps average for speech
        OPENAI_MP3_BITRATE = 165000
        audio_duration_ms = (audio_bytes * 8 * 1000) / OPENAI_MP3_BITRATE

        # No speed adjustment - bitrate tuned for accuracy
        # audio_duration_ms *= 1.0

        chars = list(text)
        if not chars:
            return {
                "chars": [],
                "charStartTimesMs": [],
                "charDurationsMs": [],
                "estimated": True,
            }

        # Calculate weight for each character (punctuation gets extra time for pause)
        def get_char_weight(char: str) -> float:
            if char in '.!?':
                return 15.0  # Long pause for sentence end
            elif char == ';':
                return 10.0  # Longer pause for semicolon
            elif char in ',:':
                return 6.0  # Medium pause for clause break
            elif char in '-—':
                return 5.0  # Pause for dashes
            else:
                return 1.0  # Regular characters including spaces

        char_weights = [get_char_weight(c) for c in chars]
        total_weight = sum(char_weights)
        if total_weight == 0:
            total_weight = len(chars)

        char_start_times = []
        char_durations = []
        current_time = 0

        for weight in char_weights:
            duration = (weight / total_weight) * audio_duration_ms
            char_start_times.append(int(current_time))
            char_durations.append(int(duration))
            current_time += duration

        return {
            "chars": chars,
            "charStartTimesMs": char_start_times,
            "charDurationsMs": char_durations,
            "estimated": True,  # Flag for frontend to skip word highlighting
        }

    async def _generate_audio(self, voice_id: str, text: str) -> None:
        """Generate audio from text using OpenAI TTS API with streaming."""
        if voice_id not in self._voices:
            return

        voice_config = self._voices[voice_id]
        model = voice_config["model"]
        speed = voice_config["speed"]

        logger.info(f"OpenAI TTS: Generating speech for voice {voice_id} ({len(text)} chars)")

        # Pre-check quota before making API call
        try:
            await self._check_tts_quota(estimated_chars=len(text), model_id=model)
        except Exception as e:
            logger.error(f"Quota pre-check failed for OpenAI TTS: {e}")
            if self.on_error:
                await self.on_error(voice_id, str(e))
            return

        try:
            # First generate audio to get actual duration for timing estimation
            response = await self._http_client.post(
                self.OPENAI_TTS_URL,
                json={
                    "model": model,
                    "input": text[:4096],  # OpenAI limit
                    "voice": voice_id,
                    "speed": speed,
                    "response_format": "mp3",  # MP3 for browser compatibility
                },
            )

            if response.status_code != 200:
                logger.error(f"OpenAI TTS error: {response.status_code} - {response.text}")
                if self.on_error:
                    await self.on_error(voice_id, f"API error: {response.status_code}")
                return

            if self._muted.get(voice_id):
                logger.debug(f"TTS muted, discarding audio for {voice_id}")
                return

            # Send complete MP3 as a single chunk (browser can decode complete MP3)
            audio_data = response.content
            if audio_data:
                # Send estimated alignment BEFORE audio for line-based transitions
                # (no word-by-word highlighting, but enables slide animation)
                if self.on_alignment:
                    alignment_data = self._estimate_alignment(text, len(audio_data), speed)
                    await self.on_alignment(voice_id, alignment_data)
                    logger.debug(f"OpenAI TTS: Sent estimated alignment for {len(text)} chars (speed={speed})")

                if self.on_audio:
                    audio_b64 = base64.b64encode(audio_data).decode("utf-8")
                    self._sequence[voice_id] = 0
                    await self.on_audio(voice_id, audio_b64, 0)
                    logger.info(f"OpenAI TTS: Generated {len(audio_data)} bytes of MP3 audio for voice {voice_id}")

                # Deduct usage from quota system after successful generation
                character_count = len(text[:4096])  # OpenAI limit
                self._deduct_tts_usage(character_count, model)

        except asyncio.CancelledError:
            logger.info(f"TTS generation cancelled for voice {voice_id}")
            raise
        except Exception as e:
            logger.error(f"OpenAI TTS generation error for {voice_id}: {e}")
            if self.on_error:
                await self.on_error(voice_id, str(e))
        finally:
            # Signal completion
            if voice_id in self._completion_events:
                self._completion_events[voice_id].set()
            if self.on_audio_complete:
                await self.on_audio_complete(voice_id)

    async def generate_audio_direct(self, voice_id: str, text: str) -> Optional[str]:
        """
        Generate audio directly and return base64-encoded MP3.

        This bypasses callbacks and returns the audio data directly.
        Used for pipelined/pre-generation where we buffer audio for later playback.

        Args:
            voice_id: OpenAI voice ID
            text: Text to synthesize

        Returns:
            Base64-encoded MP3 audio, or None on error
        """
        if voice_id not in self._voices:
            logger.warning(f"Voice {voice_id} not connected for direct generation")
            return None

        voice_config = self._voices[voice_id]
        model = voice_config["model"]
        speed = voice_config["speed"]

        logger.info(f"OpenAI TTS direct: Generating speech for voice {voice_id} ({len(text)} chars)")

        # Pre-check quota before making API call
        try:
            await self._check_tts_quota(estimated_chars=len(text), model_id=model)
        except Exception as e:
            logger.error(f"Quota pre-check failed for OpenAI TTS direct: {e}")
            return None

        try:
            response = await self._http_client.post(
                self.OPENAI_TTS_URL,
                json={
                    "model": model,
                    "input": text[:4096],  # OpenAI limit
                    "voice": voice_id,
                    "speed": speed,
                    "response_format": "mp3",
                },
            )

            if response.status_code != 200:
                logger.error(f"OpenAI TTS direct error: {response.status_code} - {response.text}")
                return None

            logger.info("OpenAI TTS direct: Response status OK, reading content...")
            # Explicitly read the full response content (required for httpx async)
            audio_data = await response.aread()
            logger.info(f"OpenAI TTS direct: Content read, size = {len(audio_data) if audio_data else 0} bytes")

            if audio_data:
                logger.info("OpenAI TTS direct: Encoding to base64...")
                audio_b64 = base64.b64encode(audio_data).decode("utf-8")
                logger.info(f"OpenAI TTS direct: Generated {len(audio_data)} bytes ({len(audio_b64)} b64 chars) for voice {voice_id}")

                # Deduct usage from quota system after successful generation
                character_count = len(text[:4096])  # OpenAI limit
                self._deduct_tts_usage(character_count, model)

                return audio_b64

            logger.warning(f"OpenAI TTS direct: No audio data received for voice {voice_id}")
            return None

        except Exception as e:
            logger.error(f"OpenAI TTS direct generation error for {voice_id}: {e}")
            return None

    async def stop_generation(self, voice_id: str) -> None:
        """
        Stop audio generation for a voice (used during user interruption).

        Mutes the voice so any pending audio is discarded.
        """
        self._muted[voice_id] = True
        self._sequence[voice_id] = 0

        # Cancel running task
        if voice_id in self._generation_tasks:
            task = self._generation_tasks[voice_id]
            if not task.done():
                task.cancel()

        # Clear completion event
        if voice_id in self._completion_events:
            self._completion_events[voice_id].set()

        logger.info(f"TTS generation stopped for voice {voice_id}")

    async def wait_for_completion(
        self,
        voice_id: str,
        timeout: float = 120.0,
        audio_silence_timeout: float = TTS_AUDIO_SILENCE_TIMEOUT_SEC,
    ) -> bool:
        """
        Wait for audio generation to complete.

        Args:
            voice_id: Voice ID to wait for
            timeout: Maximum time to wait in seconds
            audio_silence_timeout: Not used for OpenAI (kept for API compatibility)

        Returns:
            True if completed, False if timed out
        """
        if voice_id not in self._completion_events:
            return True

        try:
            await asyncio.wait_for(
                self._completion_events[voice_id].wait(),
                timeout=timeout
            )
            return True
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for audio completion for voice {voice_id}")
            return False
        finally:
            self._completion_events.pop(voice_id, None)

    def is_voice_connected(self, voice_id: str) -> bool:
        """Check if a voice is registered."""
        return voice_id in self._voices

    def get_connected_voices(self) -> list:
        """Get list of registered voice IDs."""
        return list(self._voices.keys())
