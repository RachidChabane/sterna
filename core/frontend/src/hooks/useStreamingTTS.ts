/**
 * useStreamingTTS Hook
 *
 * Provides streaming text-to-speech functionality for real-time AI responses.
 * Instead of waiting for the entire response, this hook speaks text chunk by chunk
 * as sentences are completed, creating a more natural conversation flow.
 *
 * Features:
 * - Sentence boundary detection for natural speech breaks
 * - Audio queue management for seamless playback
 * - Interrupt support (clears queue and stops playback)
 * - Integrates with existing TTS settings
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { getAccessToken } from '@/api/client'
import { useSettingsStore } from '@/store/settingsStore'

interface UseStreamingTTSOptions {
  /** Minimum characters before speaking (to avoid tiny chunks) */
  minChunkSize?: number
  /** Whether to use browser fallback if API fails */
  useBrowserFallback?: boolean
}

interface UseStreamingTTSReturn {
  /** Add streaming text - will extract and queue complete sentences */
  addStreamingText: (text: string) => void
  /** Signal that streaming is complete - speak any remaining text */
  flushRemaining: (fullText?: string) => void
  /** Stop speaking and clear the queue */
  stop: () => void
  /** Clear accumulated text (for new conversation) */
  reset: () => void
  /** Whether TTS is currently speaking */
  isSpeaking: boolean
  /** Whether TTS is loading (fetching audio) */
  isLoading: boolean
  /** Number of chunks waiting in queue */
  queueLength: number
  /** Whether TTS is enabled in settings */
  isEnabled: boolean
  /** Any error that occurred */
  error: string | null
  /** Whether any audio has started playing (for hiding loading indicators) */
  hasStartedPlaying: boolean
}

// Sentence ending patterns - split on these for natural speech breaks
// Matches: . ! ? followed by space (removed colon - too many false positives with metadata like {{ACTION: }})
const SENTENCE_END_REGEX = /([.!?])\s+/

