import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import axios from 'axios'
import apiClient, { LONG_RUNNING_TIMEOUT_MS } from '../api/client'
import type {
  VoiceRoom,
  VoiceRoomState,
  VoiceRoomMessage,
  VoiceInfo,
  RoomStatus,
  CreateRoomRequest,
  UpdateRoomRequest,
  ServerEvent,
  TTSModelInfo,
  TTSProvider,
  TTSProviderId,
} from '../types/voiceRoom'
import { createUserScopedStorage } from '../lib/userScopedStorage'
import { generateUUID } from '../lib/utils'

// apiClient's response interceptor already shows the session-expired modal
// (via handleUnauthorized in ../api/client) and retries once through the
// refresh-token flow before giving up — this only needs to recognize an
// unrecoverable 401 so the call sites below skip layering a generic
// "failed to X" error state on top of that modal.
const isUnauthorized = (error: unknown): boolean =>
  axios.isAxiosError(error) && error.response?.status === 401

interface VoiceRoomStore {
  // Room management state
  rooms: VoiceRoom[]
  currentRoom: VoiceRoom | null
  roomsLoading: boolean
  roomsError: string | null

  // Voice catalog state
  voices: VoiceInfo[]
  voicesLoading: boolean
  recommendedVoices: VoiceInfo[]

  // TTS providers state
  ttsProviders: TTSProvider[]
  ttsProvidersLoaded: boolean

  // TTS models state
  ttsModels: TTSModelInfo[]
  ttsModelsLoading: boolean
  ttsModelsLoaded: boolean

  // Session state
  sessionState: VoiceRoomState | null
  isConnected: boolean
  isRecording: boolean
  isMuted: boolean

  // Audio state
  audioLevel: number
  currentTranscript: string

  // Streaming message state (for real-time transcript display)
  streamingMessage: {
    agent_id: string
    agent_name: string
    content: string
  } | null

  // Live transcript alignment data (for synced captions)
  liveTranscript: {
    agentId: string
    text: string
    words: Array<{ word: string; startMs: number; endMs: number }>
    audioStartTime: number // timestamp when audio playback started
    estimated?: boolean // true for OpenAI (skip word highlighting, keep line animation)
  } | null

  // Track waiting state between agents (for OpenAI TTS - show thinking until next agent's audio arrives)
  waitingForNextAudio: boolean

  // Recent rooms for quick access
  recentRooms: string[]

  // Cache tracking
  lastRoomsFetchTime: number

  // Room CRUD actions
  fetchRooms: (forceRefresh?: boolean) => Promise<void>
  createRoom: (request: CreateRoomRequest) => Promise<VoiceRoom | null>
  updateRoom: (roomId: string, request: UpdateRoomRequest) => Promise<VoiceRoom | null>
  deleteRoom: (roomId: string) => Promise<boolean>
  setCurrentRoom: (room: VoiceRoom | null) => void

  // Voice actions
  fetchVoices: (provider?: TTSProviderId) => Promise<void>
  fetchRecommendedVoices: (provider?: TTSProviderId) => Promise<void>
  fetchTTSModels: (provider?: TTSProviderId) => Promise<void>
  fetchTTSProviders: () => Promise<void>

  // Session actions
  setSessionState: (state: VoiceRoomState | null) => void
  updateSessionStatus: (status: RoomStatus) => void
  setCurrentSpeaker: (speaker: string | null) => void
  addMessage: (message: VoiceRoomMessage) => void
  updateLastMessage: (text: string, isFinal: boolean) => void
  setDetectedLanguage: (language: string) => void

  // Connection actions
  setConnected: (connected: boolean) => void
  setRecording: (recording: boolean) => void
  setMuted: (muted: boolean) => void

  // Audio actions
  setAudioLevel: (level: number) => void
  setCurrentTranscript: (transcript: string) => void

  // Streaming message actions
  setStreamingMessage: (message: { agent_id: string; agent_name: string; content: string } | null) => void
  appendToStreamingMessage: (text: string) => void

