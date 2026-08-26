/**
 * Voice Room types for multi-AI voice conversations
 */

/**
 * Room status states
 */
export type RoomStatus = 'idle' | 'listening' | 'processing' | 'speaking' | 'paused' | 'ended'

/**
 * TTS Provider types
 */
export type TTSProviderId = 'openai' | 'elevenlabs'

export interface TTSProvider {
  id: TTSProviderId
  name: string
  is_default: boolean
}

/**
 * Voice information (provider-agnostic)
 */
/** Language-specific voice preview info (ElevenLabs) */
interface VoiceLanguagePreview {
  language: string
  model_id: string
  accent?: string
  locale?: string
  preview_url: string
}

export interface VoiceInfo {
  voice_id: string
  name: string
  provider: TTSProviderId
  description?: string
  preview_url?: string
  category: 'premade' | 'cloned' | 'generated'
  labels?: Record<string, string>
  languages?: string[]
  is_recommended?: boolean
  /** ElevenLabs: List of TTS model IDs this voice is optimized for */
  high_quality_base_model_ids?: string[]
  /** ElevenLabs: Language-specific previews with locale info */
  verified_languages?: VoiceLanguagePreview[]
}

/**
 * TTS model options (provider-specific)
 */
// OpenAI models
type OpenAITTSModel = 'tts-1' | 'tts-1-hd'
// ElevenLabs models
type ElevenLabsTTSModel = 'eleven_v3' | 'eleven_turbo_v2_5' | 'eleven_flash_v2_5' | 'eleven_multilingual_v2'
// Combined type for backwards compatibility
export type TTSModel = OpenAITTSModel | ElevenLabsTTSModel

/**
 * TTS model info (provider-agnostic)
 */
export interface TTSModelInfo {
  model_id: string
  name: string
  provider: TTSProviderId
  description?: string
  can_use_style: boolean
  can_use_speaker_boost: boolean
  supports_streaming: boolean
  languages: TTSLanguage[]
}

/**
 * TTS voice settings for an agent (ElevenLabs voice rooms)
 */
export interface VoiceSettings {
  tts_provider?: TTSProviderId // TTS provider (openai or elevenlabs)
  tts_model: TTSModel      // TTS model to use
  stability: number        // 0-1, default 0.5 (ElevenLabs)
  similarity_boost: number // 0-1, default 0.8 (ElevenLabs)
  style: number           // 0-1, default 0.3 (ElevenLabs)
  use_speaker_boost: boolean // default true (ElevenLabs)
  speed: number           // 0.25-4.0, default 1.0
}

/**
 * Agent configuration within a voice room
 */
export interface VoiceAgent {
  id: string
  display_name: string
  model_id: string
  system_prompt: string
  voice_id: string
  voice_name: string
  order: number
  is_active?: boolean
  voice_settings?: VoiceSettings
  color?: string // Hex color for UI visualization (e.g., "#38bdf8")
}

/**
 * Voice room configuration
 */
export interface VoiceRoom {
  id: string
  name: string
  description?: string
  user_id: string
  user_name?: string // User's display name for agents to address them
  agents: VoiceAgent[]
  language: string
  max_response_tokens: number
  is_active?: boolean
  created_at: string
  updated_at: string
}

/**
 * Message in a voice room conversation
 */
export interface VoiceRoomMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  agent_id?: string
  agent_name?: string
  audio_duration_ms?: number
  created_at: string
}

/**
 * Voice room session state
 */
export interface VoiceRoomState {
  room_id: string
  status: RoomStatus
  current_speaker?: string
  conversation: VoiceRoomMessage[]
  detected_language?: string
}

/**
 * Create room request
 */
export interface CreateRoomRequest {
  name: string
  description?: string
  user_name?: string
  agents: Omit<VoiceAgent, 'id'>[]
  language?: string
  max_response_tokens?: number
}

/**
 * Update room request
 */
export interface UpdateRoomRequest {
  name?: string
  description?: string
  user_name?: string
  agents?: VoiceAgent[]
  language?: string
  max_response_tokens?: number
}

// WebSocket Event Types

/**
 * Client to server: Audio chunk
 */
interface AudioChunkEvent {
  type: 'audio_chunk'
  data: string  // base64 encoded
  sequence?: number
}

/**
 * Client to server: End speaking signal
 */
interface EndSpeakingEvent {
  type: 'end_speaking'
}

/**
 * Client to server: Control events
 */
