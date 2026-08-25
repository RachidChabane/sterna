/**
 * VoiceConversationOverlay
 *
 * A fullscreen overlay for voice conversations in single chats.
 * Replicates the Voice Session UX with SpatialPresence visuals.
 * - Automatic listening with silence detection
 * - Auto-send message after speech ends
 * - Auto-read AI response via TTS
 * - Auto-resume listening after TTS finishes
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { Mic, MicOff, X, Hand, MessageSquareText, Wrench } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTheme } from '@/hooks/useTheme'
import { useStreamingTTS } from '@/hooks/useStreamingTTS'
import { useSettingsStore } from '@/store/settingsStore'
import { getAccessToken } from '@/api/client'
import { toast } from 'sonner'
import { SpatialPresence } from '@/components/voice-rooms/SpatialPresence'
import { UserVoicePulse } from '@/components/voice-rooms/UserVoicePulse'
import { ThinkingDots } from '@/components/voice-rooms/ThinkingIndicator'
import { ModelIcon } from './ModelIcon'
import type { Message, Model } from './types'
import type { VoiceAgent } from '@/types/voiceRoom'

// Audio recording configuration
const AUDIO_CONSTRAINTS: MediaStreamConstraints = {
  audio: {
    sampleRate: 16000,
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  },
}

// Silence detection settings
const SILENCE_THRESHOLD = 0.02 // Audio level below this is considered silence
const SILENCE_DURATION_MS = 1500 // How long silence must last before auto-stop
const MIN_SPEECH_DURATION_MS = 500 // Minimum speech before allowing silence detection

/**
 * Extract current tool action from message steps
 * Returns { isExecuting, actionDescription } or null if no tool execution
 */
function extractToolAction(message: Message | undefined): { isExecuting: boolean; actionDescription: string } | null {
  if (!message || message.role !== 'assistant' || !message.steps) return null

  // Find tool_executions steps
  for (const step of message.steps) {
    if (step.type === 'tool_executions' && step.executions?.length > 0) {
      const isExecuting = step.executions.some((e: any) => e.isExecuting === true)
      if (isExecuting || step.isExecuting) {
        // Get action description from first executing tool
        const exec = step.executions.find((e: any) => e.isExecuting) || step.executions[0]
        const displayName = exec?.tool_call?.display_name
        const toolName = exec?.tool_call?.function?.name || ''

        let actionDescription = displayName
        if (!actionDescription) {
          // Generate from tool name
          if (toolName.startsWith('brave_') || toolName.includes('_search')) {
            actionDescription = 'Searching the web'
          } else if (toolName.startsWith('read_')) {
            actionDescription = 'Reading files'
          } else if (toolName.startsWith('write_') || toolName.startsWith('edit_')) {
            actionDescription = 'Writing code'
          } else if (toolName.startsWith('execute_')) {
            actionDescription = 'Running code'
          } else if (toolName.startsWith('get_')) {
            actionDescription = 'Getting information'
          } else if (toolName.includes('image')) {
            actionDescription = 'Working with images'
          } else {
            // Default: capitalize and format
            actionDescription = toolName.replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase())
          }
        }

        return { isExecuting: true, actionDescription }
      }
    }
  }

  return null
}

interface VoiceConversationOverlayProps {
  isOpen: boolean
  onClose: () => void
  onSendMessage: (text: string) => Promise<void>
  messages: Message[]
  isGenerating: boolean
  model?: Model | null
  modelName?: string
}

type ConversationState = 'idle' | 'listening' | 'processing' | 'thinking' | 'speaking'

