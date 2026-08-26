/**
 * useTTS Hook
 *
 * Provides text-to-speech functionality supporting multiple providers
 * (OpenAI TTS, ElevenLabs).
 *
 * Features:
 * - Multiple TTS providers (OpenAI default, ElevenLabs for premium)
 * - Play/stop controls
 * - Loading and speaking state tracking
 * - Automatic cleanup on unmount
 * - Falls back to browser speechSynthesis if API fails
 * - Uses settings from settingsStore for voice configuration
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { fetchStream } from '@/api/transport'
import { useSettingsStore } from '@/store/settingsStore'
import type { TTSModel, TTSProviderId } from '@/types/voiceRoom'

/** JSON body posted to `/api/voice-rooms/tts/`, built from the current TTS settings. */
interface TTSRequestBody {
  text: string
  provider: TTSProviderId
  voice_id: string
  model_id: TTSModel
  speed: number
  stability?: number
  similarity_boost?: number
  style?: number
  use_speaker_boost?: boolean
  language_code?: string
}

interface UseTTSOptions {
  /** Override voice ID from settings (optional) */
  voiceIdOverride?: string
  /** Whether to use browser fallback if API fails */
  useBrowserFallback?: boolean
}

interface UseTTSReturn {
  /** Start speaking the provided text */
  speak: (text: string) => void
  /** Stop speaking */
  stop: () => void
  /** Whether TTS is currently speaking */
  isSpeaking: boolean
  /** Whether TTS is loading (fetching audio) */
  isLoading: boolean
  /** Whether TTS is supported and enabled */
  isSupported: boolean
  /** Whether TTS is enabled in settings */
  isEnabled: boolean
  /** Any error that occurred */
  error: string | null
}

/**
 * Strip markdown and code blocks from text for cleaner TTS output
 */