// Pattern to detect if text ends with sentence-ending punctuation (possibly with quotes)
const ENDS_WITH_SENTENCE_PUNCT = /[.!?]["']?\s*$/

// Minimum chunk size to avoid speaking tiny fragments
// Keep low for natural voice conversations (short sentences like "Sure!" should be spoken)
const DEFAULT_MIN_CHUNK_SIZE = 5

// Timeout (ms) to wait before speaking text ending in punctuation
// This handles the streaming case where we get "Hello." but haven't received the next word yet
// Keep very short (100ms) for responsive streaming TTS - minimize pauses
const SENTENCE_FLUSH_TIMEOUT_MS = 100

/**
 * Strip markdown, code blocks, and internal metadata from text for cleaner TTS output
 */
function stripMarkdown(text: string): string {
  return text
    // Remove {{ACTION: ...}} metadata tags (internal system content)
    .replace(/\{\{ACTION:[^}]*\}\}/g, '')
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
 * Reduce punctuation pauses for more natural flowing speech
 * TTS engines pause at periods - this softens some pauses while keeping natural rhythm
 */
function reducePunctuationPauses(text: string): string {
  return text
    // Replace ellipsis with comma (softer pause)
    .replace(/\.{2,}/g, ',')
    // Replace semicolons with commas (shorter pause)
    .replace(/;/g, ',')
    // Replace colons mid-sentence with commas
    .replace(/:\s+(?=[a-z])/g, ', ')
    // Remove double punctuation
    .replace(/([.!?])\1+/g, '$1')
    // Reduce multiple commas
    .replace(/,{2,}/g, ',')
    // Remove pause before "and", "or", "but" (reads more naturally)
    .replace(/,\s+(and|or|but)\s+/gi, ' $1 ')
    // Normalize spaces around punctuation
    .replace(/\s+([.,!?])/g, '$1')
    .replace(/([.,!?])\s+/g, '$1 ')
    .trim()
}

/**
 * Extract complete sentences from text, returning [sentences, remaining]
 */
function extractSentences(text: string, minSize: number): [string[], string] {
  const sentences: string[] = []
  let remaining = text

  // Keep extracting sentences until we can't find any more
  while (true) {
    const match = remaining.match(SENTENCE_END_REGEX)
    if (!match || match.index === undefined) break

    // Include the punctuation in the sentence
    const endIndex = match.index + match[0].length
    const sentence = remaining.slice(0, endIndex).trim()

    // Only add if it meets minimum size
    if (sentence.length >= minSize) {
      sentences.push(sentence)
      remaining = remaining.slice(endIndex).trim()
    } else {
      // Sentence too short, keep accumulating
      break
    }
  }

  return [sentences, remaining]
}

export function useStreamingTTS(options: UseStreamingTTSOptions = {}): UseStreamingTTSReturn {
  const { minChunkSize = DEFAULT_MIN_CHUNK_SIZE, useBrowserFallback = false } = options

  // Get TTS settings from store
  const ttsSettings = useSettingsStore((state) => state.tts)
  const {
    enabled: ttsEnabled,
    provider,
    voiceId,
    language,
    ttsModel,
    speed,
    stability,
    similarityBoost,
    style,
    useSpeakerBoost,
  } = ttsSettings

  // State
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [queueLength, setQueueLength] = useState(0)
  const [hasStartedPlaying, setHasStartedPlaying] = useState(false) // Track if any audio has started playing

  // Refs for queue management
  const lastQueuedIndexRef = useRef(0) // Track how much of the text we've already queued
  const textQueueRef = useRef<string[]>([]) // Text waiting to be converted to audio
  const audioQueueRef = useRef<{ text: string; audioUrl: string }[]>([]) // Pre-fetched audio ready to play
  const isProcessingRef = useRef(false) // Currently playing audio
  const isFetchingRef = useRef(false) // Currently fetching TTS audio
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const isMountedRef = useRef(true)

  // Refs for timeout-based sentence flushing
  const pendingTextRef = useRef('') // Text waiting to be flushed (ends with punctuation but no space yet)
  const flushTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  // Track mounted state
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current.src = ''
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
      if (flushTimeoutRef.current) {
        clearTimeout(flushTimeoutRef.current)
      }
      // Revoke any pre-fetched audio URLs to free memory
      audioQueueRef.current.forEach(({ audioUrl }) => {
        URL.revokeObjectURL(audioUrl)
      })
    }
  }, [])

  // Fetch TTS audio for the next text in queue (runs in parallel with playback)
  const fetchNextAudio = useCallback(async () => {
    if (!isMountedRef.current) return
    if (isFetchingRef.current) return
    if (textQueueRef.current.length === 0) return

    isFetchingRef.current = true
    const text = textQueueRef.current.shift()!

    // Create abort controller for this fetch
    abortControllerRef.current = new AbortController()

    // Clean the text and reduce punctuation pauses for natural speech
    const cleanText = reducePunctuationPauses(stripMarkdown(text))
    if (!cleanText.trim() || cleanText.trim().length < 2) {
      isFetchingRef.current = false
      // Try next immediately
      setTimeout(() => fetchNextAudio(), 0)
      return
    }

    setIsLoading(true)

    try {
      const token = getAccessToken()
      const requestBody: Record<string, any> = {
        text: cleanText,
        provider,
        voice_id: voiceId,
        model_id: ttsModel,
        speed,
      }

      if (provider === 'elevenlabs') {
        requestBody.stability = stability
        requestBody.similarity_boost = similarityBoost
        requestBody.style = style
        requestBody.use_speaker_boost = useSpeakerBoost
      }

      if (language && language !== 'auto') {
        requestBody.language_code = language
      }

      const response = await fetch('/api/voice-rooms/tts/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(requestBody),
        signal: abortControllerRef.current?.signal,
      })

      if (!response.ok) {
        throw new Error(`TTS API error: ${response.status}`)
      }

      const audioBlob = await response.blob()
      if (audioBlob.size === 0) {
        throw new Error('Empty audio response')
      }

      const audioUrl = URL.createObjectURL(audioBlob)

      // Add to audio queue
      audioQueueRef.current.push({ text: cleanText, audioUrl })
      setQueueLength(textQueueRef.current.length + audioQueueRef.current.length)

      isFetchingRef.current = false

      // Start playback if not already playing
      if (!isProcessingRef.current) {
        playNextAudio()
      }

      // Continue fetching more
      if (textQueueRef.current.length > 0) {
        fetchNextAudio()
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
      } else {
        console.error('[StreamingTTS] Fetch error:', err)
        if (isMountedRef.current) {
          setError(err instanceof Error ? err.message : 'TTS failed')
        }
      }
      isFetchingRef.current = false
      setIsLoading(false)

      // Try next
      if (textQueueRef.current.length > 0) {
        fetchNextAudio()
      }
    }
  }, [provider, voiceId, ttsModel, speed, stability, similarityBoost, style, useSpeakerBoost, language])

  // Play the next audio from the pre-fetched queue
  const playNextAudio = useCallback(() => {
    if (!isMountedRef.current) return
    if (isProcessingRef.current) return

    if (audioQueueRef.current.length === 0) {
      // No audio ready - if still fetching, wait; otherwise we're done
      if (!isFetchingRef.current && textQueueRef.current.length === 0) {
        setIsSpeaking(false)
        setIsLoading(false)
      }
      return
    }

    isProcessingRef.current = true
    const { text, audioUrl } = audioQueueRef.current.shift()!
    setQueueLength(textQueueRef.current.length + audioQueueRef.current.length)


    const audio = new Audio(audioUrl)
    audioRef.current = audio

    audio.onplay = () => {
      if (isMountedRef.current) {
        setIsLoading(audioQueueRef.current.length === 0 && isFetchingRef.current)
        setIsSpeaking(true)
        setHasStartedPlaying(true) // First audio chunk has started playing
      }
    }

    audio.onended = () => {
      URL.revokeObjectURL(audioUrl)
      isProcessingRef.current = false
      if (isMountedRef.current) {
        playNextAudio()
      }
    }

    audio.onerror = (e) => {
      console.error('[StreamingTTS] 🔊 Audio error:', e)
      URL.revokeObjectURL(audioUrl)
      isProcessingRef.current = false
      if (isMountedRef.current) {
        setError('Audio playback failed')
        playNextAudio()
      }
    }

    audio.play().catch(err => {
      console.error('[StreamingTTS] Play error:', err)
      isProcessingRef.current = false
      playNextAudio()
    })
  }, [])

  // Legacy processQueue - now just triggers the new pipeline
  const processQueue = useCallback(() => {
    // Start fetching if not already
    if (!isFetchingRef.current && textQueueRef.current.length > 0) {
      fetchNextAudio()
    }
    // Start playing if not already
    if (!isProcessingRef.current && audioQueueRef.current.length > 0) {
      playNextAudio()
    }
  }, [fetchNextAudio, playNextAudio])

  // Helper to queue a sentence
  const queueSentence = useCallback((sentence: string) => {
    if (!sentence.trim()) return

    const totalQueue = textQueueRef.current.length + audioQueueRef.current.length + 1
    textQueueRef.current.push(sentence)
    setQueueLength(totalQueue)

    // Start fetching immediately (will run in parallel with any ongoing playback)
    if (!isFetchingRef.current) {
      fetchNextAudio()
    }
  }, [fetchNextAudio])

  // Add streaming text - extract and queue complete sentences
  const addStreamingText = useCallback((fullText: string) => {
    if (!ttsEnabled) return

    // Only look at new content since last queue
    const newContent = fullText.slice(lastQueuedIndexRef.current)
    if (!newContent) return

    // Check if we had pending text that ended with punctuation
    // If new content has MORE than just the pending text, the pending text is complete!
    if (pendingTextRef.current && flushTimeoutRef.current) {
      // Check if the new content extends beyond the pending text
      if (newContent.length > pendingTextRef.current.length) {
        // The pending text is complete - queue it immediately
        clearTimeout(flushTimeoutRef.current)
        flushTimeoutRef.current = null

        const pendingLength = pendingTextRef.current.length
        const textToFlush = pendingTextRef.current.trim()
        pendingTextRef.current = ''

        if (textToFlush.length >= minChunkSize) {
          queueSentence(textToFlush)
        }
        // Always update the queued index by the original pending length (not trimmed)
        // This ensures we skip past the full pending text including any whitespace
        lastQueuedIndexRef.current += pendingLength
      }
    }

    // Re-calculate new content after potentially queuing pending text
    const currentNewContent = fullText.slice(lastQueuedIndexRef.current)
    if (!currentNewContent) return

    // Try to extract complete sentences (those followed by whitespace)
    const [sentences, remaining] = extractSentences(currentNewContent, minChunkSize)

    if (sentences.length > 0) {
      // Update the queued index to include all queued sentences
      lastQueuedIndexRef.current = fullText.length - remaining.length

      // Queue all complete sentences
      sentences.forEach(queueSentence)
    }

    // If remaining text ends with sentence punctuation, set timeout to flush it
    // This handles cases like "Hello." where the next word hasn't arrived yet
    // Only set timeout if we don't already have one for this exact text
    if (remaining.length >= minChunkSize && ENDS_WITH_SENTENCE_PUNCT.test(remaining)) {
      // Only set a new timeout if we don't have pending text or it's different
      if (pendingTextRef.current !== remaining) {
        // Clear existing timeout if any
        if (flushTimeoutRef.current) {
          clearTimeout(flushTimeoutRef.current)
        }

        pendingTextRef.current = remaining

        flushTimeoutRef.current = setTimeout(() => {
          if (pendingTextRef.current && isMountedRef.current) {
            const pendingLength = pendingTextRef.current.length
            const textToFlush = pendingTextRef.current.trim()
            pendingTextRef.current = ''
            flushTimeoutRef.current = null
            // Update queued index by original length (not trimmed)
            lastQueuedIndexRef.current += pendingLength

            if (textToFlush.length >= minChunkSize) {
              queueSentence(textToFlush)
            }
          }
        }, SENTENCE_FLUSH_TIMEOUT_MS)
      }
      // If pendingTextRef.current === remaining, keep the existing timeout running
    } else {
      // Remaining text doesn't end with punctuation - clear any pending timeout
      if (flushTimeoutRef.current) {
        clearTimeout(flushTimeoutRef.current)
        flushTimeoutRef.current = null
      }
      pendingTextRef.current = ''
    }
  }, [ttsEnabled, minChunkSize, queueSentence])

  // Flush remaining text when streaming completes
  // Called with the final full text
  const flushRemaining = useCallback((fullText?: string) => {
    if (!ttsEnabled) return

    // Clear any pending flush timeout
    if (flushTimeoutRef.current) {
      clearTimeout(flushTimeoutRef.current)
      flushTimeoutRef.current = null
    }
    pendingTextRef.current = ''

    // If fullText is not provided, nothing to flush
    if (!fullText) return

    // Get any remaining text that hasn't been queued
    const remaining = fullText.slice(lastQueuedIndexRef.current).trim()

    if (remaining.length > 0) {
      queueSentence(remaining)
      lastQueuedIndexRef.current = fullText.length
    }
  }, [ttsEnabled, queueSentence])

  // Stop speaking and clear queue
  const stop = useCallback(() => {

    // Clear flush timeout
    if (flushTimeoutRef.current) {
      clearTimeout(flushTimeoutRef.current)
      flushTimeoutRef.current = null
    }

    // Abort any pending request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }

    // Stop current audio
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }

    // Revoke any pre-fetched audio URLs to free memory
    audioQueueRef.current.forEach(({ audioUrl }) => {
      URL.revokeObjectURL(audioUrl)
    })

    // Clear both queues and pending text but keep index (so we don't re-speak content)
    textQueueRef.current = []
    audioQueueRef.current = []
    pendingTextRef.current = ''
    setQueueLength(0)
    isProcessingRef.current = false
    isFetchingRef.current = false

    setIsSpeaking(false)
    setIsLoading(false)
  }, [])

  // Reset for new conversation
  const reset = useCallback(() => {
    stop()
    lastQueuedIndexRef.current = 0
    pendingTextRef.current = ''
    setHasStartedPlaying(false) // Reset playback tracking for new conversation
  }, [stop])

  return {
    addStreamingText,
    flushRemaining,
    stop,
    reset,
    isSpeaking,
    isLoading,
    queueLength,
    isEnabled: ttsEnabled,
    error,
    hasStartedPlaying,
  }
}