  // Live transcript actions
  setLiveTranscript: (transcript: { agentId: string; text: string; words: Array<{ word: string; startMs: number; endMs: number }>; audioStartTime: number; estimated?: boolean } | null) => void
  appendLiveTranscriptWords: (agentId: string, text: string, words: Array<{ word: string; startMs: number; endMs: number }>, estimated?: boolean) => void
  setLiveTranscriptAudioStart: (timestamp: number) => void
  clearLiveTranscript: () => void

  // Waiting for audio state (OpenAI TTS)
  setWaitingForNextAudio: (waiting: boolean) => void

  // Event handling
  handleServerEvent: (event: ServerEvent) => void

  // Conversation persistence
  fetchConversation: (roomId: string) => Promise<VoiceRoomMessage[]>
  clearConversation: (roomId: string) => Promise<void>

  // AI Room Generation
  generateRoom: (description: string, provider?: string) => Promise<GeneratedRoomConfig | null>
  isGeneratingRoom: boolean

  // Utility
  addRecentRoom: (roomId: string) => void
  clearSession: () => void
  reset: () => void
}

// Generated room configuration from AI
interface GeneratedRoomConfig {
  name: string
  description: string
  language: string
  agents: Array<{
    display_name: string
    model_id: string
    system_prompt: string
    voice_id: string
    voice_name: string
    order: number
    color: string
    voice_settings: {
      stability: number
      similarity_boost: number
      speed: number
    }
  }>
}

// Django backend handles all voice room features (rooms, agents, voices, WebSocket)
// Path is relative to apiClient's `/api` baseURL.
const BACKEND_API_BASE = '/voice-rooms'
const MAX_RECENT_ROOMS = 5

