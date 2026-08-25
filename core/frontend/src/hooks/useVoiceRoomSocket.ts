import { useCallback, useEffect, useRef, useState } from 'react'
import type { ServerEvent, ClientEvent } from '../types/voiceRoom'
import useVoiceRoomStore from '../store/voiceRoomStore'
import { useAuthStore } from '../store/authStore'
import { useAuthModalStore } from '../store/authModalStore'
import { getAuthModalVariant } from '../lib/sessionDetection'

// WebSocket connects to Django Channels (same host as API, using ws:// protocol)
const getWebSocketUrl = () => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  // In development, Django runs on port 8000
  const host = import.meta.env.DEV ? 'localhost:8000' : window.location.host
  return `${protocol}//${host}`
}

const VOICE_ROOM_WS_BASE = getWebSocketUrl()

interface VoiceSettings {
  silenceTimeout: number // seconds before processing (1-5)
  interruptionThreshold: number // 0-100, higher = harder to interrupt
  allowInterruptions: boolean
}

interface UseVoiceRoomSocketOptions {
  roomId: string
  token: string
  onConnected?: () => void
  onDisconnected?: () => void
  onError?: (error: string) => void
}

interface UseVoiceRoomSocketReturn {
  connect: () => void
  disconnect: () => void
  startRecording: () => Promise<void>
  stopRecording: () => void
  pause: () => void
  resume: () => void
  skipAgent: () => void
  interrupt: () => void
  endSession: () => void
  updateSettings: (settings: VoiceSettings) => void
  isConnected: boolean
  isRecording: boolean
  error: string | null
}

// Thinking sound player - plays a looping sound while AI is processing
// To enable: place a sound file at /sounds/thinking.mp3 in the public folder
class ThinkingSound {
  private audio: HTMLAudioElement | null = null
  private isPlaying = false
  // Set to true once you've added a sound file to public/sounds/thinking.mp3
  private static readonly SOUND_ENABLED = false
  private static readonly SOUND_PATH = '/sounds/thinking.mp3'

  start() {
    if (this.isPlaying || !ThinkingSound.SOUND_ENABLED) return

    try {
      this.audio = new Audio(ThinkingSound.SOUND_PATH)
      this.audio.loop = true
      this.audio.volume = 0.3 // Adjust volume as needed
      this.audio.play().catch(err => {
        console.warn('Failed to play thinking sound (file may not exist):', err)
      })
      this.isPlaying = true
    } catch (err) {
      console.error('Failed to start thinking sound:', err)
    }
  }

  stop() {
    if (!this.isPlaying || !this.audio) return

    try {
      this.audio.pause()
      this.audio.currentTime = 0
      this.audio = null
      this.isPlaying = false
    } catch (err) {
      console.error('Failed to stop thinking sound:', err)
    }
  }
}

