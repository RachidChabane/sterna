"""Voice Room Orchestrator - coordinates the conversation flow."""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Callable, Dict, List, Optional, Awaitable, Any

from django.conf import settings

from .deepgram_stt import DeepgramSTTClient
from .elevenlabs_tts import VoiceSettings
from .tts_client_factory import MultiProviderTTSClient, detect_tts_provider
from .llm_router import LLMRouter
from voice_rooms.constants import (
    DEFAULT_SILENCE_TIMEOUT_SEC,
    MIN_SILENCE_TIMEOUT_SEC,
    MAX_SILENCE_TIMEOUT_SEC,
    DUPLICATE_MESSAGE_COOLDOWN_SEC,
    INTERRUPTION_COOLDOWN_SEC,
    TTS_GENERATION_TIMEOUT_SEC,
    PLAYBACK_WAIT_TIMEOUT_SEC,
    PLAYBACK_CHECK_INTERVAL_SEC,
)

logger = logging.getLogger(__name__)


def filter_thinking_tags(text: str) -> str:
    """
    Remove internal thinking/reasoning tags from LLM output before TTS.

    Filters patterns like:
    - <thinking>...</thinking>, <think>...</think>
    - <thought>...</thought>
    - <internal>...</internal>
    - <scratchpad>...</scratchpad>
    - *thinking: ...*, **Internal:**
    - [Internal: ...], [Thinking: ...]
    - (thinking: ...), (internal: ...)
    """
    original_text = text

    # Remove XML-style thinking tags (handles multiline)
    # Common tags used by various models
    xml_patterns = [
        r'<thinking>.*?</thinking>',
        r'<think>.*?</think>',
        r'<thought>.*?</thought>',
        r'<thoughts>.*?</thoughts>',
        r'<internal>.*?</internal>',
        r'<reasoning>.*?</reasoning>',
        r'<reflection>.*?</reflection>',
        r'<scratchpad>.*?</scratchpad>',
        r'<analysis>.*?</analysis>',
        r'<inner_monologue>.*?</inner_monologue>',
        r'<self_reflection>.*?</self_reflection>',
    ]
    for pattern in xml_patterns:
        text = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE)

    # Remove asterisk-style thinking (*thinking: ...* or *internal thoughts* or **Thinking:**...)
    text = re.sub(r'\*\*?(?:thinking|internal|thought|reasoning|reflection|analysis)[:\s].*?\*\*?', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Also match **Internal thoughts:** followed by content until next ** or end of line
    text = re.sub(r'\*\*(?:Internal thoughts?|Thinking|Reasoning)[:\s]*\*\*[^\n]*', '', text, flags=re.IGNORECASE)

    # Remove bracket-style thinking ([Internal: ...] or [Thinking: ...])
    text = re.sub(r'\[(?:internal|thinking|thought|reasoning|reflection)[:\s].*?\]', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Remove parenthesis-style thinking ((thinking: ...) or (internal: ...))
    text = re.sub(r'\((?:thinking|internal|thought|reasoning|reflection)[:\s].*?\)', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Remove lines that start with common thinking prefixes
    text = re.sub(r'^(?:Internal(?: thoughts?)?|Thinking|Reasoning|Reflection|Analysis)[:\s].*$', '', text, flags=re.MULTILINE | re.IGNORECASE)

    # Remove "Let me think..." style phrases at the start
    text = re.sub(r'^(?:Let me (?:think|reason|analyze|consider).*?[.!]\s*)', '', text, flags=re.IGNORECASE)

    # Clean up extra whitespace
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)  # Max 2 newlines
    text = re.sub(r'  +', ' ', text)

    result = text.strip()

    # Log if anything was filtered
    if result != original_text.strip():
        removed_chars = len(original_text) - len(result)
        logger.info(f"[FILTER] Removed {removed_chars} chars of internal thinking")

    return result


def build_agent_routing_tool(agent_names: List[str], user_name: Optional[str] = None) -> Dict:
    """Build tool for redirecting messages to other agents or back to the user."""
    # Include user as a valid redirect target
    user_target = user_name if user_name else "User"
    all_targets = agent_names + [user_target]

    return {
        "type": "function",
        "function": {
            "name": "redirect_to_agent",
            "description": f"ONLY use when someone is EXPLICITLY mentioned by name (e.g. 'Hey Marie' or 'What do you think, Robert?'). Valid targets: {', '.join(all_targets)}. NEVER redirect for general statements, topics, or prompts - respond yourself instead. Your job is to speak, not to delegate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "enum": all_targets,
                    },
                },
                "required": ["agent_name"],
            },
        },
    }


class RoomStatus:
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    PAUSED = "paused"
    ENDED = "ended"
    ERROR = "error"
    CONNECTING = "connecting"