const useVoiceRoomStore = create<VoiceRoomStore>()(
  persist(
    (set, get) => ({
      // Initial state
      rooms: [],
      currentRoom: null,
      roomsLoading: false,
      roomsError: null,

      voices: [],
      voicesLoading: false,
      recommendedVoices: [],

      ttsProviders: [],
      ttsProvidersLoaded: false,

      ttsModels: [],
      ttsModelsLoading: false,
      ttsModelsLoaded: false,

      sessionState: null,
      isConnected: false,
      isRecording: false,
      isMuted: false,

      audioLevel: 0,
      currentTranscript: '',
      streamingMessage: null,
      liveTranscript: null,
      waitingForNextAudio: false,
      isGeneratingRoom: false,

      recentRooms: [],

      lastRoomsFetchTime: 0,

      // Fetch all rooms for current user (from Django backend)
      fetchRooms: async (forceRefresh = false) => {
        const state = get()

        // Cache validity: 5 minutes
        const CACHE_TTL = 5 * 60 * 1000
        const isCacheValid = Date.now() - state.lastRoomsFetchTime < CACHE_TTL

        // Skip fetch if cache is valid and not forcing refresh
        if (!forceRefresh && state.rooms.length > 0 && isCacheValid && !state.roomsLoading) {
          return
        }

        set({ roomsLoading: true, roomsError: null })
        try {
          const response = await apiClient.get(`${BACKEND_API_BASE}/rooms/`)
          const rooms = response.data
          set({ rooms: rooms || [], roomsLoading: false, lastRoomsFetchTime: Date.now() })
        } catch (error) {
          if (isUnauthorized(error)) return
          set({
            roomsError: error instanceof Error ? error.message : 'Failed to fetch rooms',
            roomsLoading: false,
          })
        }
      },

      // Create a new room (in Django backend)
      createRoom: async (request) => {
        try {
          const response = await apiClient.post(`${BACKEND_API_BASE}/rooms/`, request)
          const room = response.data
          set((state) => ({ rooms: [room, ...state.rooms] }))
          return room
        } catch (error) {
          if (isUnauthorized(error)) return null
          set({
            roomsError: error instanceof Error ? error.message : 'Failed to create room',
          })
          return null
        }
      },

      // Update an existing room (in Django backend)
      updateRoom: async (roomId, request) => {
        try {
          const response = await apiClient.put(`${BACKEND_API_BASE}/rooms/${roomId}/`, request)
          const room = response.data
          set((state) => ({
            rooms: state.rooms.map((r) => (r.id === roomId ? room : r)),
            currentRoom: state.currentRoom?.id === roomId ? room : state.currentRoom,
          }))
          return room
        } catch (error) {
          if (isUnauthorized(error)) return null
          set({
            roomsError: error instanceof Error ? error.message : 'Failed to update room',
          })
          return null
        }
      },

      // Delete a room (in Django backend)
      deleteRoom: async (roomId) => {
        try {
          await apiClient.delete(`${BACKEND_API_BASE}/rooms/${roomId}/`)
          set((state) => ({
            rooms: state.rooms.filter((r) => r.id !== roomId),
            currentRoom: state.currentRoom?.id === roomId ? null : state.currentRoom,
          }))
          return true
        } catch (error) {
          if (isUnauthorized(error)) return false
          set({
            roomsError: error instanceof Error ? error.message : 'Failed to delete room',
          })
          return false
        }
      },

      setCurrentRoom: (room) => {
        set({ currentRoom: room })
        if (room) {
          get().addRecentRoom(room.id)
        }
      },

      // Fetch TTS providers (from Django backend)
      fetchTTSProviders: async () => {
        const state = get()
        if (state.ttsProvidersLoaded) return

        try {
          const response = await apiClient.get(`${BACKEND_API_BASE}/tts-providers/`)
          set({ ttsProviders: response.data, ttsProvidersLoaded: true })
        } catch (error) {
          console.error('Failed to fetch TTS providers:', error)
        }
      },

      // Fetch available voices (from Django backend, supports provider filter)
      fetchVoices: async (provider?: TTSProviderId) => {
        set({ voicesLoading: true })
        try {
          const response = await apiClient.get(`${BACKEND_API_BASE}/voices/`, {
            params: provider ? { provider } : undefined,
          })
          set({ voices: response.data, voicesLoading: false })
        } catch (error) {
          console.error('Failed to fetch voices:', error)
          set({ voicesLoading: false })
        }
      },

      // Fetch recommended voices (from Django backend, supports provider filter)
      fetchRecommendedVoices: async (provider?: TTSProviderId) => {
        try {
          const response = await apiClient.get(`${BACKEND_API_BASE}/voices/recommended/`, {
            params: provider ? { provider } : undefined,
          })
          set({ recommendedVoices: response.data })
        } catch (error) {
          console.error('Failed to fetch recommended voices:', error)
        }
      },

      // Fetch TTS models with languages (from Django backend, supports provider filter)
      fetchTTSModels: async (provider?: TTSProviderId) => {
        set({ ttsModelsLoading: true, ttsModelsLoaded: false })
        try {
          const response = await apiClient.get(`${BACKEND_API_BASE}/tts-models/`, {
            params: provider ? { provider } : undefined,
          })
          set({ ttsModels: response.data, ttsModelsLoading: false, ttsModelsLoaded: true })
        } catch (error) {
          console.error('Failed to fetch TTS models:', error)
          set({ ttsModelsLoading: false })
        }
      },

      // Session state management
      setSessionState: (state) => set({ sessionState: state }),

      updateSessionStatus: (status) => {
        set((state) => ({
          sessionState: state.sessionState
            ? { ...state.sessionState, status }
            : null,
        }))
      },

      setCurrentSpeaker: (speaker) => {
        set((state) => ({
          sessionState: state.sessionState
            ? { ...state.sessionState, current_speaker: speaker || undefined }
            : null,
        }))
      },

      addMessage: (message) => {
        set((state) => ({
          sessionState: state.sessionState
            ? {
                ...state.sessionState,
                conversation: [...state.sessionState.conversation, message],
              }
            : null,
        }))
      },

      updateLastMessage: (text, isFinal) => {
        set((state) => {
          if (!state.sessionState) return state
          const conversation = [...state.sessionState.conversation]
          if (conversation.length > 0) {
            const lastMsg = conversation[conversation.length - 1]
            conversation[conversation.length - 1] = {
              ...lastMsg,
              content: isFinal ? text : lastMsg.content + text,
            }
          }
          return {
            sessionState: {
              ...state.sessionState,
              conversation,
            },
          }
        })
      },

      setDetectedLanguage: (language) => {
        set((state) => ({
          sessionState: state.sessionState
            ? { ...state.sessionState, detected_language: language }
            : null,
        }))
      },

      // Connection state
      setConnected: (connected) => set({ isConnected: connected }),
      setRecording: (recording) => set({ isRecording: recording }),
      setMuted: (muted) => set({ isMuted: muted }),

      // Audio state
      setAudioLevel: (level) => set({ audioLevel: level }),
      setCurrentTranscript: (transcript) => set({ currentTranscript: transcript }),

      // Streaming message state
      setStreamingMessage: (message) => set({ streamingMessage: message }),
      appendToStreamingMessage: (text) => set((state) => ({
        streamingMessage: state.streamingMessage
          ? { ...state.streamingMessage, content: state.streamingMessage.content + text }
          : null,
      })),

      // Live transcript state
      setLiveTranscript: (transcript) => set({ liveTranscript: transcript }),
      appendLiveTranscriptWords: (agentId, text, words, estimated) => set((state) => {
        const current = state.liveTranscript
        if (current && current.agentId === agentId) {
          // Calculate offset for new words based on last word's end time
          const lastEndMs = current.words.length > 0
            ? current.words[current.words.length - 1].endMs
            : 0
          const offsetWords = words.map(w => ({
            ...w,
            startMs: w.startMs + lastEndMs,
            endMs: w.endMs + lastEndMs,
          }))
          return {
            liveTranscript: {
              ...current,
              text: current.text + text,
              words: [...current.words, ...offsetWords],
              estimated: current.estimated || estimated,
            },
          }
        }
        // New agent or first alignment data
        return {
          liveTranscript: {
            agentId,
            text,
            words,
            audioStartTime: Date.now(),
            estimated,
          },
        }
      }),
      setLiveTranscriptAudioStart: (timestamp) => set((state) => ({
        liveTranscript: state.liveTranscript
          ? { ...state.liveTranscript, audioStartTime: timestamp }
          : null,
      })),
      clearLiveTranscript: () => set({ liveTranscript: null }),

      // Waiting for audio state (OpenAI TTS)
      setWaitingForNextAudio: (waiting) => set({ waitingForNextAudio: waiting }),

      // Handle incoming server events
      handleServerEvent: (event) => {
        const state = get()

        switch (event.type) {
          case 'connected':
            state.setConnected(true)
            state.setSessionState({
              room_id: event.room_id,
              status: 'idle',
              conversation: [],
            })
            // If there are previous messages, fetch them
            if (event.previous_messages && event.previous_messages > 0 && event.room_id) {
              state.fetchConversation(event.room_id).then((messages) => {
                if (messages.length > 0) {
                  // Update the session state with fetched messages
                  set((s) => ({
                    sessionState: s.sessionState
                      ? { ...s.sessionState, conversation: messages }
                      : null,
                  }))
                  
                }
              })
            }
            break

          case 'transcript':
            if (event.is_final) {
              state.addMessage({
                id: generateUUID(),
                role: 'user',
                content: event.text,
                created_at: new Date().toISOString(),
              })
            }
            state.setCurrentTranscript(event.is_final ? '' : event.text)
            break

          case 'agent_state':
            if (event.state === 'speaking') {
              state.setCurrentSpeaker(event.agent_id)
              state.updateSessionStatus('speaking')
            } else if (event.state === 'thinking') {
              // Set speaker to thinking agent so carousel shows them
              state.setCurrentSpeaker(event.agent_id)
              state.updateSessionStatus('processing')
            } else if (event.state === 'done') {
              // Safety net: clear streaming message if it belongs to this agent
              // (normally cleared by agent_text is_final, but this handles edge cases)
              const currentStreaming = get().streamingMessage
              if (currentStreaming && currentStreaming.agent_id === event.agent_id) {
                state.setStreamingMessage(null)
              }
            }
            // Don't clear speaker on 'done' - let 'turn' or next agent's state handle it
            break

          case 'agent_text':
            if (event.is_final) {
              // Final message - add to conversation and clear streaming
              state.addMessage({
                id: generateUUID(),
                role: 'assistant',
                content: event.text,
                agent_id: event.agent_id,
                agent_name: event.agent_name,
                created_at: new Date().toISOString(),
              })
              state.setStreamingMessage(null)
            } else {
              // Streaming chunk - update or create streaming message
              const current = get().streamingMessage
              if (current && current.agent_id === event.agent_id) {
                // Append to existing streaming message
                state.appendToStreamingMessage(event.text)
              } else {
                // New streaming message (different agent or first chunk)
                state.setStreamingMessage({
                  agent_id: event.agent_id,
                  agent_name: event.agent_name || 'Assistant',
                  content: event.text,
                })
              }
            }
            break

          case 'turn':
            if (event.speaker === 'user') {
              state.setCurrentSpeaker(null)  // Clear agent speaker when it's user's turn
              state.updateSessionStatus('listening')
              state.setStreamingMessage(null)  // Clear any streaming message
              state.clearLiveTranscript()  // Clear live transcript
              state.setWaitingForNextAudio(false)  // Clear waiting state - it's user's turn
            }
            break

          case 'alignment':
            // Append word timing data for live transcript sync
            // estimated flag indicates OpenAI (skip word highlighting, keep line animation)
            state.appendLiveTranscriptWords(event.agent_id, event.text, event.words, event.estimated)
            break

          case 'session_ended':
            state.clearSession()
            break

          case 'error':
            console.error('Voice room error:', event.message)
            if (!event.recoverable) {
              state.clearSession()
            }
            break
        }
      },

      // Fetch conversation history for a room
      fetchConversation: async (roomId: string) => {
        try {
          const response = await apiClient.get(`${BACKEND_API_BASE}/rooms/${roomId}/conversation/`)
          return response.data.messages || []
        } catch (error) {
          console.error('Failed to fetch conversation:', error)
          return []
        }
      },

      // Clear conversation history for a room (start fresh)
      clearConversation: async (roomId: string) => {
        try {
          await apiClient.post(`${BACKEND_API_BASE}/rooms/${roomId}/clear_conversation/`)
        } catch (error) {
          console.error('Failed to clear conversation:', error)
        }
      },

      // AI Room Generation
      generateRoom: async (description: string, provider?: string) => {
        set({ isGeneratingRoom: true })
        try {
          const response = await apiClient.post(
            `${BACKEND_API_BASE}/generate-room/`,
            { description, provider },
            { timeout: LONG_RUNNING_TIMEOUT_MS }
          )
          set({ isGeneratingRoom: false })
          return response.data as GeneratedRoomConfig
        } catch (error) {
          if (isUnauthorized(error)) return null
          console.error('Failed to generate room:', error)
          set({ isGeneratingRoom: false })
          return null
        }
      },

      // Add room to recent list
      addRecentRoom: (roomId) => {
        set((state) => {
          const recent = [
            roomId,
            ...state.recentRooms.filter((id) => id !== roomId),
          ].slice(0, MAX_RECENT_ROOMS)
          return { recentRooms: recent }
        })
      },

      // Clear current session
      clearSession: () => {
        set({
          sessionState: null,
          isConnected: false,
          isRecording: false,
          audioLevel: 0,
          currentTranscript: '',
          streamingMessage: null,
          liveTranscript: null,
          waitingForNextAudio: false,
        })
      },

      // Full reset
      reset: () => {
        set({
          rooms: [],
          currentRoom: null,
          roomsLoading: false,
          roomsError: null,
          voices: [],
          voicesLoading: false,
          recommendedVoices: [],
          ttsProviders: [],
          ttsProvidersLoaded: false,
          ttsModels: [],
          ttsModelsLoading: false,
          ttsModelsLoaded: false,
          sessionState: null,
          isConnected: false,
          isRecording: false,
          isMuted: false,
          audioLevel: 0,
          currentTranscript: '',
          streamingMessage: null,
          liveTranscript: null,
          waitingForNextAudio: false,
          isGeneratingRoom: false,
          recentRooms: [],
        })
      },
    }),
    {
      name: 'voice-room-storage',
      storage: createUserScopedStorage('voice-room-storage'),
      partialize: (state) => ({
        recentRooms: state.recentRooms,
        isMuted: state.isMuted,
      }),
    }
  )
)

export default useVoiceRoomStore
