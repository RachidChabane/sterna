"""ElevenLabs Text-to-Speech client for real-time voice synthesis."""

import asyncio
import base64
import json
import logging
import re
from typing import Callable, Dict, List, Optional, Awaitable, TYPE_CHECKING

import httpx
import websockets
from django.conf import settings

if TYPE_CHECKING:
    from authentication.models import User

from voice_rooms.constants import (
    TTS_HTTP_TIMEOUT_SEC,
    TTS_WEBSOCKET_PING_INTERVAL_SEC,
    TTS_WEBSOCKET_PING_TIMEOUT_SEC,
    TTS_KEEPALIVE_INTERVAL_SEC,
    TTS_AUDIO_SILENCE_TIMEOUT_SEC,
)
from .tts_base import TTSProvider, TTSVoice, TTSModel, TTSSettings

logger = logging.getLogger(__name__)


def strip_bracketed_text(text: str, model_id: Optional[str] = None) -> str:
    """
    Remove bracketed annotations from text before TTS.

    These are stage directions or annotations like [laughs], [sighs], [pauses].
    - Eleven v3 supports these as "Audio Tags" for emotional control
    - Older models (v2.5 Flash/Turbo) read them aloud literally

    Args:
        text: Input text potentially containing [bracketed] annotations
        model_id: TTS model being used (v3 models keep brackets)

    Returns:
        Text with bracketed annotations removed (unless using v3)
    """
    # Eleven v3 supports audio tags - don't strip brackets
    if model_id and 'v3' in model_id.lower():
        return text

    # For older models, remove [text] patterns
    cleaned = re.sub(r'\s*\[[^\]]*\]\s*', ' ', text)
    # Clean up any double spaces that may have been created
    cleaned = re.sub(r'  +', ' ', cleaned)
    return cleaned.strip()


class VoiceSettings:
    """Voice settings for TTS."""

    def __init__(
        self,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        use_speaker_boost: bool = True,
    ):
        self.stability = stability
        self.similarity_boost = similarity_boost
        self.style = style
        self.use_speaker_boost = use_speaker_boost


class VoiceInfo:
    """Information about an available voice."""

    def __init__(
        self,
        voice_id: str,
        name: str,
        category: str = "premade",
        description: Optional[str] = None,
        preview_url: Optional[str] = None,
        labels: Optional[Dict] = None,
        high_quality_base_model_ids: Optional[List[str]] = None,
        verified_languages: Optional[List[Dict]] = None,
    ):
        self.voice_id = voice_id
        self.name = name
        self.category = category
        self.description = description
        self.preview_url = preview_url
        self.labels = labels or {}
        self.high_quality_base_model_ids = high_quality_base_model_ids or []
        self.verified_languages = verified_languages or []


