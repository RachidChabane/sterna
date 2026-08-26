import { useState } from 'react'
import { useToast } from '@/hooks/use-toast'
import useVoiceRoomStore from '@/store/voiceRoomStore'
import type { TTSModel, TTSProviderId, VoiceRoom, VoiceSettings } from '@/types/voiceRoom'
import { AGENT_COLOR_PRESETS, DEFAULT_VOICE_SETTINGS, createDefaultAgent, generateAgentId } from './constants'
import type { AgentFormData, VoiceSettingsFormState } from './types'

export interface RoomFormSnapshot {
  name: string
  description: string
  userName: string
  language: string
  agents: AgentFormData[]
  voiceSettings: VoiceSettingsFormState
  selectedProvider: string
  isEditMode: boolean
  roomToEdit: VoiceRoom | null | undefined
  defaultUserName: string
  aiDescription: string
}

export interface RoomFormResetSetters {
  setName: (v: string) => void
  setDescription: (v: string) => void
  setUserName: (v: string) => void
  setLanguage: (v: string) => void
  setVoiceSettings: React.Dispatch<React.SetStateAction<VoiceSettingsFormState>>
  setAgents: React.Dispatch<React.SetStateAction<AgentFormData[]>>
  setAiGenerateOpen: (v: boolean) => void
  setAiDescription: (v: string) => void
}

/**
 * AI-generation and final submission for the room form — validation, the
 * create/update API call, and the fill-from-AI-generated-config flow.
 */
export function useRoomSubmission(form: RoomFormSnapshot, setters: RoomFormResetSetters, onCreated: (room: VoiceRoom) => void) {
  const { toast } = useToast()
  const { createRoom, updateRoom, generateRoom, isGeneratingRoom } = useVoiceRoomStore()
  const [isCreating, setIsCreating] = useState(false)

  const { name, description, userName, language, agents, voiceSettings, selectedProvider, isEditMode, roomToEdit, defaultUserName, aiDescription } = form
  const { setName, setDescription, setUserName, setLanguage, setVoiceSettings, setAgents, setAiGenerateOpen, setAiDescription } = setters

  // Handle AI room generation
  const handleAIGenerate = async () => {
    if (!aiDescription.trim()) return

    // Pass the selected TTS provider so AI can choose appropriate voices
    const generated = await generateRoom(aiDescription.trim(), selectedProvider || undefined)
    if (generated) {
      // Fill the form with generated config
      setName(generated.name)
      setDescription(generated.description)
      // Set detected language from AI (e.g., "en", "fr", "es")
      if (generated.language && generated.language !== 'auto') {
        setLanguage(generated.language)
      }

      // Set agents from generated config
      setAgents(
        generated.agents.map((agent) => ({
          id: generateAgentId(),
          display_name: agent.display_name,
          model_id: agent.model_id,
          system_prompt: agent.system_prompt,
          voice_id: agent.voice_id,
          voice_name: agent.voice_name,
          order: agent.order,
          color: agent.color,
        }))
      )

      // Collapse the AI section and clear input
      setAiGenerateOpen(false)
      setAiDescription('')

      toast({
        title: 'Room generated',
        description: 'Review the configuration and make any adjustments before creating.',
      })
    }
  }

  const handleSubmit = async () => {
    if (!name.trim() || agents.some((a) => !a.display_name || !a.model_id || !a.system_prompt)) {
      return
    }

    // Check for duplicate display names (case-insensitive)
    const displayNames = agents.map((a) => a.display_name.trim().toLowerCase())
    const duplicates = displayNames.filter((n, index) => displayNames.indexOf(n) !== index)
    if (duplicates.length > 0) {
      toast({
        title: 'Duplicate agent names',
        description: `Each agent must have a unique name. Duplicates: ${[...new Set(duplicates)].join(', ')}`,
        variant: 'destructive',
      })
      return
    }

    setIsCreating(true)
    try {
      // Apply room-level voice settings to all agents.
      // tts_model is validated against the provider's model list in the effect
      // above; the API accepts any model id the TTS provider exposes, so assert
      // the static TTSModel union at this boundary.
      const agentVoiceSettings: VoiceSettings = {
        ...voiceSettings,
        tts_model: voiceSettings.tts_model as TTSModel,
        tts_provider: selectedProvider as TTSProviderId,
      }
      const buildAgent = (a: AgentFormData, index: number) => ({
        display_name: a.display_name,
        model_id: a.model_id,
        system_prompt: a.system_prompt,
        voice_id: a.voice_id,
        voice_name: a.voice_name,
        order: a.order,
        voice_settings: agentVoiceSettings,
        color: a.color || AGENT_COLOR_PRESETS[index % AGENT_COLOR_PRESETS.length],
      })
      const roomData = {
        name: name.trim(),
        description: description.trim() || undefined,
        user_name: userName.trim() || undefined,
        language,
      }

      let room: VoiceRoom | null = null
      if (isEditMode && roomToEdit) {
        room = await updateRoom(roomToEdit.id, {
          ...roomData,
          // Include IDs when editing to preserve agent references in messages
          agents: agents.map((a, index) => ({ ...buildAgent(a, index), id: a.id })),
        })
      } else {
        room = await createRoom({
          ...roomData,
          agents: agents.map((a, index) => buildAgent(a, index)),
        })
      }

      if (room) {
        onCreated(room)
        // Reset form
        setName('')
        setDescription('')
        setUserName(defaultUserName)
        setLanguage('auto')
        setVoiceSettings({ ...DEFAULT_VOICE_SETTINGS })
        setAgents([createDefaultAgent(1)])
      }
    } finally {
      setIsCreating(false)
    }
  }

  // Check if form is valid for submission
  const isFormValid = Boolean(name.trim()) && !agents.some((a) => !a.display_name || !a.model_id || !a.system_prompt)

  // Mobile step validation
  const canProceedFromStep = (step: number) => {
    if (step === 1) return name.trim() !== ''
    if (step === 2) return !agents.some((a) => !a.display_name || !a.model_id || !a.system_prompt)
    return true
  }

  return { isCreating, isGeneratingRoom, handleAIGenerate, handleSubmit, isFormValid, canProceedFromStep }
}
