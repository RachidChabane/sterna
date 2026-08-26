/**
 * Hook for speech-to-text functionality in chat.
 *
 * Records audio from the microphone and sends it to the backend for transcription
 * using Deepgram's pre-recorded API. Includes real-time audio level monitoring
 * for waveform visualization.
 */

import { useState, useRef, useCallback, useEffect } from 'react'
import { toast } from 'sonner'
import apiClient, { LONG_RUNNING_TIMEOUT_MS } from '@/api/client'
import { useSettingsStore } from '@/store/settingsStore'

/** Audio level entry with unique ID for stable rendering */
export interface AudioLevelEntry {
  id: number
  level: number
}

interface UseSpeechToTextReturn {
  /** Whether currently recording audio */
  isRecording: boolean
  /** Whether waiting for transcription result */
  isTranscribing: boolean
  /** Current error message, if any */
  error: string | null
  /** Start recording audio */
  startRecording: () => Promise<boolean>
  /** Stop recording and get transcription */
  stopRecording: () => Promise<string | null>
  /** Cancel recording without transcription */
  cancelRecording: () => void
  /** Recording duration in seconds */
  duration: number
  /** Current audio level (0-1) for visualization */
  audioLevel: number
  /** Array of recent audio levels for waveform display (with unique IDs) */
  audioLevels: AudioLevelEntry[]
}

// Audio recording configuration matching voice rooms
const AUDIO_CONSTRAINTS: MediaStreamConstraints = {
  audio: {
    sampleRate: 16000,
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  },
}

// Preferred MIME types in order of preference
const MIME_TYPES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/mp4',
]

// Number of bars in the waveform visualization (enough to fill wide containers)
// More bars + faster updates = smoother movement
const WAVEFORM_BARS = 200

function getSupportedMimeType(): string {
  for (const mimeType of MIME_TYPES) {
    if (MediaRecorder.isTypeSupported(mimeType)) {
      return mimeType
    }
  }
  // Fallback - let browser choose
  return ''
}

// Helper to create initial empty audio levels with unique IDs
function createInitialLevels(): AudioLevelEntry[] {
  return Array.from({ length: WAVEFORM_BARS }, (_, i) => ({ id: i, level: 0 }))
}