class ElevenLabsTTSClient:
    """
    Real-time text-to-speech using ElevenLabs' streaming API.

    Features:
    - WebSocket streaming for low latency
    - Multiple concurrent voice connections
    - Text chunking for streaming LLM responses
    - Audio completion tracking for turn management
    """

    ELEVENLABS_WS_URL = "wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input"
    ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"

    def __init__(
        self,
        on_audio: Optional[Callable[[str, str, int], Awaitable[None]]] = None,
        on_error: Optional[Callable[[str, str], Awaitable[None]]] = None,
        on_audio_complete: Optional[Callable[[str], Awaitable[None]]] = None,
        on_alignment: Optional[Callable[[str, dict], Awaitable[None]]] = None,
        user: Optional['User'] = None,
        session_id: Optional[str] = None,
        feature=None,
    ):
        """
        Initialize the ElevenLabs TTS client.

        Args:
            on_audio: Callback for audio chunks (voice_id, base64_audio, sequence)
            on_error: Callback for errors (voice_id, error_message)
            on_audio_complete: Callback when audio generation is complete (voice_id)
            on_alignment: Callback for word timing alignment (voice_id, alignment_data)
            user: User for quota tracking (optional)
            session_id: Session ID for quota tracking (optional)
            feature: Optional FeatureType override for the billing row's
                feature column (default VOICE_ROOM). Preview flow passes
                FeatureType.CHAT.
        """
        from usage_quota.models import FeatureType as _FT
        self.api_key = settings.ELEVENLABS_API_KEY
        self.on_audio = on_audio
        self.on_error = on_error
        self.on_audio_complete = on_audio_complete
        self.on_alignment = on_alignment
        self._user = user
        self._session_id = session_id
        self._feature = feature if feature is not None else _FT.VOICE_ROOM

        self._connections: Dict[str, dict] = {}
        self._http_client: Optional[httpx.AsyncClient] = None
        self._completion_events: Dict[str, asyncio.Event] = {}
        self._last_audio_time: Dict[str, float] = {}  # Track when we last received audio
        self._muted: Dict[str, bool] = {}  # Track muted voices (audio discarded during interruption)

    def _deduct_tts_usage(self, character_count: int, model_id: str = "") -> None:
        """Deduct TTS usage from quota system using centralized BillingService."""
        if not self._user:
            return

        try:
            from usage_quota.billing import get_billing_service, BillableOperation
            from usage_quota.models import ServiceType

            # Create billable operation
            operation = BillableOperation(
                service=ServiceType.ELEVENLABS_TTS,
                feature=self._feature,
                model_id=model_id,
                character_count=character_count,
                session_id=self._session_id or '',
            )

            # Record via centralized billing service. ElevenLabs is always
            # platform-billed (not OpenRouter-backed); the BillingService
            # guard rejects 'byok' for ELEVENLABS_TTS but we set
            # 'platform' explicitly here for clarity.
            billing = get_billing_service()
            billing.record_usage(self._user, operation, billing_origin='platform')

            logger.info(f"TTS usage recorded: {character_count} chars")

        except Exception as e:
            logger.error(f"Failed to record TTS usage: {e}")

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
            from usage_quota.models import ServiceType
            from usage_quota.exceptions import QuotaExceededException

            quota_service = get_quota_service()
            cost_calculator = get_cost_calculator()

            # Estimate cost
            estimated_cost = cost_calculator.calculate_elevenlabs_cost(
                character_count=estimated_chars,
                model_id=model_id,
            )

            # Check quota (async) — feature_name routes through tier
            # cascading guard (flag + per-feature count + USD).
            check_result = await quota_service.acheck_quota(
                user=self._user,
                service=ServiceType.ELEVENLABS_TTS,
                estimated_cost_usd=estimated_cost,
                feature=self._feature,
                session_id=self._session_id,
                feature_name='voice_tts',
            )

            if not check_result.allowed:
                logger.warning(f"TTS quota exceeded for user {self._user.id}: {check_result.reason}")
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
            logger.error(f"Failed to check TTS quota: {e}")
            return True

    async def initialize(self) -> None:
        """Initialize HTTP client for API calls."""
        self._http_client = httpx.AsyncClient(
            base_url=self.ELEVENLABS_API_URL,
            headers={"xi-api-key": self.api_key},
            timeout=TTS_HTTP_TIMEOUT_SEC,
        )

    async def cleanup(self) -> None:
        """Cleanup all connections."""
        voice_ids = list(self._connections.keys())
        for voice_id in voice_ids:
            await self.disconnect_voice(voice_id)

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def connect_voice(
        self,
        voice_id: str,
        voice_settings: Optional[VoiceSettings] = None,
        model: Optional[str] = None,
    ) -> bool:
        """
        Create a WebSocket connection for a specific voice.

        Args:
            voice_id: ElevenLabs voice ID
            voice_settings: Optional voice settings override
            model: TTS model to use (defaults to settings.ELEVENLABS_MODEL)

        Returns:
            True if connection successful
        """
        if voice_id in self._connections:
            logger.warning(f"Voice {voice_id} already connected")
            return True

        if not self.api_key:
            logger.error("ElevenLabs API key not configured")
            if self.on_error:
                await self.on_error(voice_id, "ElevenLabs API key not configured")
            return False

        # Pre-check quota before connecting (estimate ~2000 chars for a typical session)
        tts_model = model or settings.ELEVENLABS_MODEL
        try:
            await self._check_tts_quota(estimated_chars=2000, model_id=tts_model)
        except Exception as e:
            logger.error(f"Quota pre-check failed for voice {voice_id}: {e}")
            if self.on_error:
                error_msg = str(e) if hasattr(e, 'message') else "Quota exceeded"
                await self.on_error(voice_id, error_msg)
            return False

        try:
            # Use provided model or fall back to global setting
            tts_model = model or settings.ELEVENLABS_MODEL
            logger.info(f"Connecting voice {voice_id} with TTS model: {tts_model}")

            url = self.ELEVENLABS_WS_URL.format(voice_id=voice_id)
            params = {
                "model_id": tts_model,
                "optimize_streaming_latency": settings.ELEVENLABS_OPTIMIZE_LATENCY,
                # Use PCM format for smooth streaming (no MP3 frame boundary issues)
                # PCM is larger but eliminates micro cuts from MP3 decoding artifacts
                "output_format": "pcm_24000",
            }
            url += "?" + "&".join(f"{k}={v}" for k, v in params.items())

            logger.info(f"Connecting to ElevenLabs TTS for voice {voice_id}...")

            ws = await websockets.connect(
                url,
                additional_headers={"xi-api-key": self.api_key},
                ping_interval=TTS_WEBSOCKET_PING_INTERVAL_SEC,
                ping_timeout=TTS_WEBSOCKET_PING_TIMEOUT_SEC,
            )

            settings_to_use = voice_settings or VoiceSettings(
                stability=settings.ELEVENLABS_STABILITY,
                similarity_boost=settings.ELEVENLABS_SIMILARITY_BOOST,
                style=settings.ELEVENLABS_STYLE,
                use_speaker_boost=settings.ELEVENLABS_USE_SPEAKER_BOOST,
            )

            bos_message = {
                "text": " ",
                "voice_settings": {
                    "stability": settings_to_use.stability,
                    "similarity_boost": settings_to_use.similarity_boost,
                    "style": settings_to_use.style,
                    "use_speaker_boost": settings_to_use.use_speaker_boost,
                },
                "generation_config": {
                    # Larger chunks = fewer MP3 frame boundary issues = smoother playback
                    # Trade-off: slightly higher latency for first audio chunk
                    "chunk_length_schedule": [300, 400, 500, 500],
                },
                # Request word-level alignment for live transcript sync
                "alignment": True,
            }
            await ws.send(json.dumps(bos_message))

            self._connections[voice_id] = {
                "ws": ws,
                "sequence": 0,
                "receive_task": None,
                "keepalive_task": None,
                "closing": False,
                "model": tts_model,  # Track model for audio tag support detection
            }

            self._connections[voice_id]["receive_task"] = asyncio.create_task(
                self._receive_loop(voice_id)
            )
            self._connections[voice_id]["keepalive_task"] = asyncio.create_task(
                self._keepalive_loop(voice_id)
            )

            logger.info(f"Connected to ElevenLabs TTS for voice {voice_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect voice {voice_id}: {e}")
            if self.on_error:
                await self.on_error(voice_id, f"Connection failed: {str(e)}")
            return False

    async def disconnect_voice(self, voice_id: str) -> None:
        """Disconnect a specific voice."""
        if voice_id not in self._connections:
            return

        conn = self._connections[voice_id]
        conn["closing"] = True

        if conn.get("keepalive_task"):
            conn["keepalive_task"].cancel()
            try:
                await conn["keepalive_task"]
            except asyncio.CancelledError:
                pass

        if conn["receive_task"]:
            conn["receive_task"].cancel()
            try:
                await conn["receive_task"]
            except asyncio.CancelledError:
                pass

        if conn["ws"]:
            try:
                await conn["ws"].send(json.dumps({"text": ""}))
                await conn["ws"].close()
            except Exception as e:
                logger.error(f"Error closing voice {voice_id}: {e}")

        total_chars = conn.get("total_chars", 0)
        model_id = conn.get("model", "")
        del self._connections[voice_id]
        logger.info(f"Disconnected voice {voice_id} (total chars sent: {total_chars})")

        # Deduct usage from quota system
        if total_chars > 0 and self._user:
            self._deduct_tts_usage(total_chars, model_id)

    async def send_text(self, voice_id: str, text: str) -> None:
        """
        Send text to be synthesized.

        Args:
            voice_id: Voice to use
            text: Text chunk to synthesize
        """
        if voice_id not in self._connections:
            return

        conn = self._connections[voice_id]
        if conn["closing"]:
            return

        # Strip bracketed annotations for models that don't support audio tags (pre-v3)
        # Eleven v3 interprets [laughs], [sighs] etc. as emotional cues
        text = strip_bracketed_text(text, model_id=conn.get("model"))
        if not text:
            return

        # Clear muted flag when sending new text (resume after interruption)
        if self._muted.get(voice_id):
            self._muted[voice_id] = False
            logger.info(f"TTS unmuted for voice {voice_id}")

        try:
            # Track characters sent for billing awareness
            char_count = len(text)
            conn["total_chars"] = conn.get("total_chars", 0) + char_count
            logger.info(f"TTS: Sending {char_count} chars to ElevenLabs (total: {conn['total_chars']})")

            message = {
                "text": text,
                "try_trigger_generation": True,
            }
            await conn["ws"].send(json.dumps(message))
        except Exception as e:
            logger.error(f"Error sending text to voice {voice_id}: {e}")
            if self.on_error:
                await self.on_error(voice_id, f"Send error: {str(e)}")

    async def flush(self, voice_id: str) -> None:
        """Flush the text buffer to generate remaining audio."""
        if voice_id not in self._connections:
            return

        conn = self._connections[voice_id]
        if conn["closing"]:
            return

        try:
            # Create/reset completion event for this voice
            self._completion_events[voice_id] = asyncio.Event()

            message = {
                "text": " ",
                "flush": True,
            }
            await conn["ws"].send(json.dumps(message))
        except Exception as e:
            logger.error(f"Error flushing voice {voice_id}: {e}")

    async def stop_generation(self, voice_id: str) -> None:
        """
        Stop audio generation for a voice (used during user interruption).

        Mutes the voice so any pending audio is discarded.
        The voice will be unmuted when new text is sent.
        """
        self._muted[voice_id] = True
        # Reset sequence number for clean restart
        if voice_id in self._connections:
            self._connections[voice_id]["sequence"] = 0
        # Clear completion event so nothing waits for it
        if voice_id in self._completion_events:
            self._completion_events[voice_id].set()
        logger.info(f"TTS generation stopped for voice {voice_id}")

    async def wait_for_completion(
        self,
        voice_id: str,
        timeout: float = 120.0,
        audio_silence_timeout: float = TTS_AUDIO_SILENCE_TIMEOUT_SEC
    ) -> bool:
        """
        Wait for audio generation to complete after a flush.

        Uses two strategies:
        1. Wait for isFinal signal from ElevenLabs
        2. If no audio received for audio_silence_timeout seconds after flush, assume complete

        Args:
            voice_id: Voice ID to wait for
            timeout: Maximum total time to wait in seconds
            audio_silence_timeout: Consider complete if no audio for this many seconds

        Returns:
            True if completed, False if timed out
        """
        import time

        if voice_id not in self._completion_events:
            return True

        start_time = time.time()
        flush_time = start_time

        try:
            while True:
                # Check if we've exceeded total timeout
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    logger.warning(f"Timeout waiting for audio completion for voice {voice_id}")
                    return False

                # Check if completion event is set (isFinal received)
                if self._completion_events[voice_id].is_set():
                    return True

                # Check audio silence - if we received audio but nothing for a while, assume complete
                last_audio = self._last_audio_time.get(voice_id, 0)
                if last_audio > flush_time:
                    # We received some audio after flush
                    silence_duration = time.time() - last_audio
                    if silence_duration >= audio_silence_timeout:
                        logger.info(f"Audio silence detected for voice {voice_id} ({silence_duration:.1f}s), assuming complete")
                        return True

                # Wait a bit before checking again
                try:
                    await asyncio.wait_for(
                        self._completion_events[voice_id].wait(),
                        timeout=0.5  # Check every 500ms
                    )
                    return True
                except asyncio.TimeoutError:
                    continue  # Keep looping

        finally:
            # Cleanup
            self._completion_events.pop(voice_id, None)
            self._last_audio_time.pop(voice_id, None)

    async def _receive_loop(self, voice_id: str) -> None:
        """Receive and process audio from ElevenLabs."""
        conn = self._connections.get(voice_id)
        if not conn:
            return

        try:
            async for message in conn["ws"]:
                if conn["closing"]:
                    break

                try:
                    data = json.loads(message)
                    await self._handle_message(voice_id, data)
                except json.JSONDecodeError:
                    if isinstance(message, bytes):
                        await self._handle_audio(voice_id, message)

        except websockets.exceptions.ConnectionClosed as e:
            if not conn.get("closing"):
                logger.warning(f"ElevenLabs connection closed for {voice_id}: {e}")
                if self.on_error:
                    await self.on_error(voice_id, f"Connection closed: {str(e)}")
        except Exception as e:
            if not conn.get("closing"):
                logger.error(f"Error in ElevenLabs receive loop for {voice_id}: {e}")
                if self.on_error:
                    await self.on_error(voice_id, str(e))

    async def _keepalive_loop(self, voice_id: str) -> None:
        """Send keepalive messages to prevent connection timeout."""
        conn = self._connections.get(voice_id)
        if not conn:
            return

        try:
            while not conn.get("closing"):
                await asyncio.sleep(TTS_KEEPALIVE_INTERVAL_SEC)
                if conn.get("closing"):
                    break
                if conn.get("ws"):
                    try:
                        # Send a space with flush to keep connection alive
                        await conn["ws"].send(json.dumps({
                            "text": " ",
                            "try_trigger_generation": False,
                        }))
                        logger.info(f"Sent keepalive to ElevenLabs for voice {voice_id}")
                    except Exception as e:
                        logger.warning(f"Keepalive failed for voice {voice_id}: {e}")
                        break
        except asyncio.CancelledError:
            pass

    async def _handle_message(self, voice_id: str, data: dict) -> None:
        """Handle a JSON message from ElevenLabs."""
        import time

        if "audio" in data:
            audio_base64 = data["audio"]
            if audio_base64:
                # Skip audio if voice is muted (user interrupted)
                if self._muted.get(voice_id):
                    return

                conn = self._connections.get(voice_id)
                if conn and self.on_audio:
                    conn["sequence"] += 1
                    self._last_audio_time[voice_id] = time.time()
                    await self.on_audio(voice_id, audio_base64, conn["sequence"])

        # Handle word-level alignment data for live transcript sync
        alignment = data.get("normalizedAlignment") or data.get("alignment")
        if alignment and self.on_alignment:
            # Skip if muted
            if self._muted.get(voice_id):
                return
            # Parse alignment data - ElevenLabs provides character-level timing
            alignment_data = {
                "chars": alignment.get("chars") or alignment.get("characters", []),
                "charStartTimesMs": alignment.get("charStartTimesMs") or alignment.get("char_start_times_ms", []),
                "charDurationsMs": alignment.get("charDurationsMs") or alignment.get("char_durations_ms", []),
            }
            if alignment_data["chars"]:
                await self.on_alignment(voice_id, alignment_data)

        # Check for completion signal (isFinal flag indicates all audio has been generated)
        if data.get("isFinal"):
            logger.info(f"Audio generation complete for voice {voice_id} (isFinal received)")
            # Signal completion event
            if voice_id in self._completion_events:
                self._completion_events[voice_id].set()
            # Call the completion callback if set
            if self.on_audio_complete:
                await self.on_audio_complete(voice_id)

        if "error" in data:
            error_msg = data.get("message", str(data["error"]))
            logger.error(f"ElevenLabs error for {voice_id}: {error_msg}")
            if self.on_error:
                await self.on_error(voice_id, error_msg)
            # Also signal completion on error to prevent hanging
            if voice_id in self._completion_events:
                self._completion_events[voice_id].set()

    async def _handle_audio(self, voice_id: str, audio_bytes: bytes) -> None:
        """Handle binary audio data."""
        conn = self._connections.get(voice_id)
        if conn and self.on_audio:
            conn["sequence"] += 1
            audio_base64 = base64.b64encode(audio_bytes).decode()
            await self.on_audio(voice_id, audio_base64, conn["sequence"])

    async def get_voices(self) -> List[VoiceInfo]:
        """Fetch available voices from ElevenLabs."""
        if not self._http_client:
            await self.initialize()

        try:
            response = await self._http_client.get("/voices")
            response.raise_for_status()
            data = response.json()

            voices = []
            for v in data.get("voices", []):
                voices.append(VoiceInfo(
                    voice_id=v["voice_id"],
                    name=v["name"],
                    category=v.get("category", "premade"),
                    description=v.get("description"),
                    preview_url=v.get("preview_url"),
                    labels=v.get("labels"),
                    high_quality_base_model_ids=v.get("high_quality_base_model_ids"),
                    verified_languages=v.get("verified_languages"),
                ))

            return voices

        except Exception as e:
            logger.error(f"Failed to fetch voices: {e}")
            return []

    async def get_models(self) -> List[dict]:
        """Fetch available models with their supported languages from ElevenLabs."""
        if not self._http_client:
            await self.initialize()

        try:
            response = await self._http_client.get("/models")
            response.raise_for_status()
            data = response.json()

            models = []
            for m in data:
                languages = []
                for lang in m.get("languages", []):
                    languages.append({
                        "language_id": lang.get("language_id"),
                        "name": lang.get("name"),
                    })

                models.append({
                    "model_id": m.get("model_id"),
                    "name": m.get("name"),
                    "description": m.get("description"),
                    "can_be_finetuned": m.get("can_be_finetuned", False),
                    "can_do_text_to_speech": m.get("can_do_text_to_speech", False),
                    "can_do_voice_conversion": m.get("can_do_voice_conversion", False),
                    "can_use_style": m.get("can_use_style", False),
                    "can_use_speaker_boost": m.get("can_use_speaker_boost", False),
                    "serves_pro_voices": m.get("serves_pro_voices", False),
                    "token_cost_factor": m.get("token_cost_factor", 1.0),
                    "languages": languages,
                })

            return models

        except Exception as e:
            logger.error(f"Failed to fetch models: {e}")
            return []

    def is_voice_connected(self, voice_id: str) -> bool:
        """Check if a voice is currently connected."""
        return voice_id in self._connections and not self._connections[voice_id].get("closing")

    async def text_to_speech(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model_id: Optional[str] = None,
        stability: Optional[float] = None,
        similarity_boost: Optional[float] = None,
        style: Optional[float] = None,
        speed: Optional[float] = None,
        use_speaker_boost: Optional[bool] = None,
    ) -> Optional[bytes]:
        """
        Convert text to speech using ElevenLabs HTTP API.

        This is a simpler alternative to the WebSocket streaming approach,
        suitable for one-shot TTS requests like reading chat messages.

        Args:
            text: Text to convert to speech
            voice_id: ElevenLabs voice ID (defaults to settings.ELEVENLABS_DEFAULT_VOICE)
            model_id: TTS model to use (defaults to settings.ELEVENLABS_MODEL)
            stability: Voice stability (0-1)
            similarity_boost: Voice similarity boost (0-1)
            style: Style exaggeration (0-1)
            speed: Speech speed (0.5-2.0)
            use_speaker_boost: Enable speaker boost

        Returns:
            Audio bytes (MP3 format) or None if failed
        """
        if not self._http_client:
            await self.initialize()

        if not self.api_key:
            logger.error("ElevenLabs API key not configured")
            return None

        # Use defaults from settings if not provided
        voice_id = voice_id or getattr(settings, 'ELEVENLABS_DEFAULT_VOICE', 'EXAVITQu4vr4xnSDxMaL')  # Sarah
        model_id = model_id or settings.ELEVENLABS_MODEL
        stability = stability if stability is not None else settings.ELEVENLABS_STABILITY
        similarity_boost = similarity_boost if similarity_boost is not None else settings.ELEVENLABS_SIMILARITY_BOOST
        style = style if style is not None else settings.ELEVENLABS_STYLE
        use_speaker_boost = use_speaker_boost if use_speaker_boost is not None else settings.ELEVENLABS_USE_SPEAKER_BOOST

        # Strip bracketed annotations for models that don't support audio tags (pre-v3)
        # Eleven v3 interprets [laughs], [sighs] etc. as emotional cues
        text = strip_bracketed_text(text, model_id=model_id)
        if not text:
            return None

        # Pre-check quota before making API call
        try:
            await self._check_tts_quota(estimated_chars=len(text), model_id=model_id)
        except Exception as e:
            logger.error(f"Quota pre-check failed for TTS: {e}")
            return None

        try:
            request_body = {
                "text": text,
                "model_id": model_id,
                "voice_settings": {
                    "stability": stability,
                    "similarity_boost": similarity_boost,
                    "style": style,
                    "use_speaker_boost": use_speaker_boost,
                }
            }

            # Add speed if provided (ElevenLabs API parameter outside voice_settings)
            if speed is not None:
                request_body["speed"] = speed

            response = await self._http_client.post(
                f"/text-to-speech/{voice_id}",
                json=request_body,
                headers={
                    "Accept": "audio/mpeg",
                },
                timeout=60.0,  # TTS can take a while for long texts
            )
            response.raise_for_status()

            # Deduct usage from quota system after successful generation
            character_count = len(text)
            self._deduct_tts_usage(character_count, model_id)

            return response.content

        except Exception as e:
            logger.error(f"Failed to generate TTS audio: {e}")
            return None