export function useVoiceRoomSocket({
  roomId,
  token,
  onConnected,
  onDisconnected,
  onError,
}: UseVoiceRoomSocketOptions): UseVoiceRoomSocketReturn {
  const wsRef = useRef<WebSocket | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const isPlayingRef = useRef(false)
  const sequenceRef = useRef(0)
  const MAX_AUDIO_QUEUE_SIZE = 50 // Prevent unbounded memory growth
  const currentPlayingAgentRef = useRef<string | null>(null)
  const currentAudioSourceRef = useRef<AudioBufferSourceNode | null>(null) // Track current playing audio for stop
  const scheduledEndTimeRef = useRef<number>(0) // For gapless audio playback scheduling
  const activeSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set()) // Track all active sources for cleanup
  const playbackTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const PLAYBACK_SAFETY_TIMEOUT = 120000 // 2 minutes safety timeout for playback completion
  // Pre-buffering for smooth playback (ElevenLabs streaming)
  // Larger buffer = smoother playback but more latency
  const PREBUFFER_DELAY_MS = 500 // Wait this long before starting playback to buffer chunks
  const decodedBufferQueueRef = useRef<{ buffer: AudioBuffer; agentId: string }[]>([])
  const isBufferingRef = useRef(false)
  const bufferingTimerRef = useRef<NodeJS.Timeout | null>(null)
  // Track agents for which all audio has been sent (agent_audio_complete received)
  const audioCompleteAgentsRef = useRef<Set<string>>(new Set())
  const isMountedRef = useRef(true)
  const isIntentionalCloseRef = useRef(false)
  const pendingTurnEventRef = useRef<ServerEvent | null>(null)
  const thinkingSoundRef = useRef<ThinkingSound | null>(null)
  // Client-side VAD for interruption detection during agent playback
  const lastInterruptSignalRef = useRef<number>(0)
  const lastVadLogRef = useRef<number>(0) // For debug logging
  const INTERRUPT_COOLDOWN_MS = 1500 // Minimum time between interrupt signals
  const INTERRUPT_THRESHOLD = 0.18 // Audio level threshold for interruption (0-1)

  const [error, setError] = useState<string | null>(null)

  const {
    isConnected,
    isRecording,
    setConnected,
    setRecording,
    setAudioLevel,
    handleServerEvent,
    clearSession,
    setStreamingMessage,
    setLiveTranscriptAudioStart,
    clearLiveTranscript,
    setWaitingForNextAudio,
  } = useVoiceRoomStore()

  // Send a message through WebSocket
  const sendMessage = useCallback((event: ClientEvent) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(event))
    }
  }, [])

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }

    // Don't connect if component is unmounted (Strict Mode double-invoke)
    if (!isMountedRef.current) {
      return
    }

    // Don't connect if roomId is not set
    if (!roomId) {
      console.warn('[useVoiceRoomSocket] Cannot connect: roomId is undefined')
      return
    }

    const wsUrl = `${VOICE_ROOM_WS_BASE}/ws/voice-rooms/${roomId}/?token=${encodeURIComponent(token)}`
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      // Only update state if still mounted
      if (!isMountedRef.current) {
        ws.close()
        return
      }
      
      setConnected(true)
      setError(null)
      onConnected?.()
    }

    ws.onclose = (event) => {
      // Only log if not an intentional close (e.g., React StrictMode cleanup)
      if (!isIntentionalCloseRef.current) {
        
      }
      // Only update state if still mounted
      if (isMountedRef.current) {
        setConnected(false)
        setRecording(false)
        onDisconnected?.()

        // Handle auth-related close codes (4001 = unauthorized, 4003 = forbidden)
        if (event.code === 4001 || event.code === 4003) {
          
          // Clear auth state
          useAuthStore.setState({
            user: null,
            isAuthenticated: false,
            isLoading: false
          })
          // Open auth modal
          const variant = getAuthModalVariant()
          const returnUrl = window.location.pathname + window.location.search
          useAuthModalStore.getState().openModal(variant, returnUrl)
        }
      }
    }

    ws.onerror = (event) => {
      // Suppress errors from intentional closes (e.g., React StrictMode double-invoke)
      if (isIntentionalCloseRef.current) {
        return
      }
      console.error('Voice room WebSocket error:', event)
      // Only update state if still mounted
      if (isMountedRef.current) {
        const errorMsg = 'WebSocket connection error'
        setError(errorMsg)
        onError?.(errorMsg)
      }
    }

    ws.onmessage = (event) => {
      try {
        const serverEvent: ServerEvent = JSON.parse(event.data)

        // Defer 'turn' events while audio is playing to avoid premature status change
        if (serverEvent.type === 'turn' && serverEvent.speaker === 'user') {
          // If turn event arrives and we still have a "current" agent, send completion for them
          // This handles the case where playback tracking failed
          if (currentPlayingAgentRef.current) {
            
            sendMessage({
              type: 'audio_playback_complete',
              agent_id: currentPlayingAgentRef.current,
            })
            if (playbackTimeoutRef.current) {
              clearTimeout(playbackTimeoutRef.current)
              playbackTimeoutRef.current = null
            }
            currentPlayingAgentRef.current = null
            isPlayingRef.current = false
          }

          if (isPlayingRef.current || decodedBufferQueueRef.current.length > 0) {
            
            pendingTurnEventRef.current = serverEvent
            // Safety timeout: process turn event after 30s max even if playback detection fails
            setTimeout(() => {
              if (pendingTurnEventRef.current) {
                
                handleServerEvent(pendingTurnEventRef.current)
                pendingTurnEventRef.current = null
              }
            }, 30000)
          } else {
            handleServerEvent(serverEvent)
          }
        } else {
          handleServerEvent(serverEvent)
        }

        // Handle thinking sound - start when agent is thinking, stop when audio arrives
        if (serverEvent.type === 'agent_state') {
          if (serverEvent.state === 'thinking') {
            // Start thinking sound
            if (!thinkingSoundRef.current) {
              thinkingSoundRef.current = new ThinkingSound()
            }
            thinkingSoundRef.current.start()
            
          } else if (serverEvent.state === 'speaking' || serverEvent.state === 'done') {
            // Stop thinking sound when agent starts speaking or is done
            thinkingSoundRef.current?.stop()
          }
        }

        // Handle audio playback for agent audio events
        if (serverEvent.type === 'agent_audio') {
          // Stop thinking sound when first audio chunk arrives
          thinkingSoundRef.current?.stop()
          // Clear waiting state - audio has arrived, stop showing thinking indicator
          setWaitingForNextAudio(false)

          // Django sends 'data', FastAPI used 'audio_data'
          const audioData = serverEvent.data || serverEvent.audio_data
          const agentId = serverEvent.agent_id
          const audioFormat = serverEvent.format || 'mp3'
          if (audioData && agentId) {
            queueAudioForPlayback(audioData, agentId, audioFormat)
          }
        }

        // Handle stop_audio - stop current audio and clear queue immediately
        if (serverEvent.type === 'stop_audio') {
          
          thinkingSoundRef.current?.stop()
          if (playbackTimeoutRef.current) {
            clearTimeout(playbackTimeoutRef.current)
            playbackTimeoutRef.current = null
          }
          // Clear buffering timer
          if (bufferingTimerRef.current) {
            clearTimeout(bufferingTimerRef.current)
            bufferingTimerRef.current = null
          }
          isBufferingRef.current = false
          // Stop all active audio sources (gapless playback may have multiple scheduled)
          activeSourcesRef.current.forEach(source => {
            try {
              source.stop()
            } catch {
              // Ignore error if already stopped
            }
          })
          activeSourcesRef.current.clear()
          currentAudioSourceRef.current = null
          scheduledEndTimeRef.current = 0
          decodedBufferQueueRef.current = []
          isPlayingRef.current = false
          currentPlayingAgentRef.current = null
          audioCompleteAgentsRef.current.clear()
          clearLiveTranscript()
          setWaitingForNextAudio(false)
        }

        // Handle agent_audio_complete - backend finished sending all audio for an agent
        if (serverEvent.type === 'agent_audio_complete') {
          const agentId = serverEvent.agent_id
          
          audioCompleteAgentsRef.current.add(agentId)
          // If we're not playing and queue is empty, we can now send completion
          if (!isPlayingRef.current && decodedBufferQueueRef.current.length === 0 && activeSourcesRef.current.size === 0 && currentPlayingAgentRef.current === agentId) {
            
            sendMessage({
              type: 'audio_playback_complete',
              agent_id: agentId,
            })
            // Show thinking state while waiting for next agent's audio (OpenAI TTS)
            setWaitingForNextAudio(true)
            audioCompleteAgentsRef.current.delete(agentId)
            currentPlayingAgentRef.current = null
            scheduledEndTimeRef.current = 0
            if (playbackTimeoutRef.current) {
              clearTimeout(playbackTimeoutRef.current)
              playbackTimeoutRef.current = null
            }
            processPendingTurnEvent()
          }
        }

        // Handle interruption - stop audio playback immediately
        if (serverEvent.type === 'interrupted') {
          
          // Stop thinking sound
          thinkingSoundRef.current?.stop()
          // Clear playback safety timeout
          if (playbackTimeoutRef.current) {
            clearTimeout(playbackTimeoutRef.current)
            playbackTimeoutRef.current = null
          }
          // Clear buffering timer
          if (bufferingTimerRef.current) {
            clearTimeout(bufferingTimerRef.current)
            bufferingTimerRef.current = null
          }
          isBufferingRef.current = false
          // Stop all active audio sources (gapless playback may have multiple scheduled)
          activeSourcesRef.current.forEach(source => {
            try {
              source.stop()
            } catch {
              // Ignore error if already stopped
            }
          })
          activeSourcesRef.current.clear()
          currentAudioSourceRef.current = null
          scheduledEndTimeRef.current = 0
          // Clear the audio queue
          decodedBufferQueueRef.current = []
          isPlayingRef.current = false
          currentPlayingAgentRef.current = null
          audioCompleteAgentsRef.current.clear()
          // Clear streaming message and live transcript
          setStreamingMessage(null)
          clearLiveTranscript()
          // Process any pending turn event
          if (pendingTurnEventRef.current) {
            handleServerEvent(pendingTurnEventRef.current)
            pendingTurnEventRef.current = null
          }
        }
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err)
      }
    }

    wsRef.current = ws
  }, [roomId, token, setConnected, setRecording, handleServerEvent, onConnected, onDisconnected, onError, setStreamingMessage, clearLiveTranscript])

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    isIntentionalCloseRef.current = true
    // Stop thinking sound
    thinkingSoundRef.current?.stop()
    // Clear playback safety timeout
    if (playbackTimeoutRef.current) {
      clearTimeout(playbackTimeoutRef.current)
      playbackTimeoutRef.current = null
    }
    // Clear buffering timer
    if (bufferingTimerRef.current) {
      clearTimeout(bufferingTimerRef.current)
      bufferingTimerRef.current = null
    }
    isBufferingRef.current = false
    // Clear audio queue to free memory
    decodedBufferQueueRef.current = []
    isPlayingRef.current = false
    currentPlayingAgentRef.current = null
    audioCompleteAgentsRef.current.clear()
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    stopRecording()
    clearSession()
    // Reset flag after a tick to allow error handlers to check it
    setTimeout(() => {
      isIntentionalCloseRef.current = false
    }, 0)
  }, [clearSession])

  // Process pending turn event when audio playback is complete
  const processPendingTurnEvent = useCallback(() => {
    
    if (pendingTurnEventRef.current && !isPlayingRef.current && decodedBufferQueueRef.current.length === 0) {
      
      handleServerEvent(pendingTurnEventRef.current)
      pendingTurnEventRef.current = null
    }
  }, [handleServerEvent])

  // Play next audio from queue - use ref to avoid circular dependency
  const playNextAudioRef = useRef<(() => Promise<void>) | undefined>(undefined)

  const playNextAudio = useCallback(async () => {
    // Check if we have decoded audio to schedule (use decodedBufferQueueRef for pre-decoded audio)
    if (decodedBufferQueueRef.current.length === 0) {
      // No more audio to play - but only send completion if backend confirmed all audio sent
      // AND all scheduled audio has finished playing
      if (!isPlayingRef.current && currentPlayingAgentRef.current && activeSourcesRef.current.size === 0) {
        const agentId = currentPlayingAgentRef.current
        // Only send completion if we received agent_audio_complete for this agent
        if (audioCompleteAgentsRef.current.has(agentId)) {
          
          // Clear safety timeout since we're completing normally
          if (playbackTimeoutRef.current) {
            clearTimeout(playbackTimeoutRef.current)
            playbackTimeoutRef.current = null
          }
          sendMessage({
            type: 'audio_playback_complete',
            agent_id: agentId,
          })
          // Show thinking state while waiting for next agent's audio (OpenAI TTS)
          setWaitingForNextAudio(true)
          audioCompleteAgentsRef.current.delete(agentId)
          currentPlayingAgentRef.current = null
          scheduledEndTimeRef.current = 0
          // Process pending turn event
          processPendingTurnEvent()
        } else {
          
        }
      }
      return
    }

    // Process all available pre-decoded chunks for gapless playback
    while (decodedBufferQueueRef.current.length > 0) {
      const { buffer: audioBuffer, agentId } = decodedBufferQueueRef.current.shift()!

      // Track which agent's audio we're playing
      const previousAgent = currentPlayingAgentRef.current
      const isNewAgent = previousAgent !== agentId
      if (previousAgent && isNewAgent) {
        // Agent changed - only send completion if we received agent_audio_complete for previous agent
        if (audioCompleteAgentsRef.current.has(previousAgent)) {
          
          // Clear previous agent's safety timeout
          if (playbackTimeoutRef.current) {
            clearTimeout(playbackTimeoutRef.current)
            playbackTimeoutRef.current = null
          }
          sendMessage({
            type: 'audio_playback_complete',
            agent_id: previousAgent,
          })
          audioCompleteAgentsRef.current.delete(previousAgent)
          // Reset scheduled time for new agent
          scheduledEndTimeRef.current = 0
        } else {
          
        }
      }
      currentPlayingAgentRef.current = agentId

      // Set audio start time for live transcript sync when new agent starts
      if (isNewAgent || !previousAgent) {
        setLiveTranscriptAudioStart(Date.now())
      }

      // Safety timeout: Detect if audio playback is stuck
      if (playbackTimeoutRef.current) {
        clearTimeout(playbackTimeoutRef.current)
      }
      const currentAgentForTimeout = agentId
      playbackTimeoutRef.current = setTimeout(() => {
        if (currentPlayingAgentRef.current === currentAgentForTimeout) {
          console.warn(`[useVoiceRoomSocket] Safety timeout: no audio progress for 30s, sending completion for agent ${currentAgentForTimeout}`)
          sendMessage({
            type: 'audio_playback_complete',
            agent_id: currentAgentForTimeout,
          })
          currentPlayingAgentRef.current = null
          isPlayingRef.current = false
          scheduledEndTimeRef.current = 0
          activeSourcesRef.current.clear()
          playNextAudioRef.current?.()
        }
      }, PLAYBACK_SAFETY_TIMEOUT)

      try {
        if (!audioContextRef.current || audioContextRef.current.state === 'closed') {
          audioContextRef.current = new AudioContext()
          scheduledEndTimeRef.current = 0
        }

        // Resume AudioContext if suspended (browser autoplay policy)
        if (audioContextRef.current.state === 'suspended') {
          await audioContextRef.current.resume()
        }

        // Audio is already decoded in queueAudioForPlayback - use the pre-decoded buffer directly
        const source = audioContextRef.current.createBufferSource()
        source.buffer = audioBuffer
        source.connect(audioContextRef.current.destination)

        // Track current audio source for interruption
        currentAudioSourceRef.current = source
        activeSourcesRef.current.add(source)
        isPlayingRef.current = true

        // Calculate start time for gapless playback
        const currentTime = audioContextRef.current.currentTime
        const startTime = Math.max(currentTime, scheduledEndTimeRef.current)
        const gap = startTime - currentTime

        // Schedule next chunk to start exactly when this one ends
        scheduledEndTimeRef.current = startTime + audioBuffer.duration

        // Log scheduling info
        const durationMs = Math.round(audioBuffer.duration * 1000)
        

        source.onended = () => {
          activeSourcesRef.current.delete(source)
          if (source === currentAudioSourceRef.current) {
            currentAudioSourceRef.current = null
          }
          // Check if all scheduled audio has finished
          if (activeSourcesRef.current.size === 0) {
            isPlayingRef.current = false
            // Try to play any newly queued audio or handle completion
            playNextAudioRef.current?.()
          }
        }

        // Start at scheduled time for gapless playback
        source.start(startTime)
      } catch (err) {
        console.error('Failed to play audio:', err)
        // Continue with next chunk
      }
    }
  }, [processPendingTurnEvent, sendMessage, setLiveTranscriptAudioStart, setWaitingForNextAudio])

  // Keep the ref updated with the latest function
  playNextAudioRef.current = playNextAudio

  // Convert PCM 24kHz 16-bit signed integer samples to AudioBuffer
  const pcmToAudioBuffer = useCallback((pcmData: Uint8Array, sampleRate: number): AudioBuffer | null => {
    if (!audioContextRef.current) return null

    // PCM is 16-bit signed integer, 2 bytes per sample
    const numSamples = pcmData.length / 2
    const audioBuffer = audioContextRef.current.createBuffer(1, numSamples, sampleRate)
    const channelData = audioBuffer.getChannelData(0)

    // Convert 16-bit signed integers to Float32 (-1.0 to 1.0)
    const dataView = new DataView(pcmData.buffer, pcmData.byteOffset, pcmData.byteLength)
    for (let i = 0; i < numSamples; i++) {
      // Read 16-bit signed integer (little-endian)
      const sample = dataView.getInt16(i * 2, true)
      // Convert to float (-1.0 to 1.0)
      channelData[i] = sample / 32768.0
    }

    return audioBuffer
  }, [])

  // Queue audio for playback with pre-buffering for ElevenLabs streaming
  const queueAudioForPlayback = useCallback(async (base64Audio: string, agentId: string, format: string = 'mp3') => {
    // Decode base64 to ArrayBuffer
    const binaryString = atob(base64Audio)
    const bytes = new Uint8Array(binaryString.length)
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i)
    }

    // Skip audio chunks that are too small
    const minSize = format.startsWith('pcm') ? 200 : 100  // PCM chunks can be larger
    if (bytes.length < minSize) {
      console.warn(`[useVoiceRoomSocket] Skipping tiny audio chunk (${bytes.length} bytes, format=${format})`)
      return
    }

    // Detect if this is a large chunk (OpenAI MP3 - full audio) or streaming (ElevenLabs)
    // OpenAI sends full MP3 at once (usually > 50KB), ElevenLabs streams smaller chunks
    const isLargeChunk = format === 'mp3' && bytes.length > 50000

    // Ensure AudioContext exists
    if (!audioContextRef.current || audioContextRef.current.state === 'closed') {
      audioContextRef.current = new AudioContext()
      scheduledEndTimeRef.current = 0
    }

    // Resume AudioContext if suspended
    if (audioContextRef.current.state === 'suspended') {
      await audioContextRef.current.resume()
    }

    // Decode audio based on format
    try {
      let audioBuffer: AudioBuffer | null = null

      if (format.startsWith('pcm_')) {
        // PCM format: pcm_24000 means 24kHz sample rate
        const sampleRate = parseInt(format.split('_')[1]) || 24000
        audioBuffer = pcmToAudioBuffer(bytes, sampleRate)
        if (!audioBuffer) {
          console.error('Failed to create AudioBuffer from PCM')
          return
        }
      } else {
        // MP3 or other formats: use decodeAudioData
        const audioDataCopy = bytes.buffer.slice(0)
        audioBuffer = await audioContextRef.current.decodeAudioData(audioDataCopy)
      }

      // Log chunk info for debugging
      const durationMs = Math.round(audioBuffer.duration * 1000)
      

      // Prevent memory leak: drop oldest decoded buffers if queue is too large
      if (decodedBufferQueueRef.current.length >= MAX_AUDIO_QUEUE_SIZE) {
        console.warn(`[useVoiceRoomSocket] Decoded buffer queue full, dropping oldest`)
        decodedBufferQueueRef.current.shift()
      }

      decodedBufferQueueRef.current.push({ buffer: audioBuffer, agentId })

      if (isLargeChunk) {
        // OpenAI: Large MP3 chunk, play immediately (no buffering needed)
        
        // Cancel any buffering timer
        if (bufferingTimerRef.current) {
          clearTimeout(bufferingTimerRef.current)
          bufferingTimerRef.current = null
        }
        isBufferingRef.current = false
        playNextAudioRef.current?.()
      } else {
        // Streaming audio (ElevenLabs PCM or small MP3): use pre-buffering for smooth playback
        if (!isPlayingRef.current && !isBufferingRef.current && activeSourcesRef.current.size === 0) {
          // Start buffering timer on first chunk
          isBufferingRef.current = true
          
          bufferingTimerRef.current = setTimeout(() => {
            isBufferingRef.current = false
            
            playNextAudioRef.current?.()
          }, PREBUFFER_DELAY_MS)
        } else if (isPlayingRef.current) {
          // Already playing - schedule the new chunk immediately for gapless playback
          playNextAudioRef.current?.()
        }
      }
    } catch (err) {
      console.error('Failed to decode audio chunk:', err, 'format:', format)
    }
  }, [pcmToAudioBuffer])

  // Start recording from microphone
  const startRecording = useCallback(async () => {
    
    try {
      
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      

      // Set up audio context for level monitoring
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContext()
      }
      const source = audioContextRef.current.createMediaStreamSource(stream)
      analyserRef.current = audioContextRef.current.createAnalyser()
      analyserRef.current.fftSize = 256
      source.connect(analyserRef.current)

      // Monitor audio levels
      const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount)
      const updateLevel = () => {
        if (analyserRef.current && mediaRecorderRef.current?.state === 'recording') {
          analyserRef.current.getByteFrequencyData(dataArray)
          const average = dataArray.reduce((a, b) => a + b) / dataArray.length
          const normalizedLevel = average / 255 // Normalize to 0-1
          setAudioLevel(normalizedLevel)

          // Client-side VAD: Detect user speech during agent playback for interruption
          // This is a backup for when Deepgram's VAD doesn't detect speech (e.g., when
          // the user's microphone picks up the AI's audio output)
          const now = Date.now()
          // Log audio levels periodically for debugging (always, not just during playback)
          if (now - lastVadLogRef.current > 2000) {
            
            lastVadLogRef.current = now
          }
          if (isPlayingRef.current) {
            if (normalizedLevel > INTERRUPT_THRESHOLD) {
              if (now - lastInterruptSignalRef.current > INTERRUPT_COOLDOWN_MS) {
                
                lastInterruptSignalRef.current = now
                sendMessage({ type: 'user_interrupt' })
              }
            }
          }

          requestAnimationFrame(updateLevel)
        }
      }

      // Set up MediaRecorder
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'

      const mediaRecorder = new MediaRecorder(stream, {
        mimeType,
        audioBitsPerSecond: 16000,
      })

      mediaRecorder.ondataavailable = async (event) => {
        if (event.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
          // Convert blob to base64
          const reader = new FileReader()
          reader.onload = () => {
            const base64 = (reader.result as string).split(',')[1]
            sendMessage({
              type: 'audio_chunk',
              data: base64,
              sequence: sequenceRef.current++,
            })
          }
          reader.readAsDataURL(event.data)
        }
      }

      
      mediaRecorder.start(100) // Send chunks every 100ms
      mediaRecorderRef.current = mediaRecorder
      
      setRecording(true)
      updateLevel()
      
    } catch (err) {
      console.error('[useVoiceRoomSocket] Failed to start recording:', err)
      const errorMsg = err instanceof Error ? err.message : 'Failed to access microphone'
      setError(errorMsg)
      onError?.(errorMsg)
    }
  }, [setRecording, setAudioLevel, sendMessage, onError])

  // Stop recording (mute) - does NOT signal end of speaking
  // End of speaking is auto-detected by Deepgram's VAD/utterance detection
  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop()
      mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop())
      mediaRecorderRef.current = null
    }
    setRecording(false)
    setAudioLevel(0)
    sequenceRef.current = 0
    // Note: We don't send 'end_speaking' here anymore
    // Deepgram's utterance_end_ms handles detecting when the user stops speaking
  }, [setRecording, setAudioLevel])

  // Control actions
  const pause = useCallback(() => {
    sendMessage({ type: 'pause' })
  }, [sendMessage])

  const resume = useCallback(() => {
    sendMessage({ type: 'resume' })
  }, [sendMessage])

  const skipAgent = useCallback(() => {
    sendMessage({ type: 'skip_agent' })
  }, [sendMessage])

  // Manual interrupt - stops AI and gives control back to user
  const interrupt = useCallback(() => {
    
    // Stop any playing audio
    if (currentAudioSourceRef.current) {
      try {
        currentAudioSourceRef.current.stop()
      } catch {
        // Ignore if already stopped
      }
      currentAudioSourceRef.current = null
    }
    // Clear buffering timer
    if (bufferingTimerRef.current) {
      clearTimeout(bufferingTimerRef.current)
      bufferingTimerRef.current = null
    }
    isBufferingRef.current = false
    // Clear audio queue
    decodedBufferQueueRef.current = []
    isPlayingRef.current = false
    currentPlayingAgentRef.current = null
    // Clear streaming message
    setStreamingMessage(null)
    // Send interrupt to backend
    sendMessage({ type: 'user_interrupt' })
  }, [sendMessage, setStreamingMessage])

  const endSession = useCallback(() => {
    sendMessage({ type: 'end_session' })
    disconnect()
  }, [sendMessage, disconnect])

  // Update voice settings
  const updateSettings = useCallback((settings: VoiceSettings) => {
    sendMessage({
      type: 'settings',
      silence_timeout: settings.silenceTimeout,
      interruption_threshold: settings.interruptionThreshold,
      allow_interruptions: settings.allowInterruptions,
    })
  }, [sendMessage])

  // Cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
      // Stop thinking sound
      thinkingSoundRef.current?.stop()
      // Clear buffering timer
      if (bufferingTimerRef.current) {
        clearTimeout(bufferingTimerRef.current)
        bufferingTimerRef.current = null
      }
      // Clear audio queue to prevent memory leak
      decodedBufferQueueRef.current = []
      isPlayingRef.current = false
      disconnect()
      if (audioContextRef.current) {
        audioContextRef.current.close()
        audioContextRef.current = null
      }
    }
  }, [disconnect])

  return {
    connect,
    disconnect,
    startRecording,
    stopRecording,
    pause,
    resume,
    skipAgent,
    interrupt,
    endSession,
    updateSettings,
    isConnected,
    isRecording,
    error,
  }
}
