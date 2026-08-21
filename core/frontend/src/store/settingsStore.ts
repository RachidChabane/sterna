import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { createUserScopedStorage } from '../lib/userScopedStorage'
import { preferencesSync } from '../lib/preferencesSync'
import type { TTSModel, TTSProviderId } from '../types/voiceRoom'
import { DEFAULT_CODE_THEME, type CodeThemeId } from '../constants/codeThemes'

/**
 * Preference keys for backend sync
 */
export const SETTINGS_PREFERENCE_KEYS = {
  // Global Instructions Settings
  INSTRUCTIONS_ENABLED: 'settings.instructions.enabled',
  INSTRUCTIONS_CONTENT: 'settings.instructions.content',

  // STT Settings
  STT_LANGUAGE: 'settings.stt.language',

  // TTS Settings
  TTS_ENABLED: 'settings.tts.enabled',
  TTS_AUTO_READ: 'settings.tts.auto_read',
  TTS_PROVIDER: 'settings.tts.provider',
  TTS_VOICE_ID: 'settings.tts.voice_id',
  TTS_VOICE_NAME: 'settings.tts.voice_name',
  TTS_LANGUAGE: 'settings.tts.language',
  TTS_MODEL: 'settings.tts.model',
  TTS_STABILITY: 'settings.tts.stability',
  TTS_SIMILARITY_BOOST: 'settings.tts.similarity_boost',
  TTS_STYLE: 'settings.tts.style',
  TTS_SPEED: 'settings.tts.speed',
  TTS_USE_SPEAKER_BOOST: 'settings.tts.use_speaker_boost',

  // Chat Settings
  CHAT_COMPACT_MODE: 'settings.chat.compact_mode',
  CHAT_SHOW_TIMESTAMPS: 'settings.chat.show_timestamps',
  CHAT_SHOW_MODEL_NAME: 'settings.chat.show_model_name',
  CHAT_SHOW_MODEL_ICON: 'settings.chat.show_model_icon',
  CHAT_SHOW_USER_AVATAR: 'settings.chat.show_user_avatar',
  CHAT_ENTER_TO_SEND: 'settings.chat.enter_to_send',
  CHAT_STREAM_RESPONSES: 'settings.chat.stream_responses',

  // Accessibility Settings
  ACCESSIBILITY_FONT_SIZE: 'settings.accessibility.font_size',
  ACCESSIBILITY_REDUCE_MOTION: 'settings.accessibility.reduce_motion',
  ACCESSIBILITY_HIGH_CONTRAST: 'settings.accessibility.high_contrast',

  // Privacy Settings
  PRIVACY_SAVE_HISTORY: 'settings.privacy.save_history',
  PRIVACY_ANALYTICS: 'settings.privacy.analytics',

  // Watermark Settings
  WATERMARK_ENABLED: 'settings.watermark.enabled',
  WATERMARK_POSITION: 'settings.watermark.position',

  // Code Theme Settings
  CODE_THEME: 'settings.code_theme',
}

/**
 * Voice/TTS Settings for immersive chat and general TTS usage
 */
export interface TTSSettings {
  enabled: boolean
  autoRead: boolean // Auto-read AI responses
  provider: TTSProviderId // 'openai' or 'elevenlabs'
  voiceId: string
  voiceName: string
  language: string // 'auto' or specific language_id
  ttsModel: TTSModel
  speed: number // 0.25-4.0 for OpenAI, 0.5-2.0 for ElevenLabs
  // ElevenLabs-specific settings
  stability: number
  similarityBoost: number
  style: number
  useSpeakerBoost: boolean
}

/**
 * Speech-to-Text Settings
 */
export interface STTSettings {
  language: string // 'auto' or specific language code (e.g., 'en', 'es', 'fr')
}

/**
 * Chat display settings
 */
export interface ChatSettings {
  compactMode: boolean
  showTimestamps: boolean
  showModelName: boolean
  showModelIcon: boolean
  showUserAvatar: boolean
  enterToSend: boolean
  streamResponses: boolean
}

/**
 * Accessibility settings
 */
export interface AccessibilitySettings {
  fontSize: 'small' | 'medium' | 'large'
  reduceMotion: boolean
  highContrast: boolean
}

/**
 * Privacy settings
 */
export interface PrivacySettings {
  saveConversationHistory: boolean
  analyticsEnabled: boolean
}