class ElevenLabsTTSProvider(TTSProvider):
    """
    ElevenLabs TTS Provider wrapper.

    This wraps the ElevenLabsTTSClient to implement the TTSProvider interface
    for use with the provider factory.

    Features:
    - High-quality neural voices
    - Voice cloning capability
    - Advanced voice settings (stability, similarity, style)
    - Large voice library
    """

    PROVIDER_ID = "elevenlabs"
    PROVIDER_NAME = "ElevenLabs"

    def __init__(self, user=None, session_id: Optional[str] = None, feature=None):
        from usage_quota.models import FeatureType as _FT
        self._client = ElevenLabsTTSClient(
            user=user,
            session_id=session_id,
            feature=feature if feature is not None else _FT.VOICE_ROOM,
        )

    async def initialize(self) -> None:
        """Initialize the underlying client."""
        await self._client.initialize()

    async def cleanup(self) -> None:
        """Cleanup the underlying client."""
        await self._client.cleanup()

    async def text_to_speech(
        self,
        text: str,
        voice_id: str,
        model_id: Optional[str] = None,
        settings: Optional[TTSSettings] = None,
    ) -> Optional[bytes]:
        """
        Convert text to speech using ElevenLabs.

        Args:
            text: Text to convert
            voice_id: ElevenLabs voice ID
            model_id: TTS model (e.g., eleven_flash_v2_5)
            settings: TTS settings including stability, similarity, style, speed

        Returns:
            Audio bytes (MP3) or None if failed
        """
        settings = settings or TTSSettings()

        return await self._client.text_to_speech(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            stability=settings.stability,
            similarity_boost=settings.similarity_boost,
            style=settings.style,
            speed=settings.speed,
            use_speaker_boost=settings.use_speaker_boost,
        )

    async def get_voices(self) -> List[TTSVoice]:
        """Get available ElevenLabs voices."""
        voices = await self._client.get_voices()
        return [
            TTSVoice(
                voice_id=v.voice_id,
                name=v.name,
                provider=self.PROVIDER_ID,
                description=v.description,
                preview_url=v.preview_url,
                category=v.category,
                labels=v.labels,
                metadata={
                    "high_quality_base_model_ids": v.high_quality_base_model_ids,
                    "verified_languages": v.verified_languages,
                },
            )
            for v in voices
        ]

    async def get_models(self) -> List[TTSModel]:
        """Get available ElevenLabs TTS models."""
        models = await self._client.get_models()
        return [
            TTSModel(
                model_id=m["model_id"],
                name=m["name"],
                provider=self.PROVIDER_ID,
                description=m.get("description"),
                languages=m.get("languages", []),
                can_use_style=m.get("can_use_style", False),
                can_use_speaker_boost=m.get("can_use_speaker_boost", False),
                metadata={
                    "can_be_finetuned": m.get("can_be_finetuned", False),
                    "can_do_voice_conversion": m.get("can_do_voice_conversion", False),
                    "serves_pro_voices": m.get("serves_pro_voices", False),
                    "token_cost_factor": m.get("token_cost_factor", 1.0),
                },
            )
            for m in models
            if m.get("can_do_text_to_speech", False)
        ]

    def get_default_voice_id(self) -> str:
        """Default to Rachel voice."""
        return getattr(settings, 'ELEVENLABS_DEFAULT_VOICE', '21m00Tcm4TlvDq8ikWAM')

    def get_default_model_id(self) -> str:
        """Default to flash model for speed."""
        return getattr(settings, 'ELEVENLABS_MODEL', 'eleven_flash_v2_5')

    def get_supported_settings(self) -> List[str]:
        """ElevenLabs supports many voice tuning settings."""
        return ["speed", "stability", "similarity_boost", "style", "use_speaker_boost"]
