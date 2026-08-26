import type { AgentFormData, VoiceSettingsFormState } from './types'

/** Generate a unique ID for new agents. */
export const generateAgentId = () => `agent-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`

/** Premium color palette for agent presets. */
export const AGENT_COLOR_PRESETS = [
  '#38bdf8', // sky-400
  '#a78bfa', // violet-400
  '#fb923c', // orange-400
  '#f472b6', // pink-400
  '#2dd4bf', // teal-400
  '#facc15', // yellow-400
  '#818cf8', // indigo-400
  '#4ade80', // green-400
]

/**
 * Allowed models for voice rooms (fast & cheap models only).
 * Must be kept in sync with backend VOICE_ROOM_MODELS in voice_rooms/constants.py
 */
export const VOICE_ROOM_ALLOWED_MODELS = [
  // OpenAI
  'openai/gpt-4o-mini',
  'openai/gpt-5-mini',
  // Anthropic (Haiku series)
  'anthropic/claude-3-haiku',
  'anthropic/claude-3.5-haiku',
  'anthropic/claude-haiku-4.5',
  // Google
  'google/gemini-2.0-flash-lite-001',
  'google/gemini-2.5-flash-lite',
  'google/gemini-2.5-flash',
  'google/gemini-3-flash-preview',
]

export const DEFAULT_VOICE_SETTINGS: VoiceSettingsFormState = {
  tts_model: '', // Will be set from first available model
  stability: 0.5,
  similarity_boost: 0.8,
  style: 0.3,
  use_speaker_boost: true,
  speed: 1.0,
}

export const DEFAULT_VOICE_ID = '21m00Tcm4TlvDq8ikWAM'
export const DEFAULT_VOICE_NAME = 'Rachel'

export const createDefaultAgent = (order: number = 0): AgentFormData => ({
  id: generateAgentId(),
  display_name: '',
  model_id: '',
  system_prompt: '',
  voice_id: DEFAULT_VOICE_ID,
  voice_name: DEFAULT_VOICE_NAME,
  order,
})