/**
 * Watermark position options
 */
export type WatermarkPosition = 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left'

/**
 * Watermark settings for shared images
 */
export interface WatermarkSettings {
  enabled: boolean
  position: WatermarkPosition
}

/**
 * Global user instructions settings
 * Note: Chat-specific instructions are stored per-chat in conversationStore
 */
export interface InstructionsSettings {
  enabled: boolean
  content: string
}

interface SettingsState {
  // Modal state
  isOpen: boolean
  activeSection: string

  // Voice conversation mode (for system prompt adjustment)
  voiceConversationActive: boolean

  // Settings sections
  instructions: InstructionsSettings
  stt: STTSettings
  tts: TTSSettings
  chat: ChatSettings
  accessibility: AccessibilitySettings
  privacy: PrivacySettings
  watermark: WatermarkSettings
  codeTheme: CodeThemeId

  // Actions
  openSettings: (section?: string) => void
  closeSettings: () => void
  setActiveSection: (section: string) => void

  // Instructions Settings actions
  setInstructionsEnabled: (enabled: boolean) => void
  setInstructionsContent: (content: string) => void

  // STT Settings actions
  setSTTLanguage: (language: string) => void

  // TTS Settings actions
  setTTSEnabled: (enabled: boolean) => void
  setAutoRead: (autoRead: boolean) => void
  setTTSProvider: (provider: TTSProviderId) => void
  setVoice: (voiceId: string, voiceName: string) => void
  setTTSLanguage: (language: string) => void
  setTTSModel: (model: TTSModel) => void
  setTTSStability: (stability: number) => void
  setTTSSimilarityBoost: (similarityBoost: number) => void
  setTTSStyle: (style: number) => void
  setTTSSpeed: (speed: number) => void
  setTTSUseSpeakerBoost: (useSpeakerBoost: boolean) => void
  resetTTSSettings: () => void

  // Chat Settings actions
  setCompactMode: (compactMode: boolean) => void
  setShowTimestamps: (showTimestamps: boolean) => void
  setShowModelName: (showModelName: boolean) => void
  setShowModelIcon: (showModelIcon: boolean) => void
  setShowUserAvatar: (showUserAvatar: boolean) => void
  setEnterToSend: (enterToSend: boolean) => void
  setStreamResponses: (streamResponses: boolean) => void

  // Accessibility Settings actions
  setFontSize: (fontSize: 'small' | 'medium' | 'large') => void
  setReduceMotion: (reduceMotion: boolean) => void
  setHighContrast: (highContrast: boolean) => void

  // Privacy Settings actions
  setSaveConversationHistory: (save: boolean) => void
  setAnalyticsEnabled: (enabled: boolean) => void

  // Watermark Settings actions
  setWatermarkEnabled: (enabled: boolean) => void
  setWatermarkPosition: (position: WatermarkPosition) => void

  // Code Theme Settings actions
  setCodeTheme: (theme: CodeThemeId) => void

  // Voice conversation mode actions
  setVoiceConversationActive: (active: boolean) => void
}

const DEFAULT_INSTRUCTIONS_SETTINGS: InstructionsSettings = {
  enabled: false,
  content: '',
}

const DEFAULT_STT_SETTINGS: STTSettings = {
  language: 'auto', // Auto-detect by default
}

const DEFAULT_TTS_SETTINGS: TTSSettings = {
  enabled: true,
  autoRead: false,
  provider: 'openai', // Default to OpenAI TTS
  voiceId: 'alloy', // OpenAI default voice
  voiceName: 'Alloy',
  language: 'auto',
  ttsModel: 'tts-1', // OpenAI standard model
  speed: 1.3, // Faster for natural voice conversations
  // ElevenLabs-specific defaults (used when provider is 'elevenlabs')
  stability: 0.5,
  similarityBoost: 0.8,
  style: 0.3,
  useSpeakerBoost: true,
}

const DEFAULT_CHAT_SETTINGS: ChatSettings = {
  compactMode: false,
  showTimestamps: false,
  showModelName: true,
  showModelIcon: true,
  showUserAvatar: true,
  enterToSend: true,
  streamResponses: true,
}

const DEFAULT_ACCESSIBILITY_SETTINGS: AccessibilitySettings = {
  fontSize: 'medium',
  reduceMotion: false,
  highContrast: false,
}

const DEFAULT_PRIVACY_SETTINGS: PrivacySettings = {
  saveConversationHistory: true,
  analyticsEnabled: true,
}

