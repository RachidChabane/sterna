import { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import useModelStore from '@/store/modelStore'
import useVoiceRoomStore from '@/store/voiceRoomStore'
import { VOICE_ROOM_ALLOWED_MODELS } from './constants'
import type { AgentFormData, VoiceSettingsFormState } from './types'
import type { TTSProviderId } from '@/types/voiceRoom'

/**
 * Owns TTS provider selection, TTS model loading/validation, the allowed-model
 * catalog for voice-room agents, and the voice validation that keeps agents'
 * voice_id pointed at a voice the current provider actually offers — the
 * "TTS provider/model" concern.
 */
export function useTtsProviderModels(
  isOpen: boolean,
  setAgents: React.Dispatch<React.SetStateAction<AgentFormData[]>>,
  voiceSettings: VoiceSettingsFormState,
  setVoiceSettings: React.Dispatch<React.SetStateAction<VoiceSettingsFormState>>,
) {
  const { allModels, fetchAllModels, allModelsLoading, allModelsLoaded } = useModelStore()
  const {
    recommendedVoices,
    ttsModels,
    fetchTTSModels,
    ttsModelsLoaded,
    fetchRecommendedVoices,
    ttsProviders,
    fetchTTSProviders,
    ttsProvidersLoaded,
  } = useVoiceRoomStore()

  // Provider state - default to first available provider
  const [selectedProvider, setSelectedProvider] = useState<TTSProviderId | ''>('')

  // Refs for tracking validation state
  const prevProviderRef = useRef<string>('')
  const validatedVoicesRef = useRef<string>('') // Track last validated state to avoid loops

  /** Reset validation refs — called by the form-population effect when the modal opens. */
  const resetVoiceValidation = useCallback(() => {
    validatedVoicesRef.current = ''
    prevProviderRef.current = ''
  }, [])

  // Load providers and models when modal opens
  useEffect(() => {
    if (isOpen) {
      if (!allModelsLoaded && !allModelsLoading) {
        fetchAllModels()
      }
      if (!ttsProvidersLoaded) {
        fetchTTSProviders()
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

  // Helper to check if a model matches a provider
  const isModelForProvider = useCallback((modelId: string, providerId: string): boolean => {
    if (!modelId || !providerId) return false
    const modelLower = modelId.toLowerCase()
    const providerLower = providerId.toLowerCase()

    if (providerLower === 'openai') {
      return modelLower.startsWith('tts-')
    }
    if (providerLower === 'elevenlabs') {
      return modelLower.startsWith('eleven')
    }
    return modelLower.includes(providerLower)
  }, [])

  // Set default provider when providers load (only if not already set)
  useEffect(() => {
    if (ttsProviders.length === 0 || selectedProvider) return
    // Default to first provider
    setSelectedProvider(ttsProviders[0].id)
  }, [ttsProviders, selectedProvider])

  // Fetch models and voices when modal opens or provider changes
  useEffect(() => {
    if (!isOpen || !selectedProvider) return

    // Reset validation ref when provider changes
    if (prevProviderRef.current !== selectedProvider) {
      validatedVoicesRef.current = ''
      prevProviderRef.current = selectedProvider
    }

    fetchTTSModels(selectedProvider)
    fetchRecommendedVoices(selectedProvider)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, selectedProvider])

  // Validate and fix agent voices when voices load or provider changes
  // This handles: 1) provider change, 2) editing room with mismatched voices
  useEffect(() => {
    if (!selectedProvider || recommendedVoices.length === 0) return

    // Ensure voices are for the current provider (check first voice's provider)
    const voicesMatchProvider = recommendedVoices.some(v =>
      v.provider?.toLowerCase() === selectedProvider.toLowerCase()
    )
    if (!voicesMatchProvider) {
      // Voices are stale (from different provider), wait for correct ones
      return
    }

    // Create a key to track if we've already validated this combination
    const validationKey = `${selectedProvider}:${recommendedVoices.map(v => v.voice_id).join(',')}`
    if (validatedVoicesRef.current === validationKey) return

    const validVoiceIds = new Set(recommendedVoices.map(v => v.voice_id))

    // Check if any agent has an invalid voice for current provider
    setAgents(prev => {
      const hasInvalidVoices = prev.some(a => !validVoiceIds.has(a.voice_id))
      if (!hasInvalidVoices) {
        validatedVoicesRef.current = validationKey
        return prev
      }

      // Reset invalid voices to valid ones for current provider
      const shuffled = [...recommendedVoices].sort(() => Math.random() - 0.5)
      validatedVoicesRef.current = validationKey

      return prev.map((agent, i) => {
        if (!validVoiceIds.has(agent.voice_id)) {
          const newVoice = shuffled[i % shuffled.length]
          return {
            ...agent,
            voice_id: newVoice.voice_id,
            voice_name: newVoice.name,
          }
        }
        return agent
      })
    })
  }, [selectedProvider, recommendedVoices, setAgents])

  // Set default TTS model when models load (or validate existing model)
  useEffect(() => {
    if (ttsModels.length > 0 && selectedProvider) {
      // Ensure ttsModels are for the current provider (not stale from previous session)
      const modelsMatchProvider = ttsModels.some(m =>
        isModelForProvider(m.model_id, selectedProvider)
      )
      if (!modelsMatchProvider) {
        // Models are stale (from different provider), wait for correct ones to load
        return
      }

      // Check if current model is valid for the loaded models (case-insensitive)
      const currentModel = voiceSettings.tts_model || ''
      const currentModelValid = ttsModels.some(m =>
        m.model_id.toLowerCase() === currentModel.toLowerCase()
      )
      if (!currentModelValid) {
        // Use first available model
        setVoiceSettings(prev => ({ ...prev, tts_model: ttsModels[0].model_id }))
      }
    }
  }, [ttsModels, voiceSettings.tts_model, selectedProvider, isModelForProvider, setVoiceSettings])

  // Filter models to only allowed voice room models
  const voiceRoomModels = useMemo(() => {
    return allModels.filter((model) =>
      VOICE_ROOM_ALLOWED_MODELS.includes(model.model_id)
    )
  }, [allModels])

  // Callers (form population, step components) work with plain strings —
  // `ttsProviders[].id` and dropdown values are always a real TTSProviderId
  // (or '' to clear) by construction, so this narrows at the one boundary
  // where untyped string input meets the provider-typed state.
  const setSelectedProviderFromString = useCallback((v: string) => {
    setSelectedProvider(v as TTSProviderId | '')
  }, [])

  return {
    selectedProvider,
    setSelectedProvider: setSelectedProviderFromString,
    resetVoiceValidation,
    ttsProviders,
    ttsModels,
    ttsModelsLoaded,
    recommendedVoices,
    voiceRoomModels,
  }
}