export function VoiceConversationOverlay({
  isOpen,
  onClose,
  onSendMessage,
  messages,
  isGenerating,
  model,
  modelName = 'AI',
}: VoiceConversationOverlayProps) {
  const { isDark } = useTheme()
  const sttLanguage = useSettingsStore((state) => state.stt.language)
  const setVoiceConversationActive = useSettingsStore((state) => state.setVoiceConversationActive)

  // Streaming TTS hook - speaks chunks as they stream in
  const {
    addStreamingText,
    flushRemaining,
    stop: stopTTS,
    reset: resetTTS,
    isSpeaking,
    isLoading: isTTSLoading,
    isEnabled: isTTSEnabled,
    queueLength: ttsQueueLength,
    hasStartedPlaying: ttsHasStartedPlaying,
  } = useStreamingTTS()

  // State
  const [state, setState] = useState<ConversationState>('idle')
  const [audioLevel, setAudioLevel] = useState(0)
  const [isMuted, setIsMuted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [transcriptText, setTranscriptText] = useState<string | null>(null)

  // Refs for recording
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const animationFrameRef = useRef<number | null>(null)

  // Refs for silence detection
  const silenceStartRef = useRef<number | null>(null)
  const speechStartRef = useRef<number | null>(null)
  const hasSpeechRef = useRef(false)

  // Ref to track last read message index
  const lastReadMessageIndexRef = useRef(-1)

  // Track if we should auto-read next response
  const shouldAutoReadRef = useRef(false)

  // Track the last content length we've processed for streaming TTS
  const lastProcessedContentLengthRef = useRef(0)

  // Ref to hold stopRecordingAndProcess to avoid circular dependency
  const stopRecordingAndProcessRef = useRef<() => Promise<void>>(async () => {})

  // Ref to track if we're in an interruptible state (thinking/speaking)
  const isInterruptibleRef = useRef(false)

  // Ref to track muted state for use in callbacks/timeouts (avoids stale closures)
  const isMutedRef = useRef(isMuted)
  useEffect(() => {
    isMutedRef.current = isMuted
  }, [isMuted])

  // Ref to stopTTS for use in audio level check
  const stopTTSRef = useRef(stopTTS)
  useEffect(() => {
    stopTTSRef.current = stopTTS
  }, [stopTTS])

  // Create a virtual "agent" for SpatialPresence from the model
  // Note: We use empty display_name and a fake model_id so SpatialPresence
  // only renders the glow effect, not the icon/name (we render those separately)
  const virtualAgent: VoiceAgent = useMemo(() => ({
    id: 'chat-model',
    model_id: '__voice_overlay__', // Fake ID so SpatialPresence won't find/render an icon
    display_name: '', // Empty - we show name in our own centered section
    system_prompt: '', // Unused - this virtual agent is only for the visual presence effect
    voice_id: 'alloy',
    voice_name: '',
    order: 0,
    color: '#38bdf8', // Sky blue - matches AGENT_COLORS[0]
  }), [])

  // Extract current tool action from the last assistant message
  const toolAction = useMemo(() => {
    const lastAssistantMessage = [...messages].reverse().find(m => m.role === 'assistant')
    return extractToolAction(lastAssistantMessage)
  }, [messages])

  // Cleanup function - stops all audio resources
  const cleanup = useCallback(() => {

    // Stop animation frame
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current)
      animationFrameRef.current = null
    }

    // Stop media recorder first (before closing stream)
    if (mediaRecorderRef.current) {
      try {
        if (mediaRecorderRef.current.state !== 'inactive') {
          mediaRecorderRef.current.stop()
        }
      } catch (e) {
      }
      mediaRecorderRef.current = null
    }

    // Stop all tracks on the stream - THIS IS THE KEY PART
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => {
        track.stop()
      })
      streamRef.current = null
    }

    // Close audio context
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {})
      audioContextRef.current = null
    }

    // Reset refs
    audioChunksRef.current = []
    analyserRef.current = null
    silenceStartRef.current = null
    speechStartRef.current = null
    hasSpeechRef.current = false
    setAudioLevel(0)
  }, [])

  // Cleanup on unmount - ensure mic is released
  useEffect(() => {
    return () => {
      // Force stop any remaining stream tracks
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop())
        streamRef.current = null
      }
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(() => {})
        audioContextRef.current = null
      }
      if (mediaRecorderRef.current) {
        try {
          if (mediaRecorderRef.current.state !== 'inactive') {
            mediaRecorderRef.current.stop()
          }
        } catch {}
        mediaRecorderRef.current = null
      }
    }
  }, [])

  // Start recording with silence detection
  const startRecording = useCallback(async () => {
    // Always check ref for current muted state (avoids stale closure issues from setTimeout)
    const currentlyMuted = isMutedRef.current

    if (currentlyMuted) {
      return
    }

    // Clean up any existing stream first to prevent leaks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {})
      audioContextRef.current = null
    }

    setError(null)
    silenceStartRef.current = null
    speechStartRef.current = null
    hasSpeechRef.current = false

    try {
      const stream = await navigator.mediaDevices.getUserMedia(AUDIO_CONSTRAINTS)
      streamRef.current = stream

      // Setup audio analysis
      const audioContext = new AudioContext()
      const analyser = audioContext.createAnalyser()
      const source = audioContext.createMediaStreamSource(stream)
      analyser.fftSize = 256
      analyser.smoothingTimeConstant = 0.5
      source.connect(analyser)
      audioContextRef.current = audioContext
      analyserRef.current = analyser

      // Setup MediaRecorder
      const mediaRecorder = new MediaRecorder(stream, { audioBitsPerSecond: 16000 })
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorder.onerror = (event) => {
      }

      mediaRecorder.start(100)
      // Only set to 'listening' if not in an interruptible state (thinking/speaking)
      // During those states, the mic is on for interruption but state stays as is
      if (!isInterruptibleRef.current) {
        setState('listening')
      }

      // Audio level monitoring with silence detection
      const dataArray = new Uint8Array(analyser.frequencyBinCount)
      let speechDetectedLogged = false
      let silenceDetectedLogged = false

      const checkAudioLevel = () => {
        if (!analyserRef.current) {
          return
        }

        analyserRef.current.getByteFrequencyData(dataArray)
        const sum = dataArray.reduce((a, b) => a + b, 0)
        const avg = sum / dataArray.length
        const normalizedLevel = Math.min(1, avg / 120)
        setAudioLevel(normalizedLevel)

        const now = Date.now()

        // Detect speech
        if (normalizedLevel > SILENCE_THRESHOLD) {
          if (!speechStartRef.current) {
            speechStartRef.current = now

            // If we're in an interruptible state (thinking/speaking), interrupt!
            if (isInterruptibleRef.current) {
              stopTTSRef.current() // Stop TTS and clear queue
              lastProcessedContentLengthRef.current = 0 // Reset for next response
              setState('listening') // Show we're listening now
            }
          }
          if (!speechDetectedLogged && hasSpeechRef.current) {
            speechDetectedLogged = true
          }
          hasSpeechRef.current = true
          silenceStartRef.current = null
          silenceDetectedLogged = false
        } else {
          // Silence detected
          if (!silenceStartRef.current) {
            silenceStartRef.current = now
          }

          // Check if we should auto-stop (silence after speech)
          const speechDuration = speechStartRef.current ? now - speechStartRef.current : 0
          const silenceDuration = silenceStartRef.current ? now - silenceStartRef.current : 0

          // Log silence progress occasionally
          if (hasSpeechRef.current && !silenceDetectedLogged && silenceDuration > 500) {
            silenceDetectedLogged = true
          }

          if (
            hasSpeechRef.current &&
            speechDuration >= MIN_SPEECH_DURATION_MS &&
            silenceDuration >= SILENCE_DURATION_MS
          ) {
            // Auto-stop recording - use ref to get current function
            stopRecordingAndProcessRef.current()
            return
          }
        }

        animationFrameRef.current = requestAnimationFrame(checkAudioLevel)
      }

      checkAudioLevel()
    } catch (err) {
      let errorMsg = 'Failed to access microphone'
      if (err instanceof DOMException) {
        if (err.name === 'NotAllowedError') {
          errorMsg = 'Microphone permission denied'
        } else if (err.name === 'NotFoundError') {
          errorMsg = 'No microphone found'
        }
      }
      setError(errorMsg)
      toast.error(errorMsg)
      setState('idle')
    }
  }, []) // Uses isMutedRef instead of isMuted to avoid stale closures

  // Stop recording and process
  const stopRecordingAndProcess = useCallback(async () => {

    if (!mediaRecorderRef.current || mediaRecorderRef.current.state === 'inactive') {
      return
    }

    setState('processing')

    // Stop animation
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current)
      animationFrameRef.current = null
    }
    setAudioLevel(0)

    return new Promise<void>((resolve) => {
      const mediaRecorder = mediaRecorderRef.current!

      mediaRecorder.onstop = async () => {

        // Cleanup stream
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((track) => track.stop())
          streamRef.current = null
        }
        if (audioContextRef.current) {
          audioContextRef.current.close().catch(() => {})
          audioContextRef.current = null
        }

        const chunks = audioChunksRef.current
        audioChunksRef.current = []


        if (chunks.length === 0 || !hasSpeechRef.current) {
          // No speech detected, resume listening
          setState('idle')
          setTimeout(() => startRecording(), 500)
          resolve()
          return
        }

        const mimeType = mediaRecorder.mimeType || 'audio/webm'
        const audioBlob = new Blob(chunks, { type: mimeType })

        // Transcribe
        try {
          const formData = new FormData()
          const extension = mimeType.includes('webm') ? 'webm' : 'mp4'
          formData.append('audio', audioBlob, `recording.${extension}`)
          formData.append('language', sttLanguage)

          const accessToken = getAccessToken()

          const response = await fetch('/api/llm/transcribe/', {
            method: 'POST',
            headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
            body: formData,
          })


          if (!response.ok) {
            throw new Error(`Transcription failed: ${response.status}`)
          }

          const result = await response.json()
          const transcript = result.transcript?.trim()

          if (!transcript) {
            // No speech detected, resume listening
            setState('idle')
            setTimeout(() => startRecording(), 500)
            resolve()
            return
          }

          // Show transcript and send message
          setTranscriptText(transcript)
          setState('thinking')
          // Reset TTS queue for new message (clears lastQueuedIndex so new content isn't skipped)
          resetTTS()
          shouldAutoReadRef.current = true

          // Send the raw transcript
          try {
            await onSendMessage(transcript)

            // Immediately restart recording so user can interrupt during thinking/speaking
            setTimeout(() => startRecording(), 100)
          } catch (sendErr) {
            throw sendErr
          }
          resolve()
        } catch (err) {
          const errorMsg = err instanceof Error ? err.message : 'Transcription failed'
          setError(errorMsg)
          toast.error(errorMsg)
          setState('idle')
          resolve()
        }
      }

      mediaRecorder.stop()
    })
  }, [sttLanguage, onSendMessage, startRecording, resetTTS])

  // Keep ref in sync with the callback
  useEffect(() => {
    stopRecordingAndProcessRef.current = stopRecordingAndProcess
  }, [stopRecordingAndProcess])

  // Track interruptible state
  useEffect(() => {
    isInterruptibleRef.current = state === 'thinking' || state === 'speaking'
  }, [state])

  // Extract text from message
  const extractTextFromMessage = (message: Message): string => {
    if (typeof message.content === 'string') {
      return message.content
    }
    if (Array.isArray(message.content)) {
      return message.content
        .filter((part: any) => part.type === 'text')
        .map((part: any) => part.text)
        .join('\n')
    }
    return ''
  }

  // Streaming TTS - feed content as it streams in
  useEffect(() => {
    const lastMessage = messages[messages.length - 1]
    const content = lastMessage?.role === 'assistant' ? extractTextFromMessage(lastMessage) : ''

    if (!isOpen || !shouldAutoReadRef.current || !isTTSEnabled) {
      return
    }

    // Find the last assistant message
    const lastAssistantIndex = messages.length - 1

    if (!lastMessage || lastMessage.role !== 'assistant') {
      return
    }

    // Get current content
    const currentLength = content.length

    // If we have new content, feed it to streaming TTS
    if (currentLength > lastProcessedContentLengthRef.current) {
      lastProcessedContentLengthRef.current = currentLength
      addStreamingText(content)

      // Set state to speaking once we start
      if (state !== 'speaking') {
        setState('speaking')
      }
    }

    // When generation completes, flush remaining text
    if (!isGenerating && lastMessage.finish_reason) {
      flushRemaining(content) // Pass full text to flush any remaining
      lastReadMessageIndexRef.current = lastAssistantIndex
      shouldAutoReadRef.current = false
      lastProcessedContentLengthRef.current = 0
    }
  }, [isOpen, isGenerating, messages, isTTSEnabled, addStreamingText, flushRemaining, state])

  // Ref to track TTS transition timeout (prevents flicker between chunks)
  const ttsTransitionTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  // Ref to track if we should transition out of speaking (set by effect, read by timeout)
  const shouldTransitionRef = useRef(false)

  // Track TTS state with debouncing to prevent flicker
  useEffect(() => {

    // Speaking if playing audio, loading, or has items in queue
    const isTTSActive = isSpeaking || isTTSLoading || ttsQueueLength > 0

    // Clear any pending transition timeout
    if (ttsTransitionTimeoutRef.current) {
      clearTimeout(ttsTransitionTimeoutRef.current)
      ttsTransitionTimeoutRef.current = null
    }

    if (isTTSActive) {
      shouldTransitionRef.current = false
      if (state !== 'speaking') {
        setState('speaking')
      }
    } else if (state === 'speaking' && !isGenerating) {
      // TTS completely finished AND model is done generating
      // Mark that we want to transition and set a delay to prevent flicker
      shouldTransitionRef.current = true

      ttsTransitionTimeoutRef.current = setTimeout(() => {
        // Only transition if we still should (ref wasn't cleared by new TTS activity)
        if (shouldTransitionRef.current) {
          // Use ref for current muted state (avoids stale closure)
          const currentlyMuted = isMutedRef.current
          setState(currentlyMuted ? 'idle' : 'listening')
          setTranscriptText(null)

          // startRecording will check isMutedRef internally, so just call it
          // It will bail out if muted
          if (!mediaRecorderRef.current || mediaRecorderRef.current.state === 'inactive') {
            startRecording()
          }
        }
      }, 300) // 300ms debounce to handle gaps between TTS chunks
    }

    return () => {
      if (ttsTransitionTimeoutRef.current) {
        clearTimeout(ttsTransitionTimeoutRef.current)
      }
    }
  }, [isSpeaking, isTTSLoading, ttsQueueLength, state, isGenerating, startRecording]) // Uses isMutedRef instead of isMuted

  // Track generating state
  useEffect(() => {
    if (isGenerating && state !== 'speaking') {
      setState('thinking')
    }
  }, [isGenerating, state])

  // Auto-start when opened
  useEffect(() => {
    if (isOpen && state === 'idle' && !isMuted) {
      startRecording()
    }
  }, [isOpen, state, isMuted, startRecording])

  // Enable TTS when opening during ongoing generation
  useEffect(() => {
    if (isOpen && isGenerating && isTTSEnabled) {
      // Reset TTS queue so we start fresh with current message content
      resetTTS()
      shouldAutoReadRef.current = true
      setState('thinking')
    }
  }, [isOpen, isGenerating, isTTSEnabled, resetTTS])

  // Cleanup on close
  useEffect(() => {
    if (!isOpen) {
      cleanup()
      resetTTS()
      setState('idle')
      setTranscriptText(null)
      lastReadMessageIndexRef.current = -1
      shouldAutoReadRef.current = false
      lastProcessedContentLengthRef.current = 0
    }
  }, [isOpen, cleanup, resetTTS])

  // Set voice conversation mode for backend system prompt adjustment
  useEffect(() => {
    setVoiceConversationActive(isOpen)
    return () => setVoiceConversationActive(false)
  }, [isOpen, setVoiceConversationActive])

  // Handle mute toggle - only affects recording, NOT TTS playback
  const handleMuteToggle = useCallback(() => {
    if (isMuted) {
      // Unmuting - start recording in any state except processing (transcription)
      setIsMuted(false)
      if (state !== 'processing') {
        startRecording()
      }
    } else {
      // Muting - only stop the microphone/recording, NOT TTS
      setIsMuted(true)

      // Stop recording if active
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop())
        streamRef.current = null
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop()
        mediaRecorderRef.current = null
      }
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(() => {})
        audioContextRef.current = null
      }
      analyserRef.current = null
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current)
        animationFrameRef.current = null
      }
      setAudioLevel(0)

      // Only reset to idle if we were listening/processing, NOT if speaking
      if (state === 'listening' || state === 'processing') {
        setState('idle')
      }
    }
  }, [isMuted, state, startRecording])

  // Handle interrupt
  const handleInterrupt = useCallback(() => {
    if (state === 'speaking') {
      stopTTS()
      setState('idle')
      setTranscriptText(null)
      // startRecording checks isMutedRef internally, so just call it
      setTimeout(() => startRecording(), 300)
    }
  }, [state, stopTTS, startRecording])

  // Handle close
  const handleClose = useCallback(() => {
    cleanup()
    resetTTS()
    onClose()
  }, [cleanup, resetTTS, onClose])

  if (!isOpen) return null

  // Determine states for SpatialPresence
  const isListening = state === 'listening'
  const isSpeakingState = state === 'speaking'
  const isProcessingState = state === 'processing' || state === 'thinking'

  return (
    <div
      className={cn(
        'fixed inset-0 z-50 flex flex-col overflow-hidden',
        isDark ? 'bg-[#0c0c0c]' : 'bg-slate-50'
      )}
    >
      {/* Main content - SpatialPresence fills the screen */}
      <div className="flex-1 min-h-0 relative overflow-hidden">
        <div className="absolute inset-0">
          <SpatialPresence
            agents={[virtualAgent]}
            isListening={!isMuted && (isListening || isProcessingState || isSpeakingState)}
            isSpeaking={isSpeakingState}
            isProcessing={false} // We handle thinking dots ourselves
            audioLevel={isSpeakingState ? 0.5 : audioLevel}
            currentSpeaker={isSpeakingState ? 'chat-model' : null} // Only set when speaking, not processing
            className="w-full h-full"
            paddingTop={70}
            paddingBottom={120}
          />
        </div>

        {/* User voice pulse - subtle glow responding to user's audio input */}
        {/* Show pulse when listening OR when mic is active during thinking/speaking for interruption */}
        <UserVoicePulse
          audioLevel={audioLevel}
          isListening={!isMuted && (isListening || isProcessingState || isSpeakingState)}
          isDark={isDark}
        />

        {/* Centered model icon and name - always visible */}
        <div className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none">
          <div className="flex flex-col items-center">
            {/* Model icon */}
            {model && (
              <ModelIcon
                modelName={model.name}
                modelId={model.model_id}
                provider={model.provider}
                modelIconSlug={model.model_icon_slug}
                modelIconUrl={model.model_icon_url}
                providerIconSlug={model.provider_icon_slug}
                providerIconUrl={model.provider_icon_url}
                size={48}
                showTooltip={false}
              />
            )}

            {/* Model name */}
            <span
              className={cn(
                'mt-3 text-sm font-light tracking-widest uppercase',
                isDark ? 'text-white/70' : 'text-gray-700'
              )}
            >
              {modelName}
            </span>

            {/* Tool action indicator - shows when AI is using tools */}
            {toolAction?.isExecuting && (
              <div
                className={cn(
                  'mt-4 flex items-center gap-2.5 px-4 py-2.5 rounded-full backdrop-blur-md',
                  'animate-in fade-in-0 zoom-in-95 duration-300',
                  isDark
                    ? 'bg-accent-brand/10 border border-accent-brand/30'
                    : 'bg-brand-50/80 border border-brand-200'
                )}
              >
                <div className="relative">
                  <Wrench
                    className={cn(
                      'w-4 h-4',
                      isDark ? 'text-accent-brand' : 'text-brand-600'
                    )}
                  />
                  {/* Pulsing ring around icon */}
                  <div className="absolute inset-0 rounded-full animate-ping opacity-30 bg-accent-brand" />
                </div>
                <span className="shimmer-text text-sm font-medium">
                  {toolAction.actionDescription}
                </span>
                <div className="w-3.5 h-3.5 border-2 border-accent-brand/30 border-t-accent-brand rounded-full animate-spin" />
              </div>
            )}

            {/* Thinking dots when processing or preparing TTS (but not when using tools, and hide after first chunk plays) */}
            {!toolAction?.isExecuting && (isProcessingState || (state === 'speaking' && isTTSLoading && !ttsHasStartedPlaying)) && (
              <div className="mt-3">
                <ThinkingDots
                  isVisible={true}
                  color={isDark ? { r: 255, g: 255, b: 255 } : { r: 60, g: 60, b: 60 }}
                />
              </div>
            )}
          </div>
        </div>

        {/* Error display */}
        {error && (
          <div className="absolute top-20 left-0 right-0 flex justify-center z-20">
            <div
              className={cn(
                'px-4 py-2 rounded-xl backdrop-blur-md',
                isDark ? 'bg-red-500/10 border border-red-500/20' : 'bg-red-50 border border-red-200'
              )}
            >
              <p className="text-red-400 text-sm max-w-md text-center">{error}</p>
            </div>
          </div>
        )}
      </div>

      {/* Header - overlays with gradient fade */}
      <div className="absolute top-0 left-0 right-0 z-20">
        {/* Gradient fade background */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: isDark
              ? 'linear-gradient(to bottom, rgba(12,12,12,0.9) 0%, rgba(12,12,12,0.6) 60%, transparent 100%)'
              : 'linear-gradient(to bottom, rgba(248,250,252,0.9) 0%, rgba(248,250,252,0.6) 60%, transparent 100%)',
          }}
        />
        <div className="relative px-5 py-4 pb-8 flex items-center justify-between">
          {/* Placeholder for symmetry */}
          <div className="w-9" />

          {/* Title */}
          <span
            className={cn(
              'text-xs font-medium tracking-wider uppercase',
              isDark ? 'text-white/50' : 'text-gray-500'
            )}
          >
            Voice Conversation
          </span>

          {/* Close button */}
          <Button
            size="icon"
            variant="ghost"
            className={cn(
              'h-9 w-9 rounded-xl transition-all duration-200',
              isDark
                ? 'text-white/50 hover:text-white/80 hover:bg-white/5'
                : 'text-gray-500 hover:text-gray-700 hover:bg-black/5'
            )}
            onClick={handleClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Footer - overlays with gradient fade */}
      <div className="absolute bottom-0 left-0 right-0 z-20">
        {/* Gradient fade background */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: isDark
              ? 'linear-gradient(to top, rgba(12,12,12,0.9) 0%, rgba(12,12,12,0.6) 60%, transparent 100%)'
              : 'linear-gradient(to top, rgba(248,250,252,0.9) 0%, rgba(248,250,252,0.6) 60%, transparent 100%)',
          }}
        />
        <div className="relative px-4 md:px-5 pt-3 md:pt-4 pb-4 md:pb-5 flex flex-col items-center gap-3">
          {/* Transcript display */}
          {transcriptText && (
            <div className="px-4 max-w-xl mx-auto text-center">
              <p
                className={cn(
                  'text-sm font-medium',
                  isDark ? 'text-white/60' : 'text-gray-600'
                )}
              >
                "{transcriptText}"
              </p>
            </div>
          )}

          {/* Status text */}
          <span
            className={cn(
              'text-xs',
              isDark ? 'text-white/40' : 'text-gray-400'
            )}
          >
            {state === 'listening' && !isMuted && 'Listening...'}
            {state === 'processing' && 'Processing...'}
            {state === 'thinking' && toolAction?.isExecuting && !isMuted && `${toolAction.actionDescription}... (speak to interrupt)`}
            {state === 'thinking' && toolAction?.isExecuting && isMuted && `${toolAction.actionDescription}...`}
            {state === 'thinking' && !toolAction?.isExecuting && !isMuted && `${modelName} is thinking... (speak to interrupt)`}
            {state === 'thinking' && !toolAction?.isExecuting && isMuted && `${modelName} is thinking...`}
            {state === 'speaking' && !isMuted && `${modelName} is speaking... (speak to interrupt)`}
            {state === 'speaking' && isMuted && `${modelName} is speaking...`}
            {(state === 'idle' || (isMuted && state !== 'thinking' && state !== 'speaking')) && (isMuted ? 'Muted' : 'Ready')}
          </span>

          <div className="flex items-center justify-center gap-4">
            {/* Interrupt button - shows when AI is speaking */}
            {isSpeakingState && (
              <Button
                size="icon"
                className="h-11 w-11 rounded-2xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/20 transition-all duration-200"
                onClick={handleInterrupt}
                title="Interrupt"
              >
                <Hand className="h-5 w-5" />
              </Button>
            )}

            {/* Mic button - central, prominent */}
            {/* Show as active (not muted) when listening OR when thinking/speaking with mic on */}
            <Button
              size="icon"
              className={cn(
                'h-14 w-14 rounded-2xl transition-all duration-300 shadow-lg',
                !isMuted && (isListening || isProcessingState || isSpeakingState)
                  ? isDark
                    ? 'bg-white/10 text-white border border-white/20 hover:bg-white/15'
                    : 'bg-black/5 text-gray-800 border border-black/10 hover:bg-black/10'
                  : 'bg-red-500/90 text-white border border-red-400/30 hover:bg-red-500'
              )}
              onClick={handleMuteToggle}
            >
              {!isMuted ? (
                <Mic className="h-6 w-6" />
              ) : (
                <MicOff className="h-6 w-6" />
              )}
            </Button>

            {/* Close button */}
            <Button
              size="icon"
              variant="ghost"
              className={cn(
                'h-11 w-11 rounded-2xl transition-all duration-200',
                isDark
                  ? 'text-white/50 hover:text-white/80 hover:bg-white/10'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-black/5'
              )}
              onClick={handleClose}
            >
              <X className="h-5 w-5" />
            </Button>
          </div>

          {/* TTS tip */}
          {!isTTSEnabled && (
            <span
              className={cn(
                'text-[9px] md:text-[10px] tracking-wide text-center',
                isDark ? 'text-white/30' : 'text-gray-400'
              )}
            >
              Enable TTS in settings for voice responses
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
