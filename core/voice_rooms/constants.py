"""
Voice Room Constants

Centralized configuration for timeouts, thresholds, and other magic numbers
used across voice room services.
"""

# =============================================================================
# Silence Detection
# =============================================================================
DEFAULT_SILENCE_TIMEOUT_SEC = 3.0  # Seconds of silence before processing speech
MIN_SILENCE_TIMEOUT_SEC = 1.0
MAX_SILENCE_TIMEOUT_SEC = 5.0
DUPLICATE_MESSAGE_COOLDOWN_SEC = 3.0  # Minimum time between processing same message

# =============================================================================
# Interruption Handling
# =============================================================================
INTERRUPTION_COOLDOWN_SEC = 1.0  # Cooldown after an interruption before allowing another

# =============================================================================
# TTS (Text-to-Speech)
# =============================================================================
TTS_GENERATION_TIMEOUT_SEC = 120.0  # Max time to wait for TTS generation
TTS_AUDIO_SILENCE_TIMEOUT_SEC = 3.0  # Silence duration to assume TTS complete
TTS_HTTP_TIMEOUT_SEC = 30.0  # HTTP request timeout for TTS API
TTS_WEBSOCKET_PING_INTERVAL_SEC = 20  # WebSocket ping interval
TTS_WEBSOCKET_PING_TIMEOUT_SEC = 30  # WebSocket ping timeout
TTS_KEEPALIVE_INTERVAL_SEC = 15.0  # Keepalive interval for TTS connections

# =============================================================================
# Audio Playback
# =============================================================================
PLAYBACK_WAIT_TIMEOUT_SEC = 120.0  # Max time to wait for client audio playback
PLAYBACK_CHECK_INTERVAL_SEC = 1.0  # Interval for checking playback completion

# =============================================================================
# Frontend-matching Constants (keep in sync with useVoiceRoomSocket.ts)
# =============================================================================
# Frontend uses: PLAYBACK_SAFETY_TIMEOUT = 120000 (ms) = 120 seconds
# Frontend uses: INTERRUPT_COOLDOWN_MS = 1500 (ms) = 1.5 seconds
# Frontend uses: INTERRUPT_THRESHOLD = 0.18

# =============================================================================
# Voice Room Sessions
# =============================================================================
# Statuses a VoiceRoomSession holds while a live voice conversation is in
# progress (i.e. everything short of "ended").
ACTIVE_SESSION_STATUSES = ["idle", "listening", "processing", "speaking", "paused"]

# =============================================================================
# AI Room Generation
# =============================================================================
ROOM_GENERATOR_MODEL = "anthropic/claude-haiku-4.5"

# Allowed models for voice rooms (fast & cheap models only)
# Used for both AI room generation and manual model selection
VOICE_ROOM_MODELS = [
    # OpenAI
    "openai/gpt-4o-mini",
    "openai/gpt-5-mini",
    # Anthropic (Haiku series)
    "anthropic/claude-3-haiku",
    "anthropic/claude-3.5-haiku",
    "anthropic/claude-3.5-haiku-20241022",
    "anthropic/claude-haiku-4.5",
    # Google
    "google/gemini-2.0-flash-lite-001",
    "google/gemini-2.5-flash-lite",
    "google/gemini-2.5-flash",
    "google/gemini-3-flash-preview",
]

# Agent color palette (consistent with frontend AGENT_COLOR_PRESETS)
AGENT_COLORS = [
    "#38bdf8",  # sky-400
    "#a78bfa",  # violet-400
    "#fb923c",  # orange-400
    "#f472b6",  # pink-400
    "#2dd4bf",  # teal-400
    "#facc15",  # yellow-400
    "#818cf8",  # indigo-400
    "#4ade80",  # green-400
]

# ElevenLabs voices with personality hints for AI matching
VOICE_PERSONALITIES = {
    "21m00Tcm4TlvDq8ikWAM": {"name": "Rachel", "personality": "calm, professional, warm female"},
    "AZnzlk1XvdvUeBnXmlld": {"name": "Domi", "personality": "strong, assertive female"},
    "EXAVITQu4vr4xnSDxMaL": {"name": "Bella", "personality": "soft, gentle, friendly female"},
    "ErXwobaYiN019PkySvjV": {"name": "Antoni", "personality": "warm, friendly, conversational male"},
    "MF3mGyEYCl7XYWbV9V6O": {"name": "Elli", "personality": "young, energetic, expressive female"},
    "TxGEqnHWrfWFTfGW9XjX": {"name": "Josh", "personality": "deep, authoritative, confident male"},
    "VR6AewLTigWG4xSOukaG": {"name": "Arnold", "personality": "strong, bold, commanding male"},
    "pNInz6obpgDQGcFmaJgB": {"name": "Adam", "personality": "deep, mature, professional male"},
}

# Default voice settings for generated agents
DEFAULT_AGENT_VOICE_SETTINGS = {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "speed": 1.0,
}
