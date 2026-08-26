import { useEffect } from 'react'
import type { VoiceRoom } from '@/types/voiceRoom'
import { AGENT_COLOR_PRESETS, DEFAULT_VOICE_ID, DEFAULT_VOICE_NAME, DEFAULT_VOICE_SETTINGS, createDefaultAgent, generateAgentId } from './constants'
import type { AgentFormData, RoomPreset, VoiceSettingsFormState } from './types'

export interface RoomFormFieldSetters {
  setName: (v: string) => void
  setDescription: (v: string) => void
  setUserName: (v: string) => void
  setLanguage: (v: string) => void
  setVoiceSettings: React.Dispatch<React.SetStateAction<VoiceSettingsFormState>>
  setSelectedProvider: (v: string) => void
  setAgents: React.Dispatch<React.SetStateAction<AgentFormData[]>>
  setMobileStep: (v: number) => void
}

/**
 * Populates the form when the modal opens for create/edit/preset, and backfills
 * preset agents with real recommended voices once they load — the "populate the
 * form from props" concern, kept out of the container so its effects read as one
 * cohesive unit instead of being interleaved with unrelated state.
 */
export function useRoomFormPopulation(
  isOpen: boolean,
  roomToEdit: VoiceRoom | null | undefined,
  preset: RoomPreset | null | undefined,
  defaultUserName: string,
  recommendedVoices: import('@/types/voiceRoom').VoiceInfo[],
  agents: AgentFormData[],
  resetVoiceValidation: () => void,
  setters: RoomFormFieldSetters,
) {
  const { setName, setDescription, setUserName, setLanguage, setVoiceSettings, setSelectedProvider, setAgents, setMobileStep } = setters

  // Populate form when editing or using preset
  useEffect(() => {
    // Reset validation refs when modal opens
    if (isOpen) {
      resetVoiceValidation()
    }

    if (isOpen && roomToEdit) {
      setName(roomToEdit.name)
      setDescription(roomToEdit.description || '')
      setUserName(roomToEdit.user_name || defaultUserName)
      setLanguage(roomToEdit.language || 'auto')
      // Get voice settings from first agent (room-level now), merge with defaults for any missing fields
      const firstAgentSettings = roomToEdit.agents?.[0]?.voice_settings
      setVoiceSettings({ ...DEFAULT_VOICE_SETTINGS, ...firstAgentSettings })

      // Set provider from saved settings
      const savedProvider = firstAgentSettings?.tts_provider
      if (savedProvider) {
        setSelectedProvider(savedProvider)
      }

      setAgents(
        roomToEdit.agents?.map((a, i) => ({
          id: generateAgentId(),
          display_name: a.display_name,
          model_id: a.model_id,
          system_prompt: a.system_prompt,
          voice_id: a.voice_id,
          voice_name: a.voice_name,
          order: a.order || i + 1,
          color: a.color,
        })) || [createDefaultAgent(1)]
      )
    } else if (isOpen && preset) {
      // Pre-fill from preset
      setName(preset.name)
      setDescription(preset.description)
      setUserName(defaultUserName)
      setLanguage('auto')
      setVoiceSettings({ ...DEFAULT_VOICE_SETTINGS })

      // Randomly assign unique voices from recommended voices
      const getRandomVoices = (count: number) => {
        if (recommendedVoices.length === 0) {
          // Fallback to default if voices not loaded yet
          return Array(count).fill({ voice_id: DEFAULT_VOICE_ID, voice_name: DEFAULT_VOICE_NAME })
        }
        // Shuffle and pick unique voices, cycling if needed
        const shuffled = [...recommendedVoices].sort(() => Math.random() - 0.5)
        return Array.from({ length: count }, (_, i) => {
          const voice = shuffled[i % shuffled.length]
          return { voice_id: voice.voice_id, voice_name: voice.name }
        })
      }

      const randomVoices = getRandomVoices(preset.agents.length)

      setAgents(
        preset.agents.map((a, i) => ({
          ...createDefaultAgent(i + 1),
          display_name: a.display_name,
          model_id: a.model_id,
          system_prompt: a.system_prompt,
          color: a.color || AGENT_COLOR_PRESETS[i % AGENT_COLOR_PRESETS.length],
          // Use preset voice if available (from AI generation), otherwise random
          voice_id: a.voice_id || randomVoices[i].voice_id,
          voice_name: a.voice_name || randomVoices[i].voice_name,
        }))
      )
    } else if (isOpen && !roomToEdit && !preset) {
      // Reset form for create mode
      setName('')
      setDescription('')
      setUserName(defaultUserName)
      setLanguage('auto')
      setVoiceSettings({ ...DEFAULT_VOICE_SETTINGS })
      setSelectedProvider('') // Will be set to default by the provider effect
      setAgents([createDefaultAgent(1)])
    }

    // Reset mobile step when modal opens
    if (isOpen) {
      setMobileStep(1)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, roomToEdit, preset, defaultUserName])

  // Update agent voices when recommendedVoices becomes available (for presets without AI-generated voices)
  useEffect(() => {
    if (isOpen && preset && recommendedVoices.length > 0) {
      // Check if agents still have the default voice (meaning voices weren't available when preset was applied)
      // But only if the preset didn't include voice selections (from AI generation)
      const presetHasVoices = preset.agents.some(a => a.voice_id)
      if (presetHasVoices) return // AI-generated presets have voices already

      const hasDefaultVoices = agents.every(a => a.voice_id === DEFAULT_VOICE_ID)
      if (hasDefaultVoices && agents.length === preset.agents.length) {
        // Assign random unique voices now that they're available
        const shuffled = [...recommendedVoices].sort(() => Math.random() - 0.5)
        setAgents(prev => prev.map((agent, i) => ({
          ...agent,
          voice_id: shuffled[i % shuffled.length].voice_id,
          voice_name: shuffled[i % shuffled.length].name,
        })))
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recommendedVoices.length, isOpen, preset])
}