export function useSpeechToText(): UseSpeechToTextReturn {
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [duration, setDuration] = useState(0)
  const [audioLevel, setAudioLevel] = useState(0)
  const [audioLevels, setAudioLevels] = useState<AudioLevelEntry[]>(createInitialLevels)

  // Get STT language from settings store
  const sttLanguage = useSettingsStore((state) => state.stt.language)

  // Counter for unique IDs - starts after initial IDs
  const levelIdCounterRef = useRef(WAVEFORM_BARS)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const audioChunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const durationIntervalRef = useRef<number | null>(null)
  const startTimeRef = useRef<number>(0)
  const audioContextRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const animationFrameRef = useRef<number | null>(null)
  const lastLevelUpdateRef = useRef<number>(0)

  // Cleanup audio analysis
  const cleanupAudioAnalysis = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current)
      animationFrameRef.current = null
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {})
      audioContextRef.current = null
    }
    analyserRef.current = null
    setAudioLevel(0)
    setAudioLevels(createInitialLevels())
    levelIdCounterRef.current = WAVEFORM_BARS
  }, [])

  const cleanup = useCallback(() => {
    // Stop duration timer
    if (durationIntervalRef.current) {
      clearInterval(durationIntervalRef.current)
      durationIntervalRef.current = null
    }

    // Cleanup audio analysis
    cleanupAudioAnalysis()

    // Stop media recorder
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.stop()
      } catch {
        // Ignore errors during cleanup
      }
    }
    mediaRecorderRef.current = null

    // Stop all tracks in stream
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }

    // Clear chunks
    audioChunksRef.current = []
  }, [cleanupAudioAnalysis])

  // Setup audio analysis for visualization
  const setupAudioAnalysis = useCallback((stream: MediaStream) => {
    try {
      const audioContext = new AudioContext()
      const analyser = audioContext.createAnalyser()
      const source = audioContext.createMediaStreamSource(stream)

      analyser.fftSize = 256
      analyser.smoothingTimeConstant = 0.5
      source.connect(analyser)

      audioContextRef.current = audioContext
      analyserRef.current = analyser

      const dataArray = new Uint8Array(analyser.frequencyBinCount)

      // Throttle interval - controls the speed of the waveform
      const UPDATE_INTERVAL_MS = 150

      const updateLevels = () => {
        if (!analyserRef.current) return

        analyserRef.current.getByteFrequencyData(dataArray)

        // Calculate overall level (0-1) - lower divisor = more sensitive
        const sum = dataArray.reduce((a, b) => a + b, 0)
        const avg = sum / dataArray.length
        const normalizedLevel = Math.min(1, avg / 120)
        setAudioLevel(normalizedLevel)

        // Throttle waveform updates to match animation speed
        const now = performance.now()
        if (now - lastLevelUpdateRef.current >= UPDATE_INTERVAL_MS) {
          lastLevelUpdateRef.current = now

          // Update waveform levels array - remove oldest (left), add new (right) with unique ID
          setAudioLevels(prev => {
            const newId = levelIdCounterRef.current++
            const newLevels = [...prev.slice(1), { id: newId, level: normalizedLevel }]
            return newLevels
          })
        }

        animationFrameRef.current = requestAnimationFrame(updateLevels)
      }

      updateLevels()
    } catch (err) {
      console.error('Failed to setup audio analysis:', err)
    }
  }, [])

  const startRecording = useCallback(async (): Promise<boolean> => {
    setError(null)
    setDuration(0)
    setAudioLevel(0)
    setAudioLevels(createInitialLevels())
    levelIdCounterRef.current = WAVEFORM_BARS

    // Check for MediaRecorder support
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      const errorMsg = 'Audio recording is not supported in this browser'
      setError(errorMsg)
      toast.error(errorMsg)
      return false
    }

    try {
      // Request microphone permission
      const stream = await navigator.mediaDevices.getUserMedia(AUDIO_CONSTRAINTS)
      streamRef.current = stream

      // Setup audio analysis for visualization
      setupAudioAnalysis(stream)

      // Get supported MIME type
      const mimeType = getSupportedMimeType()
      const options: MediaRecorderOptions = {
        audioBitsPerSecond: 16000,
      }
      if (mimeType) {
        options.mimeType = mimeType
      }

      // Create MediaRecorder
      const mediaRecorder = new MediaRecorder(stream, options)
      mediaRecorderRef.current = mediaRecorder
      audioChunksRef.current = []

      // Collect audio data
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      // Start recording
      mediaRecorder.start(100) // Collect chunks every 100ms
      setIsRecording(true)
      startTimeRef.current = Date.now()

      // Start duration timer
      durationIntervalRef.current = window.setInterval(() => {
        const elapsed = (Date.now() - startTimeRef.current) / 1000
        setDuration(elapsed)
      }, 100)

      return true
    } catch (err) {
      let errorMsg = 'Failed to access microphone'

      if (err instanceof DOMException) {
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
          errorMsg = 'Microphone permission denied. Please allow microphone access in your browser settings.'
        } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
          errorMsg = 'No microphone found. Please connect a microphone and try again.'
        } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
          errorMsg = 'Microphone is in use by another application.'
        }
      }

      setError(errorMsg)
      toast.error(errorMsg)
      cleanup()
      return false
    }
  }, [cleanup, setupAudioAnalysis])

  const stopRecording = useCallback(async (): Promise<string | null> => {
    if (!mediaRecorderRef.current || !isRecording) {
      return null
    }

    setIsRecording(false)

    // Stop duration timer
    if (durationIntervalRef.current) {
      clearInterval(durationIntervalRef.current)
      durationIntervalRef.current = null
    }

    // Cleanup audio analysis
    cleanupAudioAnalysis()

    return new Promise((resolve) => {
      const mediaRecorder = mediaRecorderRef.current!

      mediaRecorder.onstop = async () => {
        // Stop stream tracks
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((track) => track.stop())
          streamRef.current = null
        }

        // Create audio blob
        const chunks = audioChunksRef.current
        if (chunks.length === 0) {
          setError('No audio recorded')
          resolve(null)
          return
        }

        const mimeType = mediaRecorder.mimeType || 'audio/webm'
        const audioBlob = new Blob(chunks, { type: mimeType })
        audioChunksRef.current = []

        // Check minimum duration (0.5 seconds)
        const recordingDuration = (Date.now() - startTimeRef.current) / 1000
        if (recordingDuration < 0.5) {
          setError('Recording too short')
          toast.error('Recording too short. Please speak for at least half a second.')
          resolve(null)
          return
        }

        // Send to backend for transcription
        setIsTranscribing(true)
        setError(null)

        try {
          const formData = new FormData()
          // Use file extension based on MIME type
          const extension = mimeType.includes('webm') ? 'webm' : mimeType.includes('ogg') ? 'ogg' : 'mp4'
          formData.append('audio', audioBlob, `recording.${extension}`)
          // Include language preference from settings
          formData.append('language', sttLanguage)

          const response = await apiClient.post('/llm/transcribe/', formData, {
            // Un-set the instance's default JSON Content-Type so the
            // browser can set the multipart boundary itself.
            headers: { 'Content-Type': undefined },
            timeout: LONG_RUNNING_TIMEOUT_MS,
          }).catch((err) => {
            const data = err?.response?.data
            throw new Error(data?.error || `Transcription failed: ${err?.response?.status ?? 'network error'}`)
          })

          const result = response.data

          if (!result.success) {
            throw new Error(result.error || 'Transcription failed')
          }

          const transcript = result.transcript?.trim() || ''

          if (!transcript) {
            toast.info('No speech detected in the recording')
            resolve(null)
            return
          }

          resolve(transcript)
        } catch (err) {
          const errorMsg = err instanceof Error ? err.message : 'Transcription failed'
          setError(errorMsg)
          toast.error(errorMsg)
          resolve(null)
        } finally {
          setIsTranscribing(false)
        }
      }

      // Stop the recorder to trigger onstop
      mediaRecorder.stop()
    })
  }, [isRecording, cleanupAudioAnalysis, sttLanguage])

  const cancelRecording = useCallback(() => {
    setIsRecording(false)
    setError(null)
    setDuration(0)
    cleanup()
  }, [cleanup])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanup()
    }
  }, [cleanup])

  return {
    isRecording,
    isTranscribing,
    error,
    startRecording,
    stopRecording,
    cancelRecording,
    duration,
    audioLevel,
    audioLevels,
  }
}