class VoiceRoomOrchestrator:
    """
    Main orchestrator for voice room conversation flow.

    Coordinates:
    - User speech transcription (Deepgram)
    - Agent LLM responses (OpenRouter)
    - Agent voice synthesis (ElevenLabs)
    - Turn management
    - State management
    """

    def __init__(
        self,
        room_id: str,
        agents: List[Dict[str, Any]],
        language: str,
        max_response_tokens: int,
        send_event: Callable[[Dict], Awaitable[None]],
        session_id: Optional[str] = None,
        initial_conversation: Optional[List[Dict]] = None,
        save_message: Optional[Callable[[Dict], Awaitable[None]]] = None,
        room_description: Optional[str] = None,
        user_name: Optional[str] = None,
        user: Optional[Any] = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            room_id: Voice room ID
            agents: List of agent configurations
            language: Language code or 'auto'
            max_response_tokens: Max tokens per response
            send_event: Callback to send events to the client
            session_id: Database session ID for persistence
            initial_conversation: Previous conversation to continue from
            save_message: Callback to persist messages to database
            room_description: Description of the room's purpose/topic
            user_name: User's display name for agents to address them
            user: User object for API key resolution
        """
        self.room_id = room_id
        self.agents = agents
        self.language = language
        self.max_response_tokens = max_response_tokens
        self.send_event = send_event
        self.session_id = session_id
        self.save_message = save_message
        self.room_description = room_description
        self.user_name = user_name
        self._user = user

        # State
        self.status = RoomStatus.IDLE
        self.current_speaker: Optional[str] = None
        self.detected_language: Optional[str] = None
        self.conversation: List[Dict] = initial_conversation or []
        self.started_at: Optional[datetime] = None

        # Agent lookup
        self.agents_by_id: Dict[str, Dict] = {a["id"]: a for a in agents}
        self.agents_by_order = sorted(agents, key=lambda a: a.get("order", 0))

        # Service clients
        self.stt_client: Optional[DeepgramSTTClient] = None
        self.tts_client: Optional[MultiProviderTTSClient] = None
        self.llm_client: Optional[LLMRouter] = None

        # Processing state
        self._processing_lock = asyncio.Lock()
        self._current_transcript = ""
        self._last_interim_transcript = ""  # Track interim for fallback
        self._is_processing = False
        self._paused = False
        self._silence_timer: Optional[asyncio.Task] = None
        self._silence_timeout = DEFAULT_SILENCE_TIMEOUT_SEC
        self._last_processed_message = ""  # Track last processed message to prevent duplicates
        self._last_processed_time: Optional[datetime] = None

        # Voice settings (configurable from frontend)
        self._interruption_threshold = 50  # 0-100, higher = harder to interrupt
        self._allow_interruptions = True

        # Echo detection state
        self._speaking_start_time: Optional[datetime] = None
        self._audio_energy_baseline = 0.0
        self._recent_audio_energies: List[float] = []
        self._echo_detection_enabled = False  # Disabled by default - too aggressive and breaks TTS

        # Interruption state
        self._interrupted = False
        self._interruption_cooldown = False  # Prevent multiple interruptions in quick succession
        self._interrupted_agent: Optional[Dict] = None  # Track which agent was interrupted
        self._current_agent: Optional[Dict] = None  # Currently speaking/processing agent

        # Audio playback completion tracking
        self._playback_complete_events: Dict[str, asyncio.Event] = {}  # agent_id -> Event

        # Client connection state (set by consumer)
        self.client_disconnected = False

        # Pipelined generation for OpenAI TTS (look-ahead by one agent)
        # Stores pre-generated response while previous agent's audio plays
        self._pregenerated_response: Optional[Dict] = None  # {agent, text, audio_b64}
        self._pregeneration_task: Optional[asyncio.Task] = None

    async def start_session(self) -> None:
        """Initialize all services and start the session."""
        logger.info(f"Starting voice room session: {self.room_id}")

        self.status = RoomStatus.CONNECTING
        self.started_at = datetime.utcnow()
        await self._send_state_update()

        try:
            # Initialize LLM client with user for API key resolution
            self.llm_client = LLMRouter(user=self._user)
            await self.llm_client.initialize()

            # Initialize TTS client (multi-provider: supports both ElevenLabs and OpenAI)
            self.tts_client = MultiProviderTTSClient(
                on_audio=self._on_tts_audio,
                on_error=self._on_tts_error,
                on_alignment=self._on_tts_alignment,
                user=self._user,
                session_id=self.room_id,
            )
            await self.tts_client.initialize()

            # Import voice utils for validation
            from voice_rooms.voice_utils import (
                is_valid_voice_for_provider,
                get_default_voice,
            )

            # Connect TTS for each agent's voice with their custom settings
            for i, agent in enumerate(self.agents_by_order):
                voice_id = agent.get("voice_id")
                if voice_id:
                    # Build voice settings from agent config
                    agent_voice_settings = agent.get("voice_settings", {})
                    voice_settings = None

                    # Get TTS model from agent settings (with fallback to global setting)
                    tts_model = agent_voice_settings.get("tts_model", settings.ELEVENLABS_MODEL)

                    # Detect provider
                    provider = agent_voice_settings.get("tts_provider") or detect_tts_provider(tts_model, voice_id)

                    # Validate voice for provider - use default if invalid
                    if not is_valid_voice_for_provider(voice_id, provider):
                        default_voice = get_default_voice(provider, index=i)
                        logger.warning(
                            f"Agent {agent.get('display_name')}: Invalid voice '{voice_id}' for provider '{provider}', "
                            f"using default '{default_voice['voice_name']}'"
                        )
                        voice_id = default_voice["voice_id"]
                        agent["voice_id"] = voice_id
                        agent["voice_name"] = default_voice["voice_name"]

                    logger.info(f"Agent {agent.get('display_name')}: voice={voice_id}, model={tts_model}, provider={provider}")

                    # Build provider-specific voice settings
                    if provider == "elevenlabs" and agent_voice_settings:
                        voice_settings = VoiceSettings(
                            stability=agent_voice_settings.get("stability", 0.5),
                            similarity_boost=agent_voice_settings.get("similarity_boost", 0.8),
                            style=agent_voice_settings.get("style", 0.3),
                            use_speaker_boost=agent_voice_settings.get("use_speaker_boost", True),
                        )
                        logger.info(f"Agent {agent.get('display_name')} ElevenLabs settings: stability={voice_settings.stability}, similarity={voice_settings.similarity_boost}, style={voice_settings.style}")

                        # eleven_v3 doesn't support WebSocket streaming - use fallback
                        WEBSOCKET_INCOMPATIBLE_MODELS = ['eleven_v3']
                        if tts_model in WEBSOCKET_INCOMPATIBLE_MODELS:
                            logger.warning(f"TTS model {tts_model} doesn't support WebSocket, using {settings.ELEVENLABS_MODEL} instead")
                            tts_model = settings.ELEVENLABS_MODEL
                    elif provider == "openai" and agent_voice_settings:
                        # OpenAI only supports speed setting
                        speed = agent_voice_settings.get("speed", 1.0)
                        voice_settings = {"speed": speed}
                        logger.info(f"Agent {agent.get('display_name')} OpenAI settings: speed={speed}")

                    success = await self.tts_client.connect_voice(voice_id, voice_settings, tts_model)
                    if not success:
                        logger.warning(f"Failed to connect voice for agent {agent.get('display_name')}")

            # Initialize STT client
            self.stt_client = DeepgramSTTClient(
                on_transcript=self._on_transcript,
                on_speech_start=self._on_speech_start,
                on_speech_end=self._on_speech_end,
                on_utterance_end=self._on_utterance_end,
                on_error=self._on_stt_error,
                user=self._user,
                session_id=self.room_id,
            )

            # Connect STT
            success = await self.stt_client.connect(self.language)
            if not success:
                raise Exception("Failed to connect to speech recognition")

            # Ready for user input
            self.status = RoomStatus.IDLE
            await self._send_state_update()

            # Signal user's turn
            await self.send_event({"type": "turn", "speaker": "user"})

            logger.info(f"Voice room session started: {self.room_id}")

        except Exception as e:
            logger.error(f"Failed to start session: {e}")
            self.status = RoomStatus.ERROR
            await self._send_state_update()
            await self.send_event({
                "type": "error",
                "code": "SESSION_START_FAILED",
                "message": str(e),
                "recoverable": False,
            })
            raise

    async def cleanup(self) -> None:
        """Cleanup all resources."""
        logger.info(f"Cleaning up voice room session: {self.room_id}")

        self.status = RoomStatus.ENDED
        self._cancel_silence_timer()

        if self.stt_client:
            await self.stt_client.close()

        if self.tts_client:
            await self.tts_client.cleanup()

        if self.llm_client:
            await self.llm_client.cleanup()

        logger.info(f"Voice room session ended: {self.room_id}")

    async def handle_audio_chunk(self, audio_data: bytes) -> None:
        """Handle incoming audio from the user."""
        if self._paused:
            logger.debug("Audio chunk dropped: session paused")
            return

        # Echo detection: when AI is speaking, check if audio is likely echo vs user interruption
        # NOTE: Echo detection is disabled by default because it's too aggressive and drops legitimate audio
        if self.status == RoomStatus.SPEAKING and self._echo_detection_enabled:
            if not self._allow_interruptions:
                logger.debug("Audio chunk dropped: interruptions disabled during AI speech")
                return

            # Calculate audio energy (simple RMS approximation)
            energy = self._calculate_audio_energy(audio_data)
            self._recent_audio_energies.append(energy)

            # Keep only last 10 samples for baseline
            if len(self._recent_audio_energies) > 10:
                self._recent_audio_energies.pop(0)

            # Update baseline when not speaking (first few samples)
            if len(self._recent_audio_energies) <= 3:
                self._audio_energy_baseline = sum(self._recent_audio_energies) / len(self._recent_audio_energies)

            # Interruption threshold: higher = need more energy to interrupt
            # At 0%: any audio passes through
            # At 100%: need 5x baseline energy to interrupt
            threshold_multiplier = 1 + (self._interruption_threshold / 100) * 4
            energy_threshold = self._audio_energy_baseline * threshold_multiplier

            if energy < energy_threshold:
                logger.debug(f"Audio chunk dropped: likely echo (energy={energy:.2f}, threshold={energy_threshold:.2f})")
                return
            else:
                # User interruption detected - stop the AI
                if not self._interruption_cooldown:
                    logger.info(f"User interruption detected! Stopping AI (energy={energy:.2f}, threshold={energy_threshold:.2f})")
                    await self._handle_interruption()

        if self.stt_client:
            # Always call send_audio - it handles reconnection internally
            await self.stt_client.send_audio(audio_data)
            # Log periodically during agent speech to verify audio is flowing
            if self.status == RoomStatus.SPEAKING:
                if not hasattr(self, '_audio_chunk_count_during_speech'):
                    self._audio_chunk_count_during_speech = 0
                self._audio_chunk_count_during_speech += 1
                if self._audio_chunk_count_during_speech % 50 == 0:  # Log every ~1 second (assuming 50 chunks/sec)
                    logger.info(f"Audio flowing to Deepgram during agent speech: {self._audio_chunk_count_during_speech} chunks sent")
        else:
            logger.warning("STT client not initialized")

    def _calculate_audio_energy(self, audio_data: bytes) -> float:
        """Calculate RMS energy of audio data."""
        if len(audio_data) < 2:
            return 0.0

        # Simple energy calculation - sum of squared samples
        # This is a rough approximation since we're dealing with encoded audio
        total = sum(b * b for b in audio_data)
        return (total / len(audio_data)) ** 0.5

    async def _handle_interruption(self) -> None:
        """Handle user interrupting the AI."""
        self._interrupted = True
        self._interruption_cooldown = True

        # Clear any accumulated transcript to prevent double processing
        # The transcript will be re-accumulated after interruption
        self._current_transcript = ""
        self._last_interim_transcript = ""

        # Save the interrupted agent so we can resume with them
        if self._current_agent:
            self._interrupted_agent = self._current_agent
            logger.info(f"Handling user interruption - stopping agent {self._interrupted_agent.get('display_name')}")
        else:
            logger.info("Handling user interruption - stopping AI response")

        # Clear any pending playback events (so orchestrator doesn't wait)
        for agent_id, event in list(self._playback_complete_events.items()):
            event.set()  # Unblock any waiting
        self._playback_complete_events.clear()

        # Stop TTS generation for all connected voices (mutes audio)
        if self.tts_client:
            for agent in self.agents_by_order:
                voice_id = agent.get("voice_id")
                if voice_id and self.tts_client.is_voice_connected(voice_id):
                    await self.tts_client.stop_generation(voice_id)

        # Notify frontend to stop audio playback FIRST (before state update)
        await self.send_event({
            "type": "stop_audio",  # Tell frontend to clear audio queue
        })
        await self.send_event({
            "type": "interrupted",
            "message": "User interrupted the AI",
            "interrupted_agent": self._interrupted_agent.get("display_name") if self._interrupted_agent else None,
        })

        # Update status to listening
        self.status = RoomStatus.LISTENING
        self.current_speaker = "user"
        await self._send_state_update()

        # Signal user's turn immediately so they can continue speaking
        await self.send_event({"type": "turn", "speaker": "user"})

        # Reset cooldown after a short delay
        asyncio.create_task(self._reset_interruption_cooldown())

    async def _reset_interruption_cooldown(self) -> None:
        """Reset the interruption cooldown after a delay."""
        await asyncio.sleep(INTERRUPTION_COOLDOWN_SEC)
        self._interruption_cooldown = False
        logger.debug("Interruption cooldown reset")

    async def handle_user_end_speaking(self) -> None:
        """Handle user signaling end of speech."""
        if self._current_transcript.strip():
            await self._process_user_message(self._current_transcript.strip())
            self._current_transcript = ""

    async def pause(self) -> None:
        """Pause the session."""
        self._paused = True
        self.status = RoomStatus.PAUSED
        await self._send_state_update()

    async def resume(self) -> None:
        """Resume the session."""
        self._paused = False
        self.status = RoomStatus.IDLE if not self._is_processing else RoomStatus.PROCESSING
        await self._send_state_update()
        await self.send_event({"type": "turn", "speaker": "user"})

    async def skip_current_agent(self) -> None:
        """Skip the current agent's response."""
        logger.info(f"Skip requested for session: {self.room_id}")

    async def update_settings(
        self,
        silence_timeout: float = 2.0,
        interruption_threshold: int = 50,
        allow_interruptions: bool = True,
        echo_detection_enabled: bool = False,
    ) -> None:
        """
        Update voice processing settings.

        Args:
            silence_timeout: Seconds to wait after speech before processing (1-5)
            interruption_threshold: 0-100, higher = harder to interrupt AI
            allow_interruptions: Whether user can interrupt AI speech
            echo_detection_enabled: Whether to enable echo detection (can be aggressive)
        """
        self._silence_timeout = max(MIN_SILENCE_TIMEOUT_SEC, min(MAX_SILENCE_TIMEOUT_SEC, silence_timeout))
        self._interruption_threshold = max(0, min(100, interruption_threshold))
        self._allow_interruptions = allow_interruptions
        self._echo_detection_enabled = echo_detection_enabled

        logger.info(
            f"Voice settings updated: silence_timeout={self._silence_timeout}s, "
            f"interruption_threshold={self._interruption_threshold}%, "
            f"allow_interruptions={self._allow_interruptions}, "
            f"echo_detection={self._echo_detection_enabled}"
        )

    async def handle_audio_playback_complete(self, agent_id: str) -> None:
        """
        Handle notification from client that audio playback finished for an agent.
        This allows the orchestrator to proceed to the next agent.
        """
        logger.info(f"Received audio playback complete signal for agent: {agent_id}")
        if agent_id in self._playback_complete_events:
            self._playback_complete_events[agent_id].set()
        else:
            logger.warning(f"No pending playback completion event for agent: {agent_id}")

    async def handle_user_interrupt(self) -> None:
        """
        Handle user interrupt signal from client-side VAD.
        This is a backup for when Deepgram's VAD doesn't detect user speech
        (e.g., when the mic picks up AI audio output).

        Note: We trust the client - if it sends an interrupt, audio is still playing.
        The backend status may already be IDLE/LISTENING if TTS generation finished
        before audio playback completed on the client.
        """
        # Allow interrupts during SPEAKING or PROCESSING (audio may still be playing)
        # Also allow during IDLE/LISTENING since client knows better if audio is playing
        if self.status == RoomStatus.ENDED:
            logger.debug("Ignoring user_interrupt: session ended")
            return

        if self._interruption_cooldown:
            logger.debug("Ignoring user_interrupt: in cooldown period")
            return

        if not self._allow_interruptions:
            logger.debug("Ignoring user_interrupt: interruptions disabled")
            return

        # If we're already listening and not processing, just clear any pending audio
        if self.status in (RoomStatus.IDLE, RoomStatus.LISTENING) and not self._is_processing:
            logger.info("User interrupt during playback (backend already idle) - sending stop_audio")
            await self.send_event({"type": "stop_audio"})
            return

        logger.info("Processing user interrupt from client-side VAD")
        await self._handle_interruption()

    # STT Callbacks

    async def _on_transcript(
        self,
        text: str,
        is_final: bool,
        language: Optional[str],
        confidence: Optional[float],
    ) -> None:
        """Handle transcription results."""
        if language and not self.detected_language:
            self.detected_language = language

        # If we receive a transcript while AI is speaking, user is interrupting
        # This is more reliable than speech_start since echo cancellation may block that
        if self.status == RoomStatus.SPEAKING and text.strip():
            if self._speaking_start_time:
                speaking_duration = (datetime.utcnow() - self._speaking_start_time).total_seconds()
                if speaking_duration >= 0.5 and not self._interruption_cooldown:
                    logger.info(f"User interruption detected via transcript during SPEAKING: '{text[:30]}...'")
                    await self._handle_interruption()
                    # After interruption, status is LISTENING - continue to process transcript normally

        await self.send_event({
            "type": "transcript",
            "text": text,
            "is_final": is_final,
            "language": language,
            "confidence": confidence,
        })

        if is_final:
            self._current_transcript += " " + text
            self._last_interim_transcript = ""  # Clear interim on final
            self._cancel_silence_timer()
        else:
            # Track interim transcript for fallback processing
            self._last_interim_transcript = text
            # Start/restart silence timer when we get interim results
            self._start_silence_timer()

    async def _on_speech_start(self) -> None:
        """Handle speech start detected by Deepgram."""
        logger.info(f"Deepgram: Speech started (current status: {self.status})")
        if self.status == RoomStatus.IDLE:
            self.status = RoomStatus.LISTENING
            self.current_speaker = "user"
            await self._send_state_update()
        elif self.status == RoomStatus.SPEAKING:
            # User is speaking while AI is speaking - this is an interruption
            # The browser's echo cancellation should filter out AI voice from mic
            # Only interrupt if we've been speaking for at least 500ms to avoid false positives
            if self._speaking_start_time:
                speaking_duration = (datetime.utcnow() - self._speaking_start_time).total_seconds()
                logger.info(f"Speech detected during SPEAKING (duration: {speaking_duration:.1f}s, cooldown: {self._interruption_cooldown})")
                if speaking_duration >= 0.5 and not self._interruption_cooldown:
                    logger.info(f"User interruption detected via Deepgram speech_start (AI speaking for {speaking_duration:.1f}s)")
                    await self._handle_interruption()
                else:
                    logger.info(f"Ignoring speech_start: speaking_duration={speaking_duration:.1f}s < 0.5s or cooldown={self._interruption_cooldown}")

    async def _on_speech_end(self) -> None:
        """Handle natural speech end."""
        pass

    async def _on_utterance_end(self) -> None:
        """Handle end of utterance - process the message automatically."""
        logger.info(f"Utterance end detected. Current transcript: '{self._current_transcript[:50]}...' (processing={self._is_processing})")
        if self._current_transcript.strip() and not self._is_processing:
            logger.info("Processing user message from utterance end...")
            await self._process_user_message(self._current_transcript.strip())
            self._current_transcript = ""
        else:
            logger.debug(f"Skipping utterance end: transcript='{self._current_transcript}', is_processing={self._is_processing}")

    async def _on_stt_error(self, error: str) -> None:
        """Handle STT errors."""
        error_lower = error.lower()

        # Don't report connection closure errors to client - auto-reconnect will handle them
        # These are normal occurrences due to timeouts, ping/pong failures, etc.
        if any(phrase in error_lower for phrase in [
            'connection closed',
            "'nonetype'",
            '_resume_reading',
            'timeout',
            'connection lost',
        ]):
            logger.warning(f"STT connection issue (will auto-reconnect): {error}")
            return

        # Only report unexpected errors to the client
        logger.error(f"STT error: {error}")
        await self.send_event({
            "type": "error",
            "code": "STT_ERROR",
            "message": error,
            "recoverable": True,
        })

    def _start_silence_timer(self) -> None:
        """Start or restart the silence timer for fallback processing."""
        self._cancel_silence_timer()
        self._silence_timer = asyncio.create_task(self._on_silence_timeout())

    def _cancel_silence_timer(self) -> None:
        """Cancel the silence timer."""
        if self._silence_timer:
            self._silence_timer.cancel()
            self._silence_timer = None

    async def _on_silence_timeout(self) -> None:
        """Fallback: process message if silence detected after interim results."""
        try:
            await asyncio.sleep(self._silence_timeout)

            # If we have interim transcript but no final was received, use it
            if self._last_interim_transcript and not self._is_processing:
                logger.info(f"Silence timeout - processing interim transcript: '{self._last_interim_transcript[:50]}...'")
                # Add the interim as if it was final
                self._current_transcript += " " + self._last_interim_transcript
                self._last_interim_transcript = ""

                if self._current_transcript.strip():
                    await self._process_user_message(self._current_transcript.strip())
                    self._current_transcript = ""
        except asyncio.CancelledError:
            pass  # Timer was cancelled, that's fine

    # TTS Callbacks

    async def _on_tts_audio(self, voice_id: str, audio_base64: str, sequence: int) -> None:
        """Handle TTS audio chunks."""
        # Skip sending audio if interrupted
        if self._interrupted:
            logger.debug("Skipping TTS audio - user interrupted")
            return

        # Use current agent instead of looking up by voice_id
        # Voice ID lookup fails when multiple agents share the same voice (e.g., OpenAI voices)
        agent_id = self._current_agent["id"] if self._current_agent else None
        agent = self._current_agent

        if not agent_id:
            # Fallback to voice_id lookup if no current agent set
            for a in self.agents_by_order:
                if a.get("voice_id") == voice_id:
                    agent_id = a["id"]
                    agent = a
                    break

        if agent_id:
            # Determine audio format based on provider
            # ElevenLabs WebSocket streaming uses PCM, OpenAI uses MP3
            provider = self._get_agent_tts_provider(agent) if agent else "elevenlabs"
            audio_format = "pcm_24000" if provider == "elevenlabs" else "mp3"

            await self.send_event({
                "type": "agent_audio",
                "agent_id": agent_id,
                "data": audio_base64,
                "sequence": sequence,
                "format": audio_format,
            })

    async def _on_tts_error(self, voice_id: str, error: str) -> None:
        """Handle TTS errors."""
        logger.error(f"TTS error for voice {voice_id}: {error}")
        await self.send_event({
            "type": "error",
            "code": "TTS_ERROR",
            "message": error,
            "recoverable": True,
        })

    async def _on_tts_alignment(self, voice_id: str, alignment_data: dict) -> None:
        """Handle TTS word alignment data for live transcript sync."""
        # Skip if interrupted
        if self._interrupted:
            return

        # Get current agent ID
        agent_id = self._current_agent["id"] if self._current_agent else None
        if not agent_id:
            # Fallback to voice_id lookup
            for agent in self.agents_by_order:
                if agent.get("voice_id") == voice_id:
                    agent_id = agent["id"]
                    break

        if agent_id:
            # Convert character-level alignment to word-level for frontend
            chars = alignment_data.get("chars", [])
            start_times = alignment_data.get("charStartTimesMs", [])
            durations = alignment_data.get("charDurationsMs", [])

            # Build text from chars and calculate word boundaries
            text = "".join(chars)
            words = []
            word_start = 0
            word_start_time = start_times[0] if start_times else 0

            for i, char in enumerate(chars):
                if char in " \n\t" or i == len(chars) - 1:
                    # End of word
                    end_idx = i + 1 if i == len(chars) - 1 and char not in " \n\t" else i
                    word = "".join(chars[word_start:end_idx])
                    if word.strip():
                        word_end_time = start_times[i] + durations[i] if i < len(start_times) else word_start_time
                        words.append({
                            "word": word,
                            "startMs": word_start_time,
                            "endMs": word_end_time,
                        })
                    word_start = i + 1
                    if i + 1 < len(start_times):
                        word_start_time = start_times[i + 1]

            event = {
                "type": "alignment",
                "agent_id": agent_id,
                "text": text,
                "words": words,
            }
            # Pass through estimated flag if present (OpenAI has estimated timing)
            if alignment_data.get("estimated"):
                event["estimated"] = True
            await self.send_event(event)

    def _estimate_word_timing_for_lines(
        self, text: str, audio_b64: Optional[str] = None
    ) -> list:
        """
        Estimate word timing for line-based transitions (OpenAI pipeline).

        Uses MP3 file size to estimate total duration, then distributes
        timing across words proportionally by character count.
        Accounts for pauses after punctuation.

        Args:
            text: The text being synthesized
            audio_b64: Base64-encoded MP3 audio (for duration estimation)

        Returns:
            List of word timing dicts with word, startMs, endMs
        """
        import base64

        text_words = [w.strip() for w in text.split() if w.strip()]
        if not text_words:
            return []

        # Estimate audio duration from MP3 file size
        # OpenAI TTS uses variable bitrate, ~165kbps average for speech
        OPENAI_MP3_BITRATE = 165000
        if audio_b64:
            try:
                audio_bytes = base64.b64decode(audio_b64)
                audio_duration_ms = (len(audio_bytes) * 8 * 1000) / OPENAI_MP3_BITRATE
            except Exception:
                audio_duration_ms = len(text_words) * 300  # ~200 WPM fallback
        else:
            audio_duration_ms = len(text_words) * 300

        # No speed adjustment - bitrate tuned for accuracy
        # audio_duration_ms *= 1.0

        # Calculate weight for each word (char count + punctuation pause)
        # Punctuation causes TTS to pause significantly
        def get_word_weight(word: str) -> float:
            weight = len(word)
            # Add substantial pause weight for trailing punctuation
            if word.endswith('...'):
                weight += 18  # Very long pause for ellipsis
            elif word.endswith(('.', '!', '?')):
                weight += 15  # Long pause for sentence end
            elif word.endswith(';'):
                weight += 10  # Longer pause for semicolon
            elif word.endswith((',', ':')):
                weight += 5  # Medium pause for clause break
            elif word.endswith(('-', '—')):
                weight += 6  # Pause for dashes
            return weight

        word_weights = [get_word_weight(w) for w in text_words]
        total_weight = sum(word_weights)
        if total_weight == 0:
            return []

        # Debug: log punctuation weight effects
        punctuated_words = [(w, wt) for w, wt in zip(text_words, word_weights) if wt > len(w)]
        if punctuated_words:
            logger.info(f"[ALIGNMENT] Punctuation weights: {punctuated_words[:5]}")

        words = []
        current_time = 0

        for word, weight in zip(text_words, word_weights):
            word_duration = (weight / total_weight) * audio_duration_ms
            words.append({
                "word": word,
                "startMs": int(current_time),
                "endMs": int(current_time + word_duration),
            })
            current_time += word_duration

        # Log some example durations to verify punctuation works
        sample_durations = [(w["word"], w["endMs"] - w["startMs"]) for w in words[:10]]
        logger.info(f"[ALIGNMENT] Total duration: {audio_duration_ms:.0f}ms, words: {len(words)}, total_weight: {total_weight}")
        logger.info(f"[ALIGNMENT] Sample durations (word, ms): {sample_durations}")
        return words

    # Message Processing

    async def _process_user_message(self, text: str) -> None:
        """Process a complete user message and generate agent responses."""
        # Check for duplicate message (same text within 3 seconds)
        now = datetime.utcnow()
        if (self._last_processed_message == text.strip() and
            self._last_processed_time and
            (now - self._last_processed_time).total_seconds() < DUPLICATE_MESSAGE_COOLDOWN_SEC):
            logger.warning(f"Duplicate message detected, skipping: '{text[:30]}...'")
            return

        async with self._processing_lock:
            if self._is_processing:
                logger.debug(f"Already processing, skipping: '{text[:30]}...'")
                return
            self._is_processing = True
            self.status = RoomStatus.PROCESSING

        # Track this message to prevent duplicates
        self._last_processed_message = text.strip()
        self._last_processed_time = now

        # Reset interruption flag - user has finished speaking, ready for new conversation
        if self._interrupted:
            logger.info("Resetting interruption flag - user finished speaking")
            self._interrupted = False

        try:
            logger.info(f"Processing user message: {text[:50]}...")

            # Add user message to conversation
            user_message = {
                "role": "user",
                "content": text,
                "timestamp": datetime.utcnow().isoformat(),
            }
            self.conversation.append(user_message)

            # Persist to database
            if self.save_message:
                try:
                    await self.save_message({
                        "role": "user",
                        "content": text,
                    })
                except Exception as e:
                    logger.error(f"Failed to save user message: {e}")

            # Determine which agents to process
            # Priority: 1) Interrupted agent, 2) All agents (with redirect support)

            if self._interrupted_agent:
                # If an agent was interrupted, resume with that agent
                interrupted_agent_id = self._interrupted_agent.get("id")
                agents_to_process = []
                found_interrupted = False
                for agent in self.agents_by_order:
                    if agent["id"] == interrupted_agent_id:
                        found_interrupted = True
                    if found_interrupted:
                        agents_to_process.append(agent)
                logger.info(f"Resuming conversation with interrupted agent: {self._interrupted_agent.get('display_name')}")
                self._interrupted_agent = None  # Clear after determining agents
            else:
                agents_to_process = list(self.agents_by_order)

            # Process agents in continuous loop until user interrupts
            # Multi-agent: Agents keep talking between themselves indefinitely
            # Single-agent: Only respond once, then wait for user input
            round_number = 0
            redirect_to_user = False
            is_single_agent = len(self.agents_by_order) == 1
            consecutive_failed_rounds = 0
            MAX_CONSECUTIVE_FAILED_ROUNDS = 2  # Stop if 2 rounds with no valid responses
            while not (self._paused or self._interrupted or self.client_disconnected or redirect_to_user):
                round_number += 1
                logger.info(f"Starting agent conversation round {round_number}")

                # Reset for each round
                i = 0
                has_redirected = False
                processed_agent_ids = set()
                agents_with_valid_response = set()  # Track which agents produced valid responses

                # For subsequent rounds, process all agents
                if round_number > 1:
                    agents_to_process = list(self.agents_by_order)

                # Track pre-generated response for pipelining (OpenAI only)
                pregenerated_response: Optional[Dict] = None

                while i < len(agents_to_process):
                    if self._paused or self._interrupted or self.client_disconnected:
                        if self._interrupted:
                            logger.info("Skipping remaining agents due to user interruption")
                        elif self.client_disconnected:
                            logger.info("Skipping remaining agents due to client disconnection")
                        break

                    agent = agents_to_process[i]
                    agent_id = agent["id"]

                    # Skip if already processed in this round (can happen after redirect)
                    if agent_id in processed_agent_ids:
                        i += 1
                        continue

                    is_last_agent = (i == len(agents_to_process) - 1)
                    agent_provider = self._get_agent_tts_provider(agent)

                    # Determine next OpenAI agent for pipelining (if any)
                    next_openai_agent = None
                    next_idx = i + 1
                    if next_idx < len(agents_to_process):
                        candidate = agents_to_process[next_idx]
                        if (candidate["id"] not in processed_agent_ids and
                            self._get_agent_tts_provider(candidate) == "openai"):
                            next_openai_agent = candidate

                    # Check if we have a pre-generated response for this agent
                    if (pregenerated_response and
                        pregenerated_response["agent"]["id"] == agent_id):
                        # Use pre-generated response (OpenAI pipelining)
                        logger.info(f"[PIPELINE] Using pre-generated response for {agent.get('display_name')}")
                        pregen_for_release = pregenerated_response
                        redirect_target, pregenerated_response = await self._release_pregenerated_response(
                            pregen_for_release,
                            next_agent_to_pregenerate=next_openai_agent,
                            allow_next_redirect=not has_redirected,
                        )
                        # Pre-generated response is valid if it has content OR redirected
                        if pregen_for_release.get("full_text") or pregen_for_release.get("redirect_to"):
                            agents_with_valid_response.add(agent_id)
                    elif agent_provider == "openai":
                        # OpenAI agent without pre-generated response - generate now
                        # This happens for the first agent or after redirects
                        logger.info(f"[PIPELINE] Generating OpenAI response inline for {agent.get('display_name')}")
                        pregen = await self._pregenerate_openai_response(
                            agent, allow_redirect=not has_redirected
                        )
                        if pregen:
                            redirect_target, pregenerated_response = await self._release_pregenerated_response(
                                pregen,
                                next_agent_to_pregenerate=next_openai_agent,
                                allow_next_redirect=not has_redirected,
                            )
                            # Agent produced a valid response if it has content OR redirected
                            if pregen.get("full_text") or pregen.get("redirect_to"):
                                agents_with_valid_response.add(agent_id)
                            else:
                                logger.warning(f"Agent {agent.get('display_name')} produced empty response")
                        else:
                            redirect_target = None
                            pregenerated_response = None
                            logger.warning(f"Agent {agent.get('display_name')} failed to produce a response")
                    else:
                        # ElevenLabs agent - use existing streaming flow (no pipelining)
                        redirect_target = await self._generate_agent_response(
                            agent, is_last_agent=is_last_agent, allow_redirect=not has_redirected
                        )
                        # Clear any OpenAI pre-generated response since we're switching providers
                        pregenerated_response = None
                        # ElevenLabs agents always produce a response (errors are handled internally)
                        agents_with_valid_response.add(agent_id)

                    processed_agent_ids.add(agent_id)

                    if redirect_target:
                        # Check if redirecting to user
                        user_target = self.user_name if self.user_name else "User"
                        if redirect_target.lower() == user_target.lower():
                            logger.info(f"Agent redirected to user ({user_target}) - returning control")
                            # Signal user's turn and break out of agent loop
                            self.status = RoomStatus.IDLE
                            self.current_speaker = "user"
                            await self._send_state_update()
                            await self.send_event({"type": "turn", "speaker": "user"})
                            # Set flag to break out of both loops
                            redirect_to_user = True
                            break
                        else:
                            # Agent chose to redirect to another agent - find target and process them next
                            target_agent = next(
                                (a for a in self.agents_by_order if a.get("display_name", "").lower() == redirect_target.lower()),
                                None
                            )
                            if target_agent and target_agent["id"] not in processed_agent_ids:
                                logger.info(f"Redirecting to agent: {redirect_target}")
                                agents_to_process.insert(i + 1, target_agent)
                                has_redirected = True
                                # Clear any pre-generated response since redirect changes the flow
                                pregenerated_response = None
                            else:
                                logger.warning(f"Redirect target '{redirect_target}' not found or already processed")

                    i += 1

                # Check if we should continue to next round
                if self._paused or self._interrupted or self.client_disconnected:
                    break

                # Track consecutive rounds with no valid responses
                if not agents_with_valid_response:
                    consecutive_failed_rounds += 1
                    logger.warning(
                        f"Round {round_number} completed with no valid agent responses "
                        f"(consecutive failures: {consecutive_failed_rounds}/{MAX_CONSECUTIVE_FAILED_ROUNDS})"
                    )
                    if consecutive_failed_rounds >= MAX_CONSECUTIVE_FAILED_ROUNDS:
                        logger.error(
                            f"Stopping conversation: {consecutive_failed_rounds} consecutive rounds "
                            f"with no valid agent responses (all agents may be rate-limited)"
                        )
                        # Signal user's turn and break
                        self.status = RoomStatus.IDLE
                        self.current_speaker = "user"
                        await self._send_state_update()
                        await self.send_event({"type": "turn", "speaker": "user"})
                        await self.send_event({
                            "type": "error",
                            "code": "AGENTS_UNAVAILABLE",
                            "message": "All agents are temporarily unavailable. Please try again in a moment.",
                            "recoverable": True,
                        })
                        break
                else:
                    # Reset counter on successful round
                    consecutive_failed_rounds = 0

                # Single-agent rooms: break after first round, wait for user input
                if is_single_agent:
                    logger.info(f"Single agent room - round {round_number} complete, waiting for user input")
                    # Signal user's turn
                    self.status = RoomStatus.IDLE
                    self.current_speaker = "user"
                    await self._send_state_update()
                    await self.send_event({"type": "turn", "speaker": "user"})
                    break

                logger.info(f"Round {round_number} complete, starting next round...")

            # Only reach here when interrupted, disconnected, or single-agent completed
            if self._interrupted:
                logger.info("Agent conversation ended due to user interruption")
            elif self.client_disconnected:
                logger.info("Agent conversation ended due to client disconnection")
            elif is_single_agent:
                logger.info("Single agent conversation round complete")

        except Exception as e:
            logger.error(f"Error processing user message: {e}")
            await self.send_event({
                "type": "error",
                "code": "PROCESSING_ERROR",
                "message": str(e),
                "recoverable": True,
            })

        finally:
            self._is_processing = False
            # Reset interrupted flag - transcript is cleared in _handle_interruption
            # so new speech will be accumulated fresh
            if self._interrupted:
                self._interrupted = False

    async def _generate_agent_response(
        self, agent: Dict, is_last_agent: bool = False, allow_redirect: bool = True
    ) -> Optional[str]:
        """
        Generate and speak an agent's response.

        Args:
            agent: Agent configuration
            is_last_agent: Whether this is the last agent in the queue
            allow_redirect: Whether to allow this agent to redirect (False to prevent loops)

        Returns:
            None if response completed normally, or agent name to redirect to
        """
        agent_id = agent["id"]
        agent_name = agent.get("display_name", "Agent")
        voice_id = agent.get("voice_id")

        model_id = agent.get("model_id", settings.OPENROUTER_DEFAULT_MODEL)
        logger.info(f"Generating response for agent: {agent_name} (model: {model_id})")

        # Signal thinking
        self.status = RoomStatus.PROCESSING
        self.current_speaker = agent_id
        await self._send_state_update()

        await self.send_event({
            "type": "agent_state",
            "agent_id": agent_id,
            "agent_name": agent_name,
            "state": "thinking",
        })

        try:
            # Build messages for LLM
            messages = self._build_llm_messages(agent)

            # Build redirect tool if redirect is allowed (can redirect to other agents or user)
            other_agent_names = [
                a.get("display_name", "") for a in self.agents_by_order
                if a["id"] != agent_id
            ]
            tools = None
            if allow_redirect:
                tools = [build_agent_routing_tool(other_agent_names, self.user_name)]
                logger.debug(f"Agent {agent_name} has redirect tool for: {other_agent_names + [self.user_name or 'User']}")
            else:
                logger.debug(f"Agent {agent_name}: redirect disabled (already redirected to this agent)")

            # Signal speaking and reset echo detection baseline
            self.status = RoomStatus.SPEAKING
            self._speaking_start_time = datetime.utcnow()
            self._recent_audio_energies = []  # Reset for fresh baseline during speech
            self._interrupted = False  # Reset interruption flag
            self._current_agent = agent  # Track current agent for interruption handling
            self._audio_chunk_count_during_speech = 0  # Reset audio counter for logging
            await self._send_state_update()

            await self.send_event({
                "type": "agent_state",
                "agent_id": agent_id,
                "agent_name": agent_name,
                "state": "speaking",
            })

            # Stream LLM response and send to TTS
            full_response = ""
            text_buffer = ""
            buffer_threshold = 50
            redirect_to_agent = None

            async for chunk_data in self.llm_client.stream_completion(
                model=model_id,
                messages=messages,
                max_tokens=self.max_response_tokens,
                tools=tools,
                tool_choice="auto" if tools else None,
            ):
                # Check for tool calls (redirect)
                if "tool_call" in chunk_data:
                    tool_call = chunk_data["tool_call"]
                    logger.info(f"Agent {agent_name} made tool call: {tool_call}")
                    if tool_call.get("function", {}).get("name") == "redirect_to_agent":
                        args_str = tool_call.get("function", {}).get("arguments", "{}")
                        try:
                            args = json.loads(args_str)
                            redirect_to_agent = args.get("agent_name")
                            reason = args.get("reason", "")
                            logger.info(f"Agent {agent_name} REDIRECT via tool to {redirect_to_agent} (reason: {reason})")
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse tool call args: {e}, raw: {args_str}")
                    continue

                # Get content chunk
                chunk = chunk_data.get("content", "")
                # Check for pause, interruption, or disconnection
                if self._paused or self._interrupted or self.client_disconnected:
                    if self._interrupted:
                        logger.info(f"Agent {agent_name} response interrupted by user")
                    elif self.client_disconnected:
                        logger.info(f"Agent {agent_name} response stopped due to client disconnection")
                    break

                full_response += chunk
                text_buffer += chunk

                await self.send_event({
                    "type": "agent_text",
                    "agent_id": agent_id,
                    "text": chunk,
                    "is_final": False,
                })

                if len(text_buffer) >= buffer_threshold and voice_id:
                    # Filter out internal thinking before sending to TTS
                    logger.info(f"[TTS] Raw buffer ({len(text_buffer)} chars): {text_buffer[:200]}...")
                    filtered_text = filter_thinking_tags(text_buffer)
                    logger.info(f"[TTS] Filtered buffer ({len(filtered_text)} chars): {filtered_text[:200] if filtered_text else '(empty)'}...")
                    if filtered_text.strip():
                        await self.tts_client.send_text(voice_id, filtered_text)
                    else:
                        logger.info("[TTS] Skipping empty filtered text")
                    text_buffer = ""

            # If interrupted, skip all remaining processing for this agent
            if self._interrupted:
                logger.info(f"Agent {agent_name} was interrupted - skipping TTS, saving, etc.")
                # Send agent_state done to clear UI
                await self.send_event({
                    "type": "agent_state",
                    "agent_id": agent_id,
                    "agent_name": agent_name,
                    "state": "done",
                })
                return None

            # If agent chose to redirect, don't generate response
            if redirect_to_agent:
                logger.info(f"Agent {agent_name} chose to redirect message to {redirect_to_agent}")
                # Send agent_state done to clear UI
                await self.send_event({
                    "type": "agent_state",
                    "agent_id": agent_id,
                    "agent_name": agent_name,
                    "state": "done",
                })
                return redirect_to_agent

            # Send remaining text to TTS (filtered)
            if text_buffer and voice_id:
                logger.info(f"[TTS] Final raw buffer ({len(text_buffer)} chars): {text_buffer[:200]}...")
                filtered_text = filter_thinking_tags(text_buffer)
                logger.info(f"[TTS] Final filtered buffer ({len(filtered_text)} chars): {filtered_text[:200] if filtered_text else '(empty)'}...")
                if filtered_text.strip():
                    await self.tts_client.send_text(voice_id, filtered_text)
                else:
                    logger.info("[TTS] Skipping empty final filtered text")

            # Send final text IMMEDIATELY after LLM finishes - don't wait for audio
            # This clears the "typing..." indicator in the frontend right away
            await self.send_event({
                "type": "agent_text",
                "agent_id": agent_id,
                "agent_name": agent_name,
                "text": full_response,
                "is_final": True,
            })
            logger.info(f"Sent agent_text (is_final=True) for {agent_name}")

            # Create playback event BEFORE TTS wait - frontend may finish playback
            # before TTS generation completes (race condition fix)
            playback_event = None
            if voice_id and not self._interrupted and not self.client_disconnected:
                playback_event = asyncio.Event()
                self._playback_complete_events[agent_id] = playback_event

            # Flush TTS and wait for audio generation to complete
            if voice_id:
                await self.tts_client.flush(voice_id)
                # Wait for all audio chunks to be generated
                logger.info(f"Waiting for TTS generation to complete for agent {agent_name}")
                completed = await self.tts_client.wait_for_completion(voice_id, timeout=TTS_GENERATION_TIMEOUT_SEC)
                logger.info(f"TTS generation {'complete' if completed else 'TIMED OUT'} for agent {agent_name}")

                # Signal client that all audio has been sent for this agent
                # Client should wait for this before sending audio_playback_complete
                await self.send_event({
                    "type": "agent_audio_complete",
                    "agent_id": agent_id,
                })
                logger.info(f"Sent agent_audio_complete for {agent_name}")

                # Now wait for client to finish playing the audio (unless interrupted or disconnected)
                # Always wait for playback - in continuous loop mode, next round starts immediately
                if playback_event and not self._interrupted and not self.client_disconnected:
                    logger.info(f"Waiting for client audio playback to complete for agent {agent_name}")
                    try:
                        # Wait for playback (timeout matches TTS timeout)
                        wait_start = asyncio.get_event_loop().time()
                        while not playback_event.is_set() and not self.client_disconnected:
                            try:
                                await asyncio.wait_for(playback_event.wait(), timeout=PLAYBACK_CHECK_INTERVAL_SEC)
                            except asyncio.TimeoutError:
                                if asyncio.get_event_loop().time() - wait_start > PLAYBACK_WAIT_TIMEOUT_SEC:
                                    logger.warning(f"Client audio playback timed out for agent {agent_name}, proceeding anyway")
                                    break
                        if self.client_disconnected:
                            logger.info(f"Client disconnected, skipping remaining playback wait for agent {agent_name}")
                        elif playback_event.is_set():
                            logger.info(f"Client audio playback complete for agent {agent_name}")
                    finally:
                        # Clean up the event
                        self._playback_complete_events.pop(agent_id, None)

            # Add agent message to conversation
            agent_message = {
                "role": "assistant",
                "agent_id": agent_id,
                "agent_name": agent_name,
                "content": full_response,
                "timestamp": datetime.utcnow().isoformat(),
            }
            self.conversation.append(agent_message)
            logger.info(f"Agent {agent_name} message added to conversation ({len(full_response)} chars)")

            # Persist to database
            if self.save_message and full_response.strip():
                try:
                    await self.save_message({
                        "role": "assistant",
                        "agent_id": agent_id,
                        "content": full_response,
                        "model_id": agent.get("model_id"),
                    })
                except Exception as e:
                    logger.error(f"Failed to save agent message: {e}")

            # Signal done (agent_text with is_final was already sent before audio wait)
            await self.send_event({
                "type": "agent_state",
                "agent_id": agent_id,
                "agent_name": agent_name,
                "state": "done",
            })

            logger.info(f"Agent {agent_name} finished responding, moving to next agent")
            return None

        except Exception as e:
            logger.error(f"Error generating response for agent {agent_name}: {e}")
            await self.send_event({
                "type": "error",
                "code": "AGENT_ERROR",
                "message": f"Failed to generate response: {str(e)}",
                "recoverable": True,
                "details": {"agent_id": agent_id},
            })

    async def _pregenerate_openai_response(
        self, agent: Dict, allow_redirect: bool = True, send_thinking_state: bool = True
    ) -> Optional[Dict]:
        """
        Pre-generate an OpenAI agent's response (LLM + TTS) without sending to frontend.

        This is used for pipelining: generate next agent's content while current
        agent's audio is still playing, then release it when ready.

        Args:
            agent: Agent configuration
            allow_redirect: Whether to allow redirects
            send_thinking_state: Whether to send "thinking" state (False for background pre-gen)

        Returns:
            Dict with {agent, full_text, audio_b64, redirect_to} or None on error
        """
        agent_id = agent["id"]
        agent_name = agent.get("display_name", "Agent")
        voice_id = agent.get("voice_id")
        model_id = agent.get("model_id", settings.OPENROUTER_DEFAULT_MODEL)

        logger.info(f"[PIPELINE] Pre-generating response for agent: {agent_name} (model: {model_id})")

        # Send "thinking" state so frontend shows the thinking indicator
        # (only for inline generation, not background pre-generation)
        if send_thinking_state:
            self._current_agent = agent
            self.status = RoomStatus.PROCESSING
            await self._send_state_update()
            await self.send_event({
                "type": "agent_state",
                "agent_id": agent_id,
                "agent_name": agent_name,
                "state": "thinking",
            })

        try:
            # Build messages for LLM
            messages = self._build_llm_messages(agent)

            # Build redirect tool (can redirect to other agents or user)
            other_agent_names = [
                a.get("display_name", "") for a in self.agents_by_order
                if a["id"] != agent_id
            ]
            tools = None
            if allow_redirect:
                tools = [build_agent_routing_tool(other_agent_names, self.user_name)]

            # Generate LLM response (collect all text, don't stream to frontend)
            full_response = ""
            redirect_to_agent = None

            async for chunk_data in self.llm_client.stream_completion(
                model=model_id,
                messages=messages,
                max_tokens=self.max_response_tokens,
                tools=tools,
                tool_choice="auto" if tools else None,
            ):
                # Check for interruption during pre-generation
                if self._paused or self._interrupted or self.client_disconnected:
                    logger.info(f"[PIPELINE] Pre-generation cancelled for {agent_name}")
                    return None

                # Check for tool calls (redirect)
                if "tool_call" in chunk_data:
                    tool_call = chunk_data["tool_call"]
                    if tool_call.get("function", {}).get("name") == "redirect_to_agent":
                        args_str = tool_call.get("function", {}).get("arguments", "{}")
                        try:
                            args = json.loads(args_str)
                            redirect_to_agent = args.get("agent_name")
                            logger.info(f"[PIPELINE] Agent {agent_name} redirects to {redirect_to_agent}")
                        except json.JSONDecodeError:
                            pass
                    continue

                chunk = chunk_data.get("content", "")
                full_response += chunk

            # If redirect, return early (no TTS needed)
            if redirect_to_agent:
                return {
                    "agent": agent,
                    "full_text": "",
                    "audio_b64": None,
                    "redirect_to": redirect_to_agent,
                }

            # Filter thinking tags and generate TTS
            filtered_text = filter_thinking_tags(full_response)
            audio_b64 = None

            if voice_id and filtered_text.strip():
                logger.info(f"[PIPELINE] Generating TTS for {agent_name} ({len(filtered_text)} chars)")
                audio_b64 = await self.tts_client.generate_audio_direct(voice_id, filtered_text)
                if audio_b64:
                    logger.info(f"[PIPELINE] TTS complete for {agent_name}")
                else:
                    logger.warning(f"[PIPELINE] TTS failed for {agent_name}")

            return {
                "agent": agent,
                "full_text": full_response,
                "audio_b64": audio_b64,
                "redirect_to": None,
            }

        except Exception as e:
            logger.error(f"[PIPELINE] Pre-generation error for {agent_name}: {e}")
            return None

    async def _release_pregenerated_response(
        self,
        pregenerated: Dict,
        next_agent_to_pregenerate: Optional[Dict] = None,
        allow_next_redirect: bool = True,
    ) -> tuple[Optional[str], Optional[Dict]]:
        """
        Release a pre-generated response to the frontend and wait for playback.

        PIPELINING: If next_agent_to_pregenerate is provided, starts generating
        their response IN PARALLEL with the current audio playback wait.
        This overlaps LLM+TTS generation with audio playback for zero-gap transitions.

        Args:
            pregenerated: Dict from _pregenerate_openai_response
            next_agent_to_pregenerate: Next OpenAI agent to pre-generate (optional)
            allow_next_redirect: Whether next agent can redirect

        Returns:
            Tuple of (redirect_target, next_pregenerated_response)
        """
        agent = pregenerated["agent"]
        agent_id = agent["id"]
        agent_name = agent.get("display_name", "Agent")
        full_response = pregenerated["full_text"]
        audio_b64 = pregenerated["audio_b64"]
        redirect_to = pregenerated.get("redirect_to")

        # Handle redirect
        if redirect_to:
            logger.info(f"[PIPELINE] Releasing redirect from {agent_name} to {redirect_to}")
            await self.send_event({
                "type": "agent_state",
                "agent_id": agent_id,
                "agent_name": agent_name,
                "state": "done",
            })
            return redirect_to, None

        logger.info(f"[PIPELINE] Releasing pre-generated response for {agent_name}")

        # Set current agent for proper audio routing
        self._current_agent = agent
        self.status = RoomStatus.SPEAKING
        self._speaking_start_time = datetime.utcnow()
        await self._send_state_update()

        # Send speaking state
        await self.send_event({
            "type": "agent_state",
            "agent_id": agent_id,
            "agent_name": agent_name,
            "state": "speaking",
        })

        # Send full text immediately (no streaming for pre-generated)
        await self.send_event({
            "type": "agent_text",
            "agent_id": agent_id,
            "agent_name": agent_name,
            "text": full_response,
            "is_final": True,
        })

        # Create playback event and send audio
        playback_event = None
        if audio_b64 and not self._interrupted and not self.client_disconnected:
            playback_event = asyncio.Event()
            self._playback_complete_events[agent_id] = playback_event

            # Send alignment data for live transcript with estimated timing
            # OpenAI doesn't provide native word timing, so we estimate for line transitions
            # Frontend will show all words as spoken (no word-by-word highlighting)
            filtered_text = filter_thinking_tags(full_response)
            if filtered_text.strip():
                words = self._estimate_word_timing_for_lines(filtered_text, audio_b64)
                await self.send_event({
                    "type": "alignment",
                    "agent_id": agent_id,
                    "text": filtered_text,
                    "words": words,
                    "estimated": True,  # Flag for frontend to skip word highlighting
                })
                logger.info(f"[PIPELINE] Sent alignment for {agent_name} ({len(words)} words, estimated)")

            # Send audio directly (already base64 encoded)
            await self.send_event({
                "type": "agent_audio",
                "agent_id": agent_id,
                "data": audio_b64,
                "sequence": 0,
                "format": "mp3",
            })

            # Signal client that all audio has been sent for this agent
            # Client waits for this before sending audio_playback_complete
            await self.send_event({
                "type": "agent_audio_complete",
                "agent_id": agent_id,
            })
            logger.info(f"[PIPELINE] Sent agent_audio_complete for {agent_name}")

        # PIPELINING: Start pre-generating next agent DURING playback wait
        # Don't send "thinking" state yet - we'll show it when releasing
        pregen_task = None
        if (next_agent_to_pregenerate and
            not self._paused and not self._interrupted and not self.client_disconnected):
            next_name = next_agent_to_pregenerate.get("display_name", "Agent")
            logger.info(f"[PIPELINE] Starting pre-generation for {next_name} during {agent_name}'s playback")
            pregen_task = asyncio.create_task(
                self._pregenerate_openai_response(
                    next_agent_to_pregenerate,
                    allow_redirect=allow_next_redirect,
                    send_thinking_state=False,  # Don't show thinking during background pre-gen
                )
            )

        # Wait for playback to complete (while pre-generation runs in parallel)
        next_pregenerated = None
        if playback_event and not self._interrupted and not self.client_disconnected:
            logger.info(f"[PIPELINE] Waiting for playback to complete for {agent_name}")
            try:
                wait_start = asyncio.get_event_loop().time()
                while not playback_event.is_set() and not self.client_disconnected:
                    try:
                        await asyncio.wait_for(playback_event.wait(), timeout=PLAYBACK_CHECK_INTERVAL_SEC)
                    except asyncio.TimeoutError:
                        if asyncio.get_event_loop().time() - wait_start > PLAYBACK_WAIT_TIMEOUT_SEC:
                            logger.warning(f"[PIPELINE] Playback timeout for {agent_name}")
                            break
                if playback_event.is_set():
                    logger.info(f"[PIPELINE] Playback complete for {agent_name}")
            finally:
                self._playback_complete_events.pop(agent_id, None)

        # Get pre-generation result (should be done or nearly done by now)
        if pregen_task:
            try:
                next_pregenerated = await pregen_task
                if next_pregenerated:
                    logger.info(f"[PIPELINE] Pre-generation complete for {next_agent_to_pregenerate.get('display_name')}")
            except Exception as e:
                logger.error(f"[PIPELINE] Pre-generation task error: {e}")
                next_pregenerated = None

        # Add to conversation and persist
        agent_message = {
            "role": "assistant",
            "agent_id": agent_id,
            "agent_name": agent_name,
            "content": full_response,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.conversation.append(agent_message)

        if self.save_message and full_response.strip():
            try:
                await self.save_message({
                    "role": "assistant",
                    "agent_id": agent_id,
                    "content": full_response,
                    "model_id": agent.get("model_id"),
                })
            except Exception as e:
                logger.error(f"[PIPELINE] Failed to save message: {e}")

        # Signal done
        await self.send_event({
            "type": "agent_state",
            "agent_id": agent_id,
            "agent_name": agent_name,
            "state": "done",
        })

        logger.info(f"[PIPELINE] Agent {agent_name} finished")
        return None, next_pregenerated

    def _format_agent_name(self, agent: Dict) -> str:
        """Format agent name with model info."""
        name = agent.get("display_name", "Assistant")
        model_id = agent.get("model_id", "")
        # Extract model name from model_id (e.g., "anthropic/claude-3.5-sonnet" -> "claude-3.5-sonnet")
        model_name = model_id.split("/")[-1] if model_id else ""
        return f"{name} ({model_name})" if model_name else name

    def _is_tts_v3(self, agent: Dict) -> bool:
        """Check if the agent's TTS model supports v3 audio tags."""
        agent_voice_settings = agent.get("voice_settings", {})
        # Get agent's TTS model, falling back to global setting
        agent_model = agent_voice_settings.get("tts_model", settings.ELEVENLABS_MODEL)
        v3_models = getattr(settings, 'ELEVENLABS_V3_MODELS', ['eleven_v3', 'eleven_v3_flash'])
        return agent_model in v3_models

    def _get_agent_tts_provider(self, agent: Dict) -> str:
        """Get the TTS provider for an agent (openai or elevenlabs)."""
        voice_id = agent.get("voice_id", "")
        agent_voice_settings = agent.get("voice_settings", {})
        tts_model = agent_voice_settings.get("tts_model", settings.ELEVENLABS_MODEL)
        return detect_tts_provider(tts_model, voice_id)

    def _build_voice_system_prompt(self, agent: Dict) -> str:
        """Build a concise system prompt optimized for voice conversations."""
        agent_name = self._format_agent_name(agent)
        custom_prompt = agent.get("system_prompt", "").strip()

        # Get other agents in the room with their model names
        other_agents = [a for a in self.agents_by_order if a["id"] != agent["id"]]
        other_agent_names = [self._format_agent_name(a) for a in other_agents]

        # Concise voice instructions
        prompt = f"""You are {agent_name} in a live voice conversation. Your responses are read aloud via TTS.

STRICT RULES:
- Speak naturally, no markdown/emojis/lists/formatting
- NEVER use meta-commentary (no "Great question!", "Let me think...", "That's interesting!", "I'd be happy to...", "Certainly!", etc.)
- NEVER use stage directions like *rolls eyes*, *sighs*, *laughs*, (pauses), etc. - these get read aloud!
- Just answer directly without preamble
- Respond in the user's language unless asked otherwise"""

        # Add v3 TTS audio tag instructions if using Eleven v3
        if self._is_tts_v3(agent):
            prompt += """

EXPRESSIVE VOICE (TTS v3 only - use [brackets] not *asterisks*):
- ONLY these tags work: [laughs], [sighs], [chuckles], [whispers]
- Use ... for pauses, CAPS for emphasis
- Maximum one tag per response
- Example: "Well... [sighs] I suppose you're right."
- WRONG: *rolls eyes* or (sighs) - these get read aloud!"""


        # Add multi-agent context if applicable
        if other_agent_names:
            user_display = self.user_name if self.user_name else "the user"
            prompt += f"\n\nYou are in a panel discussion with: {', '.join(other_agent_names)} and {user_display}. {user_display.capitalize()} is an active participant - acknowledge their input, respond to their questions, and include them in the conversation. You can address other panelists by name, respond to their points, debate them, but ALWAYS remember {user_display} is part of the discussion too."
            if self.user_name:
                prompt += f" Address them as {self.user_name} when speaking to them directly."
            prompt += f"\n\nROUTING: Use redirect_to_agent when someone is explicitly mentioned by name (including {user_display}). For general statements or topics - respond yourself first, then others will follow."
        else:
            # Single agent - talking directly to user
            if self.user_name:
                prompt += f"\n\nYou are having a one-on-one conversation with {self.user_name}. Address them by name when appropriate."
            else:
                prompt += "\n\nYou are having a one-on-one conversation with the user. Respond directly to them."

        # Add room description/topic if provided
        if self.room_description:
            prompt += f"\n\nTOPIC/CONTEXT: {self.room_description}"

        # Add custom personality if provided
        if custom_prompt:
            prompt += f"\n\nYour role: {custom_prompt}"

        return prompt

    def _build_llm_messages(self, agent: Dict) -> List[Dict[str, str]]:
        """Build message history for an agent's LLM call."""
        messages = [{"role": "system", "content": self._build_voice_system_prompt(agent)}]

        for msg in self.conversation:
            if msg["role"] == "user":
                messages.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                if msg.get("agent_id") == agent["id"]:
                    messages.append({"role": "assistant", "content": msg["content"]})
                else:
                    other_agent = self.agents_by_id.get(msg.get("agent_id"), {})
                    other_name = other_agent.get("display_name", "Another AI")
                    messages.append({"role": "user", "content": f"[{other_name}]: {msg['content']}"})

        return messages

    async def _send_state_update(self) -> None:
        """Send room state update to client."""
        await self.send_event({
            "type": "room_state",
            "status": self.status,
            "current_speaker": self.current_speaker,
            "detected_language": self.detected_language,
            "message_count": len(self.conversation),
            "connected_at": self.started_at.isoformat() if self.started_at else None,
        })