interface ControlEvent {
  type: 'pause' | 'resume' | 'skip_agent' | 'end_session'
}

/**
 * Client to server: Voice settings update
 */
interface SettingsEvent {
  type: 'settings'
  silence_timeout: number  // seconds before processing (1-5)
  interruption_threshold: number  // 0-100, higher = harder to interrupt
  allow_interruptions: boolean
}

/**
 * Client to server: Audio playback finished for an agent
 */
interface AudioPlaybackCompleteEvent {
  type: 'audio_playback_complete'
  agent_id: string
}

/**
 * Client to server: User interrupt signal from client-side VAD
 */
interface UserInterruptEvent {
  type: 'user_interrupt'
}

/**
 * Server to client: Transcript from STT
 */
interface TranscriptEvent {
  type: 'transcript'
  text: string
  is_final: boolean
  confidence?: number
  speaker: 'user'
}

/**
 * Server to client: Agent state change
 */
interface AgentStateEvent {
  type: 'agent_state'
  agent_id: string
  agent_name: string
  state: 'thinking' | 'speaking' | 'done'
}

/**
 * Server to client: Agent text response (streaming)
 */
interface AgentTextEvent {
  type: 'agent_text'
  agent_id: string
  agent_name: string
  text: string
  is_final: boolean
}

/**
 * Server to client: Agent audio chunk
 */
interface AgentAudioEvent {
  type: 'agent_audio'
  agent_id: string
  data: string  // base64 encoded
  audio_data?: string  // legacy field for backwards compatibility
  sequence?: number
  format?: string  // audio format (e.g., 'mp3')
}

/**
 * Server to client: Turn notification
 */
interface TurnEvent {
  type: 'turn'
  speaker: 'user' | string  // 'user' or agent_id
  turn_number: number
}

/**
 * Server to client: Error event
 */
interface ErrorEvent {
  type: 'error'
  code: string
  message: string
  recoverable: boolean
}

/**
 * Server to client: Connection acknowledgment
 */
interface ConnectedEvent {
  type: 'connected'
  room_id: string
  session_id: string
  previous_messages?: number  // Number of messages from previous session
  agents?: Array<{
    id: string
    name: string
    model_id: string
    voice_id: string
    order: number
  }>
}

/**
 * Server to client: Session ended
 */
interface SessionEndedEvent {
  type: 'session_ended'
  reason: 'user_ended' | 'timeout' | 'error'
  summary?: {
    duration_ms: number
    messages: number
    detected_language?: string
  }
}

/**
 * Server to client: Stop audio playback
 */
interface StopAudioEvent {
  type: 'stop_audio'
}

/**
 * Server to client: User interrupted AI
 */
interface InterruptedEvent {
  type: 'interrupted'
  message: string
  interrupted_agent?: string
}

/**
 * Server to client: Room state update
 */
interface RoomStateEvent {
  type: 'room_state'
  status: RoomStatus
  current_speaker?: string
  detected_language?: string
  message_count: number
  connected_at?: string
}

/**
 * Server to client: Word-level alignment for live transcript sync
 */
interface AlignmentEvent {
  type: 'alignment'
  agent_id: string
  text: string
  words: Array<{
    word: string
    startMs: number
    endMs: number
  }>
  estimated?: boolean  // true for OpenAI (skip word highlighting, keep line animation)
}

/**
 * Server to client: All audio has been sent for an agent
 * Client should wait for this before sending audio_playback_complete
 */
interface AgentAudioCompleteEvent {
  type: 'agent_audio_complete'
  agent_id: string
}

/**
 * Union type of all server events
 */
export type ServerEvent =
  | TranscriptEvent
  | AgentStateEvent
  | AgentTextEvent
  | AgentAudioEvent
  | TurnEvent
  | ErrorEvent
  | ConnectedEvent
  | SessionEndedEvent
  | StopAudioEvent
  | InterruptedEvent
  | RoomStateEvent
  | AlignmentEvent
  | AgentAudioCompleteEvent

/**
 * Union type of all client events
 */
export type ClientEvent =
  | AudioChunkEvent
  | EndSpeakingEvent
  | ControlEvent
  | SettingsEvent
  | AudioPlaybackCompleteEvent
  | UserInterruptEvent

/**
 * Language info from ElevenLabs
 */
interface TTSLanguage {
  language_id: string
  name: string
  country_code: string
}

// TTSModelInfo is defined above (lines 62-71) - removed duplicate
