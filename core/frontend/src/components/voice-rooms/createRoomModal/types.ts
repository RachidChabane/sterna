import type { VoiceSettings } from '@/types/voiceRoom'

/** Preset configuration for quick room creation. */
export interface RoomPreset {
  name: string
  description: string
  agents: Array<{
    display_name: string
    model_id: string
    system_prompt: string
    color?: string
    voice_id?: string // Optional voice selection from AI generation
    voice_name?: string
  }>
}

export interface AgentFormData {
  id: string // Unique ID for drag-and-drop
  display_name: string
  model_id: string
  system_prompt: string
  voice_id: string
  voice_name: string
  order: number
  voice_settings?: VoiceSettings
  color?: string // Hex color for UI visualization
}

/**
 * Form-local voice settings state.
 * `tts_model` is a plain string here because model ids come dynamically from the
 * TTS models API ('' = not selected yet), while the TTSModel union in
 * types/voiceRoom.ts is a static snapshot of known models.
 */
export type VoiceSettingsFormState = Omit<VoiceSettings, 'tts_model'> & { tts_model: string }