function stripMarkdown(text: string): string {
  return text
    // Remove code blocks
    .replace(/```[\s\S]*?```/g, '')
    // Remove inline code
    .replace(/`[^`]+`/g, '')
    // Remove bold/italic markers
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/_([^_]+)_/g, '$1')
    // Remove links, keep text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    // Remove headers
    .replace(/^#+\s+/gm, '')
    // Remove bullet points
    .replace(/^[\s]*[-*+]\s+/gm, '')
    // Remove numbered lists
    .replace(/^[\s]*\d+\.\s+/gm, '')
    // Remove blockquotes
    .replace(/^>\s+/gm, '')
    // Remove horizontal rules
    .replace(/^[-*_]{3,}$/gm, '')
    // Normalize whitespace
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

/**
 * Browser-based TTS fallback using Web Speech API
 */
const browserTTSSpeak = (text: string, speed: number = 1) => {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return
  speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.rate = speed
  utterance.pitch = 1
  utterance.volume = 1
  speechSynthesis.speak(utterance)
}

const browserTTSStop = () => {
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    speechSynthesis.cancel()
  }
}

export function useTTS(options: UseTTSOptions = {}): UseTTSReturn {
  const { voiceIdOverride, useBrowserFallback = true } = options

  // Get TTS settings from store
  const ttsSettings = useSettingsStore((state) => state.tts)
  const {
    enabled: ttsEnabled,
    provider,
    voiceId: settingsVoiceId,
    language,
    ttsModel,
    speed,
    // ElevenLabs-specific settings
    stability,
    similarityBoost,
    style,
    useSpeakerBoost,
  } = ttsSettings

  // Use override voice or settings voice
  const voiceId = voiceIdOverride || settingsVoiceId

  const [isSpeaking, setIsSpeaking] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Check if supported (always true since we have browser fallback)
  const isSupported = true

  // Cleanup on unmount only
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current.src = ''
        audioRef.current = null
      }
      const controller = abortControllerRef.current
      if (controller) {
        abortControllerRef.current = null
        try {
          controller.abort()
        } catch {
          // Ignore abort errors
        }
      }
      browserTTSStop()
    }
  }, []) // Empty deps - only run on unmount

  const stop = useCallback(() => {
    // Stop audio playback
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }

    // Abort any pending request - store reference first to avoid race conditions
    const controller = abortControllerRef.current
    if (controller) {
      abortControllerRef.current = null
      try {
        controller.abort()
      } catch {
        // Ignore abort errors
      }
    }

    // Stop browser TTS if it was used as fallback
    browserTTSStop()

    setIsSpeaking(false)
    setIsLoading(false)
  }, [])

  const speak = useCallback(async (text: string) => {
    // Check if TTS is enabled in settings
    if (!ttsEnabled) {
      
      return
    }

    
    if (!text.trim()) {
      
      return
    }

    // Clean the text first before any state changes
    const cleanText = stripMarkdown(text)
    
    if (!cleanText.trim()) {
      
      return
    }

    // Stop any current playback
    stop()

    // Create a new abort controller for this request
    const controller = new AbortController()
    abortControllerRef.current = controller

    setIsLoading(true)
    setError(null)

    try {
      // Build request body with provider and common settings
      const requestBody: TTSRequestBody = {
        text: cleanText,
        provider: provider,
        voice_id: voiceId,
        model_id: ttsModel,
        speed,
      }

      // Add ElevenLabs-specific settings only for that provider
      if (provider === 'elevenlabs') {
        requestBody.stability = stability
        requestBody.similarity_boost = similarityBoost
        requestBody.style = style
        requestBody.use_speaker_boost = useSpeakerBoost
      }

      // Add language if not auto-detect
      if (language && language !== 'auto') {
        requestBody.language_code = language
      }

      const response = await fetchStream('/api/voice-rooms/tts/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      })

      

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`TTS API error: ${response.status} - ${errorText}`)
      }

      // Check if aborted during fetch
      if (controller.signal.aborted) {
        
        setIsLoading(false)
        return
      }

      // Get the audio blob
      const audioBlob = await response.blob()
      

      if (audioBlob.size === 0) {
        throw new Error('Received empty audio response')
      }

      const audioUrl = URL.createObjectURL(audioBlob)

      // Create and play audio
      
      const audio = new Audio(audioUrl)
      audioRef.current = audio

      audio.onloadeddata = () => {
        
      }

      audio.oncanplay = () => {
        
      }

      audio.onplay = () => {
        
        // Only update state if this request wasn't aborted
        if (!controller.signal.aborted) {
          setIsLoading(false)
          setIsSpeaking(true)
        }
      }

      audio.onended = () => {
        
        // Only update state if this request wasn't aborted
        if (!controller.signal.aborted) {
          setIsSpeaking(false)
        }
        URL.revokeObjectURL(audioUrl)
      }

      audio.onerror = (e) => {
        console.error('[TTS] Audio error:', e, audio.error)
        // Only update state if this request wasn't aborted
        if (!controller.signal.aborted) {
          setIsSpeaking(false)
          setIsLoading(false)
          setError('Failed to play audio')
        }
        URL.revokeObjectURL(audioUrl)
      }

      
      try {
        await audio.play()
        
      } catch (playError) {
        console.error('[TTS] audio.play() failed:', playError)
        throw playError
      }

    } catch (err: unknown) {
      

      // Don't report abort/cancel errors (axios uses 'CanceledError' or code 'ERR_CANCELED')
      const isAxiosCancel = err && typeof err === 'object' && 'code' in err && (err as {code: string}).code === 'ERR_CANCELED'
      if (err instanceof Error && (err.name === 'AbortError' || err.name === 'CanceledError') || isAxiosCancel) {
        
        setIsLoading(false)
        return
      }

      // Handle errors - only if this request wasn't aborted
      if (controller.signal.aborted) {
        
        return
      }

      const errorMessage = err instanceof Error ? err.message : 'TTS failed'
      console.error('[TTS] Error:', err)
      setError(errorMessage)
      setIsLoading(false)

      // Fall back to browser TTS if enabled
      if (useBrowserFallback) {
        
        browserTTSSpeak(cleanText, speed)
        setIsSpeaking(true)

        // Browser TTS doesn't have easy end detection, estimate based on text length
        const estimatedDuration = Math.max(3000, cleanText.length * 50)
        setTimeout(() => {
          setIsSpeaking(false)
        }, estimatedDuration)
      }
    }
  }, [ttsEnabled, provider, voiceId, language, ttsModel, stability, similarityBoost, style, speed, useSpeakerBoost, useBrowserFallback, stop])

  return {
    speak,
    stop,
    isSpeaking,
    isLoading,
    isSupported,
    isEnabled: ttsEnabled,
    error,
  }
}
