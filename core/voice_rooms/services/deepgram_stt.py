"""Deepgram Speech-to-Text client for real-time transcription."""

import asyncio
import json
import logging
from typing import Callable, Optional, Awaitable, TYPE_CHECKING

import websockets
from websockets.asyncio.client import ClientConnection
from django.conf import settings

if TYPE_CHECKING:
    from authentication.models import User

logger = logging.getLogger(__name__)


class DeepgramSTTClient:
    """
    Real-time speech-to-text using Deepgram's streaming API.

    Features:
    - Real-time transcription via WebSocket
    - Automatic language detection
    - Voice activity detection (VAD)
    - Endpointing for turn detection
    - Interim and final results
    """

    DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"

    def __init__(
        self,
        on_transcript: Callable[[str, bool, Optional[str], Optional[float]], Awaitable[None]],
        on_speech_start: Optional[Callable[[], Awaitable[None]]] = None,
        on_speech_end: Optional[Callable[[], Awaitable[None]]] = None,
        on_utterance_end: Optional[Callable[[], Awaitable[None]]] = None,
        on_error: Optional[Callable[[str], Awaitable[None]]] = None,
        user: Optional['User'] = None,
        session_id: Optional[str] = None,
    ):
        """
        Initialize the Deepgram STT client.

        Args:
            on_transcript: Callback for transcription results (text, is_final, language, confidence)
            on_speech_start: Callback when speech starts
            on_speech_end: Callback when speech ends
            on_utterance_end: Callback when an utterance is complete
            on_error: Callback for errors
            user: User for quota tracking (optional)
            session_id: Session ID for quota tracking (optional)
        """
        self.api_key = settings.DEEPGRAM_API_KEY
        self.on_transcript = on_transcript
        self.on_speech_start = on_speech_start
        self.on_speech_end = on_speech_end
        self.on_utterance_end = on_utterance_end
        self.on_error = on_error
        self._user = user
        self._session_id = session_id

        self.ws: Optional[ClientConnection] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._keepalive_task: Optional[asyncio.Task] = None
        self._connected = False
        self._closing = False
        self._language = "auto"
        self._reconnecting = False
        self._audio_bytes_sent = 0  # Track audio data for quota estimation
        self._last_not_connected_log: Optional[float] = None  # Throttle "not connected" log spam

    def _deduct_stt_usage(self) -> None:
        """Deduct STT usage from quota system based on audio bytes sent."""
        if not self._user or self._audio_bytes_sent == 0:
            return

        # Estimate audio duration from bytes sent
        # WebM/Opus at ~32kbps (typical for voice) gives us roughly:
        # 32000 bits/second = 4000 bytes/second
        # So audio_seconds = bytes / 4000
        ESTIMATED_BITRATE_BPS = 4000  # bytes per second for voice opus
        audio_seconds = self._audio_bytes_sent / ESTIMATED_BITRATE_BPS
        model_id = getattr(settings, 'DEEPGRAM_MODEL', 'nova-2')

        try:
            from usage_quota.billing import get_billing_service, BillableOperation
            from usage_quota.models import ServiceType, FeatureType

            operation = BillableOperation(
                service=ServiceType.DEEPGRAM_STT,
                feature=FeatureType.VOICE_ROOM,
                model_id=model_id,
                audio_seconds=audio_seconds,
                session_id=self._session_id or '',
            )
            billing = get_billing_service()
            # Deepgram is always platform-billed; the BillingService guard
            # rejects 'byok' for DEEPGRAM_STT but we set 'platform'
            # explicitly here for clarity.
            billing.record_usage(self._user, operation, billing_origin='platform')
            logger.info(f"Deepgram STT usage recorded: {audio_seconds:.1f}s audio")
        except Exception as e:
            logger.error(f"Failed to record Deepgram STT usage: {e}")

    async def _check_stt_quota(self, estimated_seconds: float = 300.0) -> bool:
        """
        Pre-check quota before STT operations.

        Args:
            estimated_seconds: Estimated audio duration in seconds (default 5 minutes)

        Returns:
            True if quota is available, False otherwise

        Raises:
            QuotaExceededException if quota is exceeded
        """
        if not self._user:
            return True

        try:
            from decimal import Decimal
            from usage_quota.billing import get_billing_service
            from usage_quota.models import ServiceType, FeatureType
            from usage_quota.exceptions import QuotaExceededException
            from usage_quota.services import get_cost_calculator

            # Estimate cost
            model_id = getattr(settings, 'DEEPGRAM_MODEL', 'nova-2')
            cost_calculator = get_cost_calculator()
            estimated_cost = cost_calculator.calculate_deepgram_cost(
                audio_seconds=estimated_seconds,
                model_id=model_id,
            )

            # Check quota using BillingService — feature_name routes
            # through the tier cascading guard. The guard raises on
            # FeatureNotAvailable / QuotaExceeded; on success it returns
            # an allowed QuotaStatus.
            billing = get_billing_service()
            billing.check_quota(
                user=self._user,
                service=ServiceType.DEEPGRAM_STT,
                estimated_cost=Decimal(str(estimated_cost)),
                feature=FeatureType.VOICE_ROOM,
                feature_name='voice_stt',
            )
            return True

        except Exception as e:
            # Re-raise quota / tier exceptions
            from usage_quota.exceptions import (
                FeatureNotAvailableException,
                QuotaExceededException,
            )
            if isinstance(e, (QuotaExceededException, FeatureNotAvailableException)):
                raise
            # Log but don't block on other errors
            logger.error(f"Failed to check STT quota: {e}")
            return True

    async def connect(self, language: str = "auto") -> bool:
        """
        Connect to Deepgram streaming API.

        Args:
            language: Language code or "auto" for detection

        Returns:
            True if connection successful
        """
        if self._connected:
            logger.warning("Already connected to Deepgram")
            return True

        if not self.api_key:
            logger.error("Deepgram API key not configured")
            if self.on_error:
                await self.on_error("Deepgram API key not configured")
            return False

        # Pre-check quota before connecting (estimate ~5 minutes of audio)
        try:
            await self._check_stt_quota(estimated_seconds=300.0)
        except Exception as e:
            logger.error(f"Quota pre-check failed for Deepgram STT: {e}")
            if self.on_error:
                error_msg = str(e) if hasattr(e, 'message') else "Quota exceeded"
                await self.on_error(error_msg)
            return False

        try:
            params = self._build_params(language)
            url = f"{self.DEEPGRAM_WS_URL}?{params}"

            headers = {
                "Authorization": f"Token {self.api_key}",
            }

            logger.info(f"Connecting to Deepgram STT (language={language})...")
            logger.info(f"Deepgram URL params: {params}")

            # Add timeout to prevent hanging
            # Increase ping_timeout to handle longer agent responses
            self.ws = await asyncio.wait_for(
                websockets.connect(
                    url,
                    additional_headers=headers,
                    ping_interval=10,
                    ping_timeout=60,
                ),
                timeout=10.0
            )

            self._connected = True
            self._closing = False
            self._language = language

            self._receive_task = asyncio.create_task(self._receive_loop())
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())

            logger.info("Connected to Deepgram STT successfully")
            return True

        except asyncio.TimeoutError:
            logger.error("Deepgram WebSocket connection timed out after 10s")
            if self.on_error:
                await self.on_error("Connection timed out")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to Deepgram: {e}", exc_info=True)
            if self.on_error:
                await self.on_error(f"Connection failed: {str(e)}")
            return False

    def _build_params(self, language: str) -> str:
        """Build URL query parameters for Deepgram."""
        # Start with minimal required params
        # Note: Frontend sends audio/webm;codecs=opus, so we don't specify encoding
        # Deepgram will auto-detect the format from the audio stream
        params = {
            "model": settings.DEEPGRAM_MODEL,
            "punctuate": "true",
            "interim_results": "true",
            "smart_format": "true",
        }

        # Language detection requires specific tier - use English as fallback for "auto"
        if language == "auto":
            params["language"] = "en"
        else:
            params["language"] = language

        # Endpointing - detect pauses in speech (sends speech_final: true)
        if settings.DEEPGRAM_ENDPOINTING_MS:
            params["endpointing"] = str(settings.DEEPGRAM_ENDPOINTING_MS)

        # Utterance end - detect when user stops speaking (sends UtteranceEnd event)
        # This is key for auto-detecting when to process the message
        if settings.DEEPGRAM_UTTERANCE_END_MS:
            params["utterance_end_ms"] = str(settings.DEEPGRAM_UTTERANCE_END_MS)

        # Enable VAD events for speech start/end detection
        params["vad_events"] = "true"

        logger.info(f"Deepgram params: {params}")
        return "&".join(f"{k}={v}" for k, v in params.items())

    async def send_audio(self, audio_data: bytes) -> None:
        """
        Send audio data to Deepgram.

        Args:
            audio_data: Audio bytes (WebM/Opus or other supported format)
        """
        # Auto-reconnect if disconnected
        if not self._connected and not self._closing and not self._reconnecting:
            logger.info("Deepgram disconnected, attempting reconnect before sending audio...")
            reconnected = await self.reconnect()
            if not reconnected:
                logger.warning("Deepgram reconnect failed, audio chunk dropped")
                return

        if not self._connected or not self.ws:
            # Log once per second instead of every chunk
            if self._last_not_connected_log is None or \
               (asyncio.get_event_loop().time() - self._last_not_connected_log) > 1.0:
                logger.warning("Deepgram not connected, audio chunk dropped")
                self._last_not_connected_log = asyncio.get_event_loop().time()
            return

        try:
            await self.ws.send(audio_data)
            # Track audio bytes for quota estimation
            self._audio_bytes_sent += len(audio_data)
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"Deepgram connection closed while sending: {e}")
            self._connected = False
            # Don't report error, will reconnect on next send
        except (AttributeError, TypeError) as e:
            # Handle ws becoming None during send
            error_str = str(e).lower()
            if "'nonetype'" in error_str:
                logger.debug("Deepgram send skipped (connection closed)")
                self._connected = False
            else:
                logger.error(f"Error sending audio to Deepgram: {e}")
        except Exception as e:
            error_str = str(e).lower()
            # Don't report connection-related errors
            if "'nonetype'" in error_str or 'connection' in error_str:
                logger.warning(f"Deepgram send error (will reconnect): {e}")
                self._connected = False
            else:
                logger.error(f"Error sending audio to Deepgram: {e}")
                if self.on_error:
                    await self.on_error(f"Send error: {str(e)}")

    async def close(self) -> None:
        """Close the WebSocket connection."""
        self._closing = True
        self._connected = False

        # Deduct usage from quota system before cleanup
        self._deduct_stt_usage()

        if self._keepalive_task:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                logger.error(f"Error closing Deepgram WebSocket: {e}")
            self.ws = None

        logger.info(f"Disconnected from Deepgram STT (total audio: {self._audio_bytes_sent} bytes)")

    async def reconnect(self) -> bool:
        """Reconnect to Deepgram after a connection loss."""
        if self._reconnecting or self._closing:
            return False

        self._reconnecting = True
        logger.info("Attempting to reconnect to Deepgram...")

        try:
            # Clean up old connection
            self._connected = False
            if self.ws:
                try:
                    await self.ws.close()
                except Exception:
                    pass
                self.ws = None

            # Wait a bit before reconnecting
            await asyncio.sleep(0.5)

            # Reconnect with same language
            success = await self.connect(self._language)
            if success:
                logger.info("Successfully reconnected to Deepgram")
            else:
                logger.error("Failed to reconnect to Deepgram")
            return success
        finally:
            self._reconnecting = False

    async def _receive_loop(self) -> None:
        """Receive and process messages from Deepgram."""
        try:
            # Guard against ws being None
            ws = self.ws
            if not ws:
                return

            async for message in ws:
                if self._closing or not self.ws:
                    break

                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from Deepgram")

        except websockets.exceptions.ConnectionClosed as e:
            if not self._closing:
                logger.warning(f"Deepgram connection closed: {e}")
                self._connected = False
                # Don't call on_error - auto-reconnect will handle this on next audio chunk
                logger.info("Deepgram will reconnect on next audio chunk")
        except asyncio.CancelledError:
            # Task was cancelled, this is expected during cleanup
            pass
        except (AttributeError, TypeError) as e:
            # Handle case where ws becomes None during iteration
            # This can manifest as AttributeError or TypeError from websockets library
            if not self._closing:
                error_str = str(e).lower()
                if "'nonetype'" in error_str or "_resume_reading" in error_str:
                    logger.debug("Deepgram receive loop stopped (connection closed during iteration)")
                    self._connected = False
                else:
                    logger.error(f"Error in Deepgram receive loop: {e}")
                    if self.on_error:
                        await self.on_error(str(e))
        except Exception as e:
            if not self._closing:
                error_str = str(e).lower()
                # Gracefully handle connection closure errors
                if "'nonetype'" in error_str or "_resume_reading" in error_str:
                    logger.debug("Deepgram receive loop stopped (connection closed)")
                    self._connected = False
                else:
                    logger.error(f"Error in Deepgram receive loop: {e}")
                    if self.on_error:
                        await self.on_error(str(e))

    async def _handle_message(self, data: dict) -> None:
        """Handle a message from Deepgram."""
        msg_type = data.get("type")

        if msg_type == "Results":
            await self._handle_results(data)
        elif msg_type == "SpeechStarted":
            logger.info("Deepgram: Speech started")
            if self.on_speech_start:
                await self.on_speech_start()
        elif msg_type == "UtteranceEnd":
            logger.info("Deepgram: Utterance end detected (user stopped speaking)")
            if self.on_utterance_end:
                await self.on_utterance_end()
        elif msg_type == "Error":
            error_msg = data.get("message", "Unknown error")
            logger.error(f"Deepgram error: {error_msg}")
            if self.on_error:
                await self.on_error(error_msg)
        else:
            logger.debug(f"Deepgram message type: {msg_type}")

    async def _handle_results(self, data: dict) -> None:
        """Handle transcription results."""
        channel = data.get("channel", {})
        alternatives = channel.get("alternatives", [])

        if not alternatives:
            logger.debug("No alternatives in transcription result")
            return

        best = alternatives[0]
        transcript = best.get("transcript", "").strip()

        if not transcript:
            return

        is_final = data.get("is_final", False)
        speech_final = data.get("speech_final", False)
        confidence = best.get("confidence")
        detected_language = data.get("detected_language")

        logger.info(f"Deepgram transcript: '{transcript}' (is_final={is_final}, speech_final={speech_final}, confidence={confidence})")

        await self.on_transcript(
            transcript,
            is_final or speech_final,
            detected_language,
            confidence,
        )

        if speech_final and self.on_speech_end:
            await self.on_speech_end()

    async def _keepalive_loop(self) -> None:
        """Send keepalive messages to maintain Deepgram connection during idle periods."""
        keepalive_count = 0
        while self._connected and not self._closing:
            try:
                await asyncio.sleep(5)
                if self.ws and self._connected and not self._closing:
                    # Deepgram accepts KeepAlive messages to prevent timeout
                    await self.ws.send(json.dumps({"type": "KeepAlive"}))
                    keepalive_count += 1
                    if keepalive_count % 6 == 0:  # Log every 30 seconds
                        logger.debug(f"Deepgram keepalive sent (count={keepalive_count})")
            except asyncio.CancelledError:
                break
            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"Deepgram connection closed during keepalive: {e}")
                self._connected = False
                break
            except Exception as e:
                # Check for NoneType errors indicating connection is gone
                if "'nonetype'" in str(e).lower():
                    logger.debug("Deepgram keepalive stopped (connection closed)")
                    self._connected = False
                else:
                    logger.error(f"Deepgram keepalive error: {e}")
                break

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._connected and self.ws is not None
