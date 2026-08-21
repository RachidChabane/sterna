/**
 * useVoiceConversation Hook
 *
 * Provides voice conversation functionality for single-chat voice interactions.
 * Combines TTS (Text-to-Speech) and STT (Speech-to-Text) with automatic flow control.
 *
 * Flow:
 * 1. User activates voice mode
 * 2. User clicks mic button and speaks
 * 3. Speech is transcribed and sent as message
 * 4. AI response is automatically read aloud
 * 5. After TTS finishes, user can speak again (or interrupt during TTS)
 *
 * Features:
 * - Voice mode toggle (active/inactive)
 * - Auto-read AI responses when voice mode is active
 * - Interrupt TTS by starting to speak
 * - Uses settings from global settings modal (TTS provider, voice, language, etc.)
 * - Provides voice conversation system prompt for natural dialogue
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { useTTS } from './useTTS'
import { useSpeechToText, type AudioLevelEntry } from './useSpeechToText'
import type { Message } from '@/components/models/types'

/**
 * Voice conversation system prompt that guides the AI to respond naturally
 * for spoken dialogue. This is injected when voice mode is active.
 */
export const VOICE_CONVERSATION_SYSTEM_PROMPT = `You are in a live voice conversation with the user. They are speaking to you through their microphone, and your response will be read aloud to them.

VOICE CONVERSATION GUIDELINES:
- Speak naturally and conversationally, as if talking to a friend
- Use verbal transitions and filler phrases when appropriate ("Sure thing!", "Let me think about that...", "Ok, I'll look into that for you...")
- Keep responses concise but complete - aim for clarity over brevity
- Avoid using markdown formatting, bullet points, numbered lists, or code blocks - these don't translate well to speech
- When you need to perform an action that takes time, acknowledge it verbally ("Just a moment while I search for that...", "Let me check that for you...")
- Use natural pauses by ending sentences clearly
- If something is complex, break it down conversationally rather than listing points
- Respond in the same language the user speaks to you
- Be warm and engaging - this is a conversation, not a text exchange

Remember: Your response will be spoken aloud, so write as you would speak.`

interface UseVoiceConversationOptions {
  /** Called when transcribed text should be sent as a message */
  onSendMessage?: (text: string) => void
  /** Current messages to detect new AI responses */
  messages?: Message[]
  /** Whether the AI is currently generating a response */
  isGenerating?: boolean
}

interface UseVoiceConversationReturn {
  // Voice mode state
  isVoiceModeActive: boolean
  toggleVoiceMode: () => void
  activateVoiceMode: () => void
  deactivateVoiceMode: () => void

  // TTS state (from useTTS)
  isSpeaking: boolean
  isTTSLoading: boolean
  speakText: (text: string) => void
  stopSpeaking: () => void

  // STT state (from useSpeechToText)
  isRecording: boolean
  isTranscribing: boolean
  audioLevels: AudioLevelEntry[]
  startRecording: () => Promise<boolean>
  stopRecording: () => Promise<string | null>
  cancelRecording: () => void

  // Combined state
  voiceState: 'idle' | 'listening' | 'processing' | 'speaking'

  // Manual trigger for reading a message
  readMessage: (content: string) => void

  // Voice conversation system prompt to inject when voice mode is active
  voiceSystemPrompt: string
}

/**
 * Extract plain text content from a message for TTS
 */
function extractTextFromMessage(message: Message): string {
  if (typeof message.content === 'string') {
    return message.content
  }
  // Handle array content (multimodal)
  if (Array.isArray(message.content)) {
    return message.content
      .filter((part: any) => part.type === 'text')
      .map((part: any) => part.text)
      .join('\n')
  }
  return ''
}

