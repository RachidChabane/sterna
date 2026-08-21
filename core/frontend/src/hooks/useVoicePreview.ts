import { useState, useRef, useCallback } from 'react'
import { getAccessToken } from '@/api/client'
import type { VoiceInfo, TTSProviderId } from '@/types/voiceRoom'

interface UseVoicePreviewOptions {
  provider: TTSProviderId
  voices: VoiceInfo[]
  language?: string
  ttsModel?: string
  speed?: number
}

/**
 * Shared hook for voice preview functionality.
 * - ElevenLabs: Uses free CDN preview URLs (with language-specific support)
 * - OpenAI: Uses our custom endpoint
 */
export function useVoicePreview({
  provider,
  voices,
  language,
  ttsModel,
  speed = 1.0,
}: UseVoicePreviewOptions) {
  const [playingVoiceId, setPlayingVoiceId] = useState<string | null>(null)
  const [isLoadingPreview, setIsLoadingPreview] = useState(false)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  // Get preview URL for a voice - prefers free CDN URLs for ElevenLabs
  const getPreviewUrl = useCallback((voiceId: string): string | undefined => {
    const voice = voices.find(v => v.voice_id === voiceId)
    if (!voice) return undefined

    // For ElevenLabs, use their free preview URLs
    if (provider === 'elevenlabs') {
      // Check for language-specific preview first
      if (language && language !== 'auto' && voice.verified_languages) {
        const langPreview = voice.verified_languages.find(
          vl => vl.language.toLowerCase() === language.toLowerCase() ||
                vl.locale?.toLowerCase() === language.toLowerCase()
        )
        if (langPreview?.preview_url) {
          return langPreview.preview_url
        }
      }
      // Fall back to default preview URL
      if (voice.preview_url) {
        return voice.preview_url
      }
    }

    // For OpenAI or fallback: use our custom endpoint
    const params = new URLSearchParams({
      provider,
      voice_id: voiceId,
    })

    if (ttsModel) {
      params.set('model_id', ttsModel)
    }

    params.set('speed', speed.toString())

    return `/api/voice-rooms/voice-preview/?${params.toString()}`
  }, [provider, voices, language, ttsModel, speed])

  // Play preview for a voice
  const playPreview = useCallback(async (voiceId: string) => {
    // Toggle off if already playing
    if (playingVoiceId === voiceId) {
      audioRef.current?.pause()
      setPlayingVoiceId(null)
      return
    }

    // Stop any current playback
    audioRef.current?.pause()

    const previewUrl = getPreviewUrl(voiceId)
    if (!previewUrl) return

    setIsLoadingPreview(true)

    try {
      const isInternalEndpoint = previewUrl.startsWith('/api/')
      let audioUrl: string
      let shouldRevoke = false

      if (isInternalEndpoint) {
        // Fetch with authentication for internal endpoints
        const token = getAccessToken()
        const response = await fetch(previewUrl, {
          headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        })

        if (!response.ok) {
          console.error('Failed to fetch voice preview:', response.status)
          return
        }

        const blob = await response.blob()
        audioUrl = URL.createObjectURL(blob)
        shouldRevoke = true
      } else {
        // External URL (e.g., ElevenLabs CDN) - use directly
        audioUrl = previewUrl
      }

      const audio = new Audio(audioUrl)
      audioRef.current = audio

      audio.onended = () => {
        setPlayingVoiceId(null)
        if (shouldRevoke) URL.revokeObjectURL(audioUrl)
      }
      audio.onerror = () => {
        setPlayingVoiceId(null)
        if (shouldRevoke) URL.revokeObjectURL(audioUrl)
      }

      await audio.play()
      setPlayingVoiceId(voiceId)
    } catch (err) {
      console.error('Error playing voice preview:', err)
    } finally {
      setIsLoadingPreview(false)
    }
  }, [playingVoiceId, getPreviewUrl])

  // Stop current playback
  const stopPreview = useCallback(() => {
    audioRef.current?.pause()
    setPlayingVoiceId(null)
  }, [])

  // Cleanup function for useEffect
  const cleanup = useCallback(() => {
    audioRef.current?.pause()
  }, [])

  return {
    playingVoiceId,
    isLoadingPreview,
    playPreview,
    stopPreview,
    cleanup,
  }
}