const DEFAULT_WATERMARK_SETTINGS: WatermarkSettings = {
  enabled: true,
  position: 'bottom-right',
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      // Modal state
      isOpen: false,
      activeSection: 'general',

      // Voice conversation mode
      voiceConversationActive: false,

      // Default settings
      instructions: { ...DEFAULT_INSTRUCTIONS_SETTINGS },
      stt: { ...DEFAULT_STT_SETTINGS },
      tts: { ...DEFAULT_TTS_SETTINGS },
      chat: { ...DEFAULT_CHAT_SETTINGS },
      accessibility: { ...DEFAULT_ACCESSIBILITY_SETTINGS },
      privacy: { ...DEFAULT_PRIVACY_SETTINGS },
      watermark: { ...DEFAULT_WATERMARK_SETTINGS },
      codeTheme: DEFAULT_CODE_THEME,

      // Modal actions
      openSettings: (section = 'general') => set({ isOpen: true, activeSection: section }),
      closeSettings: () => set({ isOpen: false }),
      setActiveSection: (section) => set({ activeSection: section }),

      // Instructions Settings actions
      setInstructionsEnabled: (enabled) => {
        set((state) => ({ instructions: { ...state.instructions, enabled } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.INSTRUCTIONS_ENABLED, enabled, 'settings')
      },
      setInstructionsContent: (content) => {
        set((state) => ({ instructions: { ...state.instructions, content } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.INSTRUCTIONS_CONTENT, content, 'settings')
      },

      // STT Settings actions
      setSTTLanguage: (language) => {
        set((state) => ({ stt: { ...state.stt, language } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.STT_LANGUAGE, language, 'settings')
      },

      // TTS Settings actions
      setTTSEnabled: (enabled) => {
        set((state) => ({ tts: { ...state.tts, enabled } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_ENABLED, enabled, 'settings')
      },
      setAutoRead: (autoRead) => {
        set((state) => ({ tts: { ...state.tts, autoRead } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_AUTO_READ, autoRead, 'settings')
      },
      setTTSProvider: (provider) => {
        set((state) => ({ tts: { ...state.tts, provider } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_PROVIDER, provider, 'settings')
      },
      setVoice: (voiceId, voiceName) => {
        set((state) => ({ tts: { ...state.tts, voiceId, voiceName } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_VOICE_ID, voiceId, 'settings')
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_VOICE_NAME, voiceName, 'settings')
      },
      setTTSLanguage: (language) => {
        set((state) => ({ tts: { ...state.tts, language } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_LANGUAGE, language, 'settings')
      },
      setTTSModel: (ttsModel) => {
        set((state) => ({ tts: { ...state.tts, ttsModel } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_MODEL, ttsModel, 'settings')
      },
      setTTSStability: (stability) => {
        set((state) => ({ tts: { ...state.tts, stability } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_STABILITY, stability, 'settings')
      },
      setTTSSimilarityBoost: (similarityBoost) => {
        set((state) => ({ tts: { ...state.tts, similarityBoost } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_SIMILARITY_BOOST, similarityBoost, 'settings')
      },
      setTTSStyle: (style) => {
        set((state) => ({ tts: { ...state.tts, style } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_STYLE, style, 'settings')
      },
      setTTSSpeed: (speed) => {
        set((state) => ({ tts: { ...state.tts, speed } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_SPEED, speed, 'settings')
      },
      setTTSUseSpeakerBoost: (useSpeakerBoost) => {
        set((state) => ({ tts: { ...state.tts, useSpeakerBoost } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_USE_SPEAKER_BOOST, useSpeakerBoost, 'settings')
      },
      resetTTSSettings: () => {
        set({ tts: { ...DEFAULT_TTS_SETTINGS } })
        // Sync all TTS settings to backend
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_ENABLED, DEFAULT_TTS_SETTINGS.enabled, 'settings')
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_AUTO_READ, DEFAULT_TTS_SETTINGS.autoRead, 'settings')
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_PROVIDER, DEFAULT_TTS_SETTINGS.provider, 'settings')
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_VOICE_ID, DEFAULT_TTS_SETTINGS.voiceId, 'settings')
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_VOICE_NAME, DEFAULT_TTS_SETTINGS.voiceName, 'settings')
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_LANGUAGE, DEFAULT_TTS_SETTINGS.language, 'settings')
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_MODEL, DEFAULT_TTS_SETTINGS.ttsModel, 'settings')
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_STABILITY, DEFAULT_TTS_SETTINGS.stability, 'settings')
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_SIMILARITY_BOOST, DEFAULT_TTS_SETTINGS.similarityBoost, 'settings')
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_STYLE, DEFAULT_TTS_SETTINGS.style, 'settings')
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_SPEED, DEFAULT_TTS_SETTINGS.speed, 'settings')
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.TTS_USE_SPEAKER_BOOST, DEFAULT_TTS_SETTINGS.useSpeakerBoost, 'settings')
      },

      // Chat Settings actions
      setCompactMode: (compactMode) => {
        set((state) => ({ chat: { ...state.chat, compactMode } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.CHAT_COMPACT_MODE, compactMode, 'settings')
      },
      setShowTimestamps: (showTimestamps) => {
        set((state) => ({ chat: { ...state.chat, showTimestamps } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_TIMESTAMPS, showTimestamps, 'settings')
      },
      setShowModelName: (showModelName) => {
        set((state) => ({ chat: { ...state.chat, showModelName } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_MODEL_NAME, showModelName, 'settings')
      },
      setShowModelIcon: (showModelIcon) => {
        set((state) => ({ chat: { ...state.chat, showModelIcon } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_MODEL_ICON, showModelIcon, 'settings')
      },
      setShowUserAvatar: (showUserAvatar) => {
        set((state) => ({ chat: { ...state.chat, showUserAvatar } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_USER_AVATAR, showUserAvatar, 'settings')
      },
      setEnterToSend: (enterToSend) => {
        set((state) => ({ chat: { ...state.chat, enterToSend } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.CHAT_ENTER_TO_SEND, enterToSend, 'settings')
      },
      setStreamResponses: (streamResponses) => {
        set((state) => ({ chat: { ...state.chat, streamResponses } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.CHAT_STREAM_RESPONSES, streamResponses, 'settings')
      },

      // Accessibility Settings actions
      setFontSize: (fontSize) => {
        set((state) => ({ accessibility: { ...state.accessibility, fontSize } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.ACCESSIBILITY_FONT_SIZE, fontSize, 'settings')
      },
      setReduceMotion: (reduceMotion) => {
        set((state) => ({ accessibility: { ...state.accessibility, reduceMotion } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.ACCESSIBILITY_REDUCE_MOTION, reduceMotion, 'settings')
      },
      setHighContrast: (highContrast) => {
        set((state) => ({ accessibility: { ...state.accessibility, highContrast } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.ACCESSIBILITY_HIGH_CONTRAST, highContrast, 'settings')
      },

      // Privacy Settings actions
      setSaveConversationHistory: (saveConversationHistory) => {
        set((state) => ({ privacy: { ...state.privacy, saveConversationHistory } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.PRIVACY_SAVE_HISTORY, saveConversationHistory, 'settings')
      },
      setAnalyticsEnabled: (analyticsEnabled) => {
        set((state) => ({ privacy: { ...state.privacy, analyticsEnabled } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.PRIVACY_ANALYTICS, analyticsEnabled, 'settings')
      },

      // Watermark Settings actions
      setWatermarkEnabled: (enabled) => {
        set((state) => ({ watermark: { ...state.watermark, enabled } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.WATERMARK_ENABLED, enabled, 'settings')
      },
      setWatermarkPosition: (position) => {
        set((state) => ({ watermark: { ...state.watermark, position } }))
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.WATERMARK_POSITION, position, 'settings')
      },

      // Code Theme Settings actions
      setCodeTheme: (codeTheme) => {
        set({ codeTheme })
        preferencesSync.update(SETTINGS_PREFERENCE_KEYS.CODE_THEME, codeTheme, 'settings')
      },

      // Voice conversation mode actions
      setVoiceConversationActive: (voiceConversationActive) => {
        set({ voiceConversationActive })
      },
    }),
    {
      name: 'settings-storage',
      storage: createUserScopedStorage('settings-storage'),
      partialize: (state) => ({
        instructions: state.instructions,
        stt: state.stt,
        tts: state.tts,
        chat: state.chat,
        accessibility: state.accessibility,
        privacy: state.privacy,
        watermark: state.watermark,
        codeTheme: state.codeTheme,
      }),
    }
  )
)

export default useSettingsStore