export function useVoiceConversation(options: UseVoiceConversationOptions = {}): UseVoiceConversationReturn {
  const { onSendMessage, messages = [], isGenerating = false } = options

  // Voice mode state
  const [isVoiceModeActive, setIsVoiceModeActive] = useState(false)

  // Track last read message index to avoid re-reading
  const lastReadMessageIndexRef = useRef(-1)

  // Track if we should auto-read the next response
  const shouldAutoReadRef = useRef(false)

  // TTS hook
  const {
    speak,
    stop: stopTTS,
    isSpeaking,
    isLoading: isTTSLoading,
    isEnabled: isTTSEnabled,
  } = useTTS()

  // STT hook
  const {
    isRecording,
    isTranscribing,
    startRecording: sttStartRecording,
    stopRecording: sttStopRecording,
    cancelRecording,
    audioLevels,
  } = useSpeechToText()

  // Compute voice state
  const voiceState = (() => {
    if (isSpeaking || isTTSLoading) return 'speaking'
    if (isTranscribing) return 'processing'
    if (isRecording) return 'listening'
    return 'idle'
  })()

  // Toggle voice mode
  const toggleVoiceMode = useCallback(() => {
    setIsVoiceModeActive(prev => {
      const newValue = !prev
      if (!newValue) {
        // Deactivating: stop any ongoing TTS
        stopTTS()
        // Cancel any ongoing recording
        cancelRecording()
      }
      return newValue
    })
  }, [stopTTS, cancelRecording])

  const activateVoiceMode = useCallback(() => {
    setIsVoiceModeActive(true)
  }, [])

  const deactivateVoiceMode = useCallback(() => {
    setIsVoiceModeActive(false)
    stopTTS()
    cancelRecording()
  }, [stopTTS, cancelRecording])

  // Speak text (wrapper that tracks auto-read state)
  const speakText = useCallback((text: string) => {
    if (!isTTSEnabled) {
      
      return
    }
    speak(text)
  }, [speak, isTTSEnabled])

  // Read a message (convenience wrapper)
  const readMessage = useCallback((content: string) => {
    speakText(content)
  }, [speakText])

  // Enhanced start recording that interrupts TTS if speaking
  const startRecording = useCallback(async (): Promise<boolean> => {
    // If TTS is speaking, stop it (interrupt)
    if (isSpeaking || isTTSLoading) {
      
      stopTTS()
    }

    // Set flag to auto-read next response when in voice mode
    if (isVoiceModeActive) {
      shouldAutoReadRef.current = true
    }

    return sttStartRecording()
  }, [isSpeaking, isTTSLoading, stopTTS, sttStartRecording, isVoiceModeActive])

  // Enhanced stop recording that sends message if in voice mode
  const stopRecording = useCallback(async (): Promise<string | null> => {
    const transcript = await sttStopRecording()

    if (transcript && isVoiceModeActive && onSendMessage) {
      // Send the transcribed message
      
      onSendMessage(transcript)
    }

    return transcript
  }, [sttStopRecording, isVoiceModeActive, onSendMessage])

  // Auto-read new AI responses when voice mode is active
  useEffect(() => {
    // Only auto-read when:
    // 1. Voice mode is active
    // 2. Not generating (response is complete)
    // 3. We have a flag to auto-read (user just sent a voice message)
    // 4. TTS is enabled
    if (!isVoiceModeActive || isGenerating || !shouldAutoReadRef.current || !isTTSEnabled) {
      return
    }

    // Find the last assistant message
    const lastAssistantIndex = messages.length - 1
    const lastMessage = messages[lastAssistantIndex]

    if (!lastMessage || lastMessage.role !== 'assistant') {
      return
    }

    // Check if we already read this message
    if (lastAssistantIndex <= lastReadMessageIndexRef.current) {
      return
    }

    // Mark as read and clear auto-read flag
    lastReadMessageIndexRef.current = lastAssistantIndex
    shouldAutoReadRef.current = false

    // Extract and read the message content
    const content = extractTextFromMessage(lastMessage)
    if (content.trim()) {
      
      speakText(content)
    }
  }, [isVoiceModeActive, isGenerating, messages, isTTSEnabled, speakText])

  // Reset state when voice mode is deactivated
  useEffect(() => {
    if (!isVoiceModeActive) {
      shouldAutoReadRef.current = false
    }
  }, [isVoiceModeActive])

  return {
    // Voice mode state
    isVoiceModeActive,
    toggleVoiceMode,
    activateVoiceMode,
    deactivateVoiceMode,

    // TTS state
    isSpeaking,
    isTTSLoading,
    speakText,
    stopSpeaking: stopTTS,

    // STT state
    isRecording,
    isTranscribing,
    audioLevels,
    startRecording,
    stopRecording,
    cancelRecording,

    // Combined state
    voiceState,

    // Manual trigger
    readMessage,

    // Voice conversation system prompt
    voiceSystemPrompt: VOICE_CONVERSATION_SYSTEM_PROMPT,
  }
}

export default useVoiceConversation
