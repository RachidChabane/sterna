/**
 * Hook for loading user preferences from backend on login
 *
 * Handles:
 * - Loading preferences from backend
 * - Migrating localStorage data to backend
 * - Populating all stores with backend data
 */

import { useCallback, useState } from 'react'
import { preferencesSync } from '../lib/preferencesSync'
import useModelStore from '../store/modelStore'
import { useNavigationStore } from '../store/navigationStore'
import { useOnboardingStore } from '../store/onboardingStore'
import { useUIStore } from '../store/uiStore'
import { useSettingsStore, SETTINGS_PREFERENCE_KEYS } from '../store/settingsStore'
import type {
  TTSSettings,
  ChatSettings,
  AccessibilitySettings,
  PrivacySettings,
  InstructionsSettings,
  STTSettings,
  WatermarkSettings,
  WatermarkPosition,
} from '../store/settingsStore'
import type { CodeThemeId } from '../constants/codeThemes'
import { CODE_THEMES } from '../constants/codeThemes'
import type { ModelCatalogEntry, ModelFavorite, RecentModel } from '../types/models'
import type { TTSModel } from '../types/voiceRoom'
import { useThemeStore } from '../store/themeStore'

/** The subset of settings-store state a single backend-preferences load can patch in one `setState()` call. */
interface SettingsPatch {
  tts?: TTSSettings
  chat?: ChatSettings
  accessibility?: AccessibilitySettings
  privacy?: PrivacySettings
  instructions?: InstructionsSettings
  stt?: STTSettings
  watermark?: WatermarkSettings
  codeTheme?: CodeThemeId
}

/**
 * Preference key mapping
 */
export const PREFERENCE_KEYS = {
  // Models
  MODELS_FAVORITES: 'models.favorites',
  MODELS_RECENT: 'models.recent',
  MODELS_RECENT_CHAT: 'models.recent_chat',
  MODELS_CURRENT: 'models.current',
  MODELS_ACTIVE_CHAT_GROUP: 'models.active_chat_group',
  MODELS_COMPARE_PRESET: 'models.compare.preset',
  MODELS_COMPARE_PRIORITIES: 'models.compare.priorities',
  MODELS_COMPARE_CONSTRAINTS: 'models.compare.constraints',
  MODELS_COMPARE_SCENARIO: 'models.compare.scenario',

  // UI
  UI_THEME: 'ui.theme',
  UI_SIDEBAR_OPEN: 'ui.sidebar_open',
  UI_SIDEBAR_COLLAPSED: 'ui.sidebar_collapsed',
  UI_NAVIGATION_ORDER: 'ui.navigation_order',

  // Onboarding
  ONBOARDING_CURRENT_STEP: 'onboarding.current_step',
  ONBOARDING_STEPS: 'onboarding.steps',
  ONBOARDING_COMPLETED: 'onboarding.completed',
  ONBOARDING_SKIPPED_AT: 'onboarding.skipped_at',
  ONBOARDING_API_KEY_CONFIGURED: 'onboarding.api_key_configured',
  ONBOARDING_SAMPLE_EVALUATION_RUN: 'onboarding.sample_evaluation_run',
}

// --- Narrowing for backend preference values ---------------------------------
// The backend stores preference values opaquely; each reader below accepts a
// value only when it matches the type the store expects, so a corrupt or
// stale payload is skipped instead of poisoning store state.

const isBoolean = (value: unknown): value is boolean => typeof value === 'boolean'
const isNumber = (value: unknown): value is number => typeof value === 'number'
const isNonEmptyString = (value: unknown): value is string =>
  typeof value === 'string' && value.length > 0
const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === 'string')

const FONT_SIZES: readonly AccessibilitySettings['fontSize'][] = ['small', 'medium', 'large']
const isFontSize = (value: unknown): value is AccessibilitySettings['fontSize'] =>
  (FONT_SIZES as readonly unknown[]).includes(value)

const WATERMARK_POSITIONS: readonly WatermarkPosition[] = [
  'bottom-right',
  'bottom-left',
  'top-right',
  'top-left',
]
const isWatermarkPosition = (value: unknown): value is WatermarkPosition =>
  (WATERMARK_POSITIONS as readonly unknown[]).includes(value)

const TTS_MODELS: readonly TTSModel[] = [
  'tts-1',
  'tts-1-hd',
  'eleven_v3',
  'eleven_turbo_v2_5',
  'eleven_flash_v2_5',
  'eleven_multilingual_v2',
]
const isTTSModel = (value: unknown): value is TTSModel =>
  (TTS_MODELS as readonly unknown[]).includes(value)

const isCodeThemeId = (value: unknown): value is CodeThemeId =>
  CODE_THEMES.some((theme) => theme.id === value)

// A models preference is written by this same client from its own store state
// and round-trips through the backend unchanged, so a well-formed container is
// read back as the store's element type.
const isStoredModelList = <T>(value: unknown): value is T[] =>
  Array.isArray(value) && value.every((item) => typeof item === 'object' && item !== null)
const isStoredModelEntry = (value: unknown): value is ModelCatalogEntry =>
  typeof value === 'object' && value !== null

/**
 * Standalone function to load preferences from backend
 * (can be called from non-React contexts like stores)
 */
export const loadPreferencesFromBackend = async (): Promise<void> => {
  try {
    // Load all preferences from backend
    const backendPrefs = await preferencesSync.loadAll()

    // Check if backend has data
    const hasBackendData = Object.keys(backendPrefs).length > 0

    if (!hasBackendData) {
      // Backend empty - no need to populate stores
      // Migration will happen in usePreferencesLoader if needed
      return
    }

    // Backend has data - populate stores from backend

    // Import stores dynamically to avoid circular dependencies
    const { default: useModelStore } = await import('../store/modelStore')
    const { useNavigationStore } = await import('../store/navigationStore')
    const { useOnboardingStore } = await import('../store/onboardingStore')
    const { useUIStore } = await import('../store/uiStore')
    const { useSettingsStore, SETTINGS_PREFERENCE_KEYS } = await import('../store/settingsStore')

    // Models - Load from backend WITHOUT triggering sync
    // Use setState() directly to avoid calling actions which would trigger another sync
    const favorites = backendPrefs[PREFERENCE_KEYS.MODELS_FAVORITES]
    if (isStoredModelList<ModelFavorite>(favorites)) {
      useModelStore.setState({ favorites })
    }

    const recentModels = backendPrefs[PREFERENCE_KEYS.MODELS_RECENT]
    if (isStoredModelList<RecentModel>(recentModels)) {
      useModelStore.setState({ recentModels })
    }

    const recentChatModels = backendPrefs[PREFERENCE_KEYS.MODELS_RECENT_CHAT]
    if (isStoredModelList<RecentModel>(recentChatModels)) {
      useModelStore.setState({ recentChatModels })
    }

    const currentModel = backendPrefs[PREFERENCE_KEYS.MODELS_CURRENT]
    if (isStoredModelEntry(currentModel)) {
      useModelStore.setState({ currentModel })
    }

    // UI
    const sidebarOpen = backendPrefs[PREFERENCE_KEYS.UI_SIDEBAR_OPEN]
    if (isBoolean(sidebarOpen)) {
      useUIStore.getState().setSidebarOpen(sidebarOpen)
    }

    // Note: UI_SIDEBAR_COLLAPSED is only stored in localStorage, not synced to backend

    const navigationOrder = backendPrefs[PREFERENCE_KEYS.UI_NAVIGATION_ORDER]
    if (isStringArray(navigationOrder)) {
      useNavigationStore.getState().setNavigationOrder(navigationOrder)
    }

    // Theme - Load from backend and apply (skipSync=true to avoid re-syncing)
    if (backendPrefs[PREFERENCE_KEYS.UI_THEME]) {
      const { useThemeStore } = await import('../store/themeStore')
      const theme = backendPrefs[PREFERENCE_KEYS.UI_THEME]
      if (theme === 'light' || theme === 'dark' || theme === 'system') {
        useThemeStore.getState().setTheme(theme, true) // skipSync=true
      }
    }

    // Onboarding
    const currentStep = backendPrefs[PREFERENCE_KEYS.ONBOARDING_CURRENT_STEP]
    if (isNumber(currentStep)) {
      useOnboardingStore.getState().setCurrentStep(currentStep)
    }

    if (backendPrefs[PREFERENCE_KEYS.ONBOARDING_COMPLETED]) {
      useOnboardingStore.getState().completeOnboarding()
    }

    if (backendPrefs[PREFERENCE_KEYS.ONBOARDING_SKIPPED_AT]) {
      useOnboardingStore.getState().skipOnboarding()
    }

    const apiKeyConfigured = backendPrefs[PREFERENCE_KEYS.ONBOARDING_API_KEY_CONFIGURED]
    if (isBoolean(apiKeyConfigured)) {
      useOnboardingStore.getState().setApiKeyConfigured(apiKeyConfigured)
    }

    const sampleEvaluationRun = backendPrefs[PREFERENCE_KEYS.ONBOARDING_SAMPLE_EVALUATION_RUN]
    if (isBoolean(sampleEvaluationRun)) {
      useOnboardingStore.getState().setSampleEvaluationRun(sampleEvaluationRun)
    }

    // Settings - Load from backend using setState() to avoid triggering sync
    const settingsState: SettingsPatch = {}

    // TTS Settings
    const ttsEnabled = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_ENABLED]
    if (isBoolean(ttsEnabled)) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.enabled = ttsEnabled
    }
    const ttsAutoRead = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_AUTO_READ]
    if (isBoolean(ttsAutoRead)) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.autoRead = ttsAutoRead
    }
    const ttsVoiceId = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_VOICE_ID]
    if (isNonEmptyString(ttsVoiceId)) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.voiceId = ttsVoiceId
    }
    const ttsVoiceName = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_VOICE_NAME]
    if (isNonEmptyString(ttsVoiceName)) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.voiceName = ttsVoiceName
    }
    const ttsLanguage = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_LANGUAGE]
    if (isNonEmptyString(ttsLanguage)) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.language = ttsLanguage
    }
    const ttsModel = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_MODEL]
    if (isTTSModel(ttsModel)) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.ttsModel = ttsModel
    }
    const ttsStability = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_STABILITY]
    if (isNumber(ttsStability)) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.stability = ttsStability
    }
    const ttsSimilarityBoost = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_SIMILARITY_BOOST]
    if (isNumber(ttsSimilarityBoost)) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.similarityBoost = ttsSimilarityBoost
    }
    const ttsStyle = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_STYLE]
    if (isNumber(ttsStyle)) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.style = ttsStyle
    }
    const ttsSpeed = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_SPEED]
    if (isNumber(ttsSpeed)) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.speed = ttsSpeed
    }
    const ttsUseSpeakerBoost = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_USE_SPEAKER_BOOST]
    if (isBoolean(ttsUseSpeakerBoost)) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.useSpeakerBoost = ttsUseSpeakerBoost
    }

    // Chat Settings
    const chatCompactMode = backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_COMPACT_MODE]
    if (isBoolean(chatCompactMode)) {
      settingsState.chat = settingsState.chat || { ...useSettingsStore.getState().chat }
      settingsState.chat.compactMode = chatCompactMode
    }
    const chatShowTimestamps = backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_TIMESTAMPS]
    if (isBoolean(chatShowTimestamps)) {
      settingsState.chat = settingsState.chat || { ...useSettingsStore.getState().chat }
      settingsState.chat.showTimestamps = chatShowTimestamps
    }
    const chatShowModelName = backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_MODEL_NAME]
    if (isBoolean(chatShowModelName)) {
      settingsState.chat = settingsState.chat || { ...useSettingsStore.getState().chat }
      settingsState.chat.showModelName = chatShowModelName
    }
    const chatEnterToSend = backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_ENTER_TO_SEND]
    if (isBoolean(chatEnterToSend)) {
      settingsState.chat = settingsState.chat || { ...useSettingsStore.getState().chat }
      settingsState.chat.enterToSend = chatEnterToSend
    }
    const chatStreamResponses = backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_STREAM_RESPONSES]
    if (isBoolean(chatStreamResponses)) {
      settingsState.chat = settingsState.chat || { ...useSettingsStore.getState().chat }
      settingsState.chat.streamResponses = chatStreamResponses
    }

    // Accessibility Settings
    const accessibilityFontSize = backendPrefs[SETTINGS_PREFERENCE_KEYS.ACCESSIBILITY_FONT_SIZE]
    if (isFontSize(accessibilityFontSize)) {
      settingsState.accessibility = settingsState.accessibility || { ...useSettingsStore.getState().accessibility }
      settingsState.accessibility.fontSize = accessibilityFontSize
    }
    const accessibilityReduceMotion = backendPrefs[SETTINGS_PREFERENCE_KEYS.ACCESSIBILITY_REDUCE_MOTION]
    if (isBoolean(accessibilityReduceMotion)) {
      settingsState.accessibility = settingsState.accessibility || { ...useSettingsStore.getState().accessibility }
      settingsState.accessibility.reduceMotion = accessibilityReduceMotion
    }
    const accessibilityHighContrast = backendPrefs[SETTINGS_PREFERENCE_KEYS.ACCESSIBILITY_HIGH_CONTRAST]
    if (isBoolean(accessibilityHighContrast)) {
      settingsState.accessibility = settingsState.accessibility || { ...useSettingsStore.getState().accessibility }
      settingsState.accessibility.highContrast = accessibilityHighContrast
    }

    // Privacy Settings
    const privacySaveHistory = backendPrefs[SETTINGS_PREFERENCE_KEYS.PRIVACY_SAVE_HISTORY]
    if (isBoolean(privacySaveHistory)) {
      settingsState.privacy = settingsState.privacy || { ...useSettingsStore.getState().privacy }
      settingsState.privacy.saveConversationHistory = privacySaveHistory
    }
    const privacyAnalytics = backendPrefs[SETTINGS_PREFERENCE_KEYS.PRIVACY_ANALYTICS]
    if (isBoolean(privacyAnalytics)) {
      settingsState.privacy = settingsState.privacy || { ...useSettingsStore.getState().privacy }
      settingsState.privacy.analyticsEnabled = privacyAnalytics
    }

    // Instructions Settings
    const instructionsEnabled = backendPrefs[SETTINGS_PREFERENCE_KEYS.INSTRUCTIONS_ENABLED]
    if (isBoolean(instructionsEnabled)) {
      settingsState.instructions = settingsState.instructions || { ...useSettingsStore.getState().instructions }
      settingsState.instructions.enabled = instructionsEnabled
    }
    const instructionsContent = backendPrefs[SETTINGS_PREFERENCE_KEYS.INSTRUCTIONS_CONTENT]
    if (isNonEmptyString(instructionsContent)) {
      settingsState.instructions = settingsState.instructions || { ...useSettingsStore.getState().instructions }
      settingsState.instructions.content = instructionsContent
    }

    // STT Settings
    const sttLanguage = backendPrefs[SETTINGS_PREFERENCE_KEYS.STT_LANGUAGE]
    if (isNonEmptyString(sttLanguage)) {
      settingsState.stt = settingsState.stt || { ...useSettingsStore.getState().stt }
      settingsState.stt.language = sttLanguage
    }

    // Watermark Settings
    const watermarkEnabled = backendPrefs[SETTINGS_PREFERENCE_KEYS.WATERMARK_ENABLED]
    if (isBoolean(watermarkEnabled)) {
      settingsState.watermark = settingsState.watermark || { ...useSettingsStore.getState().watermark }
      settingsState.watermark.enabled = watermarkEnabled
    }
    const watermarkPosition = backendPrefs[SETTINGS_PREFERENCE_KEYS.WATERMARK_POSITION]
    if (isWatermarkPosition(watermarkPosition)) {
      settingsState.watermark = settingsState.watermark || { ...useSettingsStore.getState().watermark }
      settingsState.watermark.position = watermarkPosition
    }

    // Code Theme
    const codeTheme = backendPrefs[SETTINGS_PREFERENCE_KEYS.CODE_THEME]
    if (isCodeThemeId(codeTheme)) {
      settingsState.codeTheme = codeTheme
    }

    // Chat Settings - additional fields
    const chatShowModelIcon = backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_MODEL_ICON]
    if (isBoolean(chatShowModelIcon)) {
      settingsState.chat = settingsState.chat || { ...useSettingsStore.getState().chat }
      settingsState.chat.showModelIcon = chatShowModelIcon
    }
    const chatShowUserAvatar = backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_USER_AVATAR]
    if (isBoolean(chatShowUserAvatar)) {
      settingsState.chat = settingsState.chat || { ...useSettingsStore.getState().chat }
      settingsState.chat.showUserAvatar = chatShowUserAvatar
    }

    // Apply settings state if any settings were loaded
    if (Object.keys(settingsState).length > 0) {
      useSettingsStore.setState(settingsState)
    }
  } catch (err) {
    console.error('[PreferencesLoader] Error loading preferences:', err)
    // Don't throw - loading failure shouldn't block login
  }
}

export const usePreferencesLoader = () => {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Get store actions
  const modelStore = useModelStore()
  const navigationStore = useNavigationStore()
  const onboardingStore = useOnboardingStore()
  const uiStore = useUIStore()
  const settingsStore = useSettingsStore()

  /**
   * Load all preferences from backend and populate stores
   */
  const loadAllPreferences = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      // Load all preferences from backend
      const backendPrefs = await preferencesSync.loadAll()

      // Check if backend has data
      const hasBackendData = Object.keys(backendPrefs).length > 0

      if (hasBackendData) {
        // Backend has data - populate stores from backend
        await populateStoresFromBackend(backendPrefs)
      } else {
        // Backend empty - check if localStorage has data to migrate
        await migrateLocalDataToBackend()
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load preferences'
      console.error('[PreferencesLoader] Error loading preferences:', err)
      setError(errorMessage)
    } finally {
      setIsLoading(false)
    }
  }, [])

  /**
   * Populate all stores from backend preferences
   */
  const populateStoresFromBackend = async (
    backendPrefs: Record<string, unknown>
  ): Promise<void> => {
    // Models are handled by loadPreferencesFromBackend's setState path;
    // this hook-level pass covers the stores whose actions it holds.

    // UI
    const sidebarOpen = backendPrefs[PREFERENCE_KEYS.UI_SIDEBAR_OPEN]
    if (isBoolean(sidebarOpen)) {
      uiStore.setSidebarOpen(sidebarOpen)
    }

    // Note: UI_SIDEBAR_COLLAPSED is only stored in localStorage, not synced to backend

    const navigationOrder = backendPrefs[PREFERENCE_KEYS.UI_NAVIGATION_ORDER]
    if (isStringArray(navigationOrder)) {
      navigationStore.setNavigationOrder(navigationOrder)
    }

    // Theme - Load from backend and apply (skipSync=true to avoid re-syncing)
    if (backendPrefs[PREFERENCE_KEYS.UI_THEME]) {
      const theme = backendPrefs[PREFERENCE_KEYS.UI_THEME]
      if (theme === 'light' || theme === 'dark' || theme === 'system') {
        useThemeStore.getState().setTheme(theme, true) // skipSync=true
      }
    }

    // Onboarding
    const currentStep = backendPrefs[PREFERENCE_KEYS.ONBOARDING_CURRENT_STEP]
    if (isNumber(currentStep)) {
      onboardingStore.setCurrentStep(currentStep)
    }

    if (backendPrefs[PREFERENCE_KEYS.ONBOARDING_COMPLETED]) {
      onboardingStore.completeOnboarding()
    }

    if (backendPrefs[PREFERENCE_KEYS.ONBOARDING_SKIPPED_AT]) {
      onboardingStore.skipOnboarding()
    }

    const apiKeyConfigured = backendPrefs[PREFERENCE_KEYS.ONBOARDING_API_KEY_CONFIGURED]
    if (isBoolean(apiKeyConfigured)) {
      onboardingStore.setApiKeyConfigured(apiKeyConfigured)
    }

    const sampleEvaluationRun = backendPrefs[PREFERENCE_KEYS.ONBOARDING_SAMPLE_EVALUATION_RUN]
    if (isBoolean(sampleEvaluationRun)) {
      onboardingStore.setSampleEvaluationRun(sampleEvaluationRun)
    }
  }

  /**
   * Migrate localStorage data to backend (one-time migration)
   */
  const migrateLocalDataToBackend = async (): Promise<void> => {
    try {
      // Get current store states (which are from localStorage)
      const localData: Record<string, unknown> = {}

      // Check models store
      if (modelStore.favorites.length > 0) {
        localData[PREFERENCE_KEYS.MODELS_FAVORITES] = modelStore.favorites
      }
      if (modelStore.recentModels.length > 0) {
        localData[PREFERENCE_KEYS.MODELS_RECENT] = modelStore.recentModels
      }
      if (modelStore.recentChatModels.length > 0) {
        localData[PREFERENCE_KEYS.MODELS_RECENT_CHAT] = modelStore.recentChatModels
      }
      if (modelStore.currentModel) {
        localData[PREFERENCE_KEYS.MODELS_CURRENT] = modelStore.currentModel
      }

      // Check navigation store
      if (navigationStore.navigationOrder.length > 0) {
        localData[PREFERENCE_KEYS.UI_NAVIGATION_ORDER] = navigationStore.navigationOrder
      }
      // Note: isCollapsed is only stored in localStorage, not synced to backend

      // Check onboarding store
      if (onboardingStore.currentStep !== undefined) {
        localData[PREFERENCE_KEYS.ONBOARDING_CURRENT_STEP] = onboardingStore.currentStep
      }
      if (onboardingStore.onboardingCompleted) {
        localData[PREFERENCE_KEYS.ONBOARDING_COMPLETED] = onboardingStore.onboardingCompleted
      }
      if (onboardingStore.skippedAt) {
        localData[PREFERENCE_KEYS.ONBOARDING_SKIPPED_AT] = onboardingStore.skippedAt
      }
      if (onboardingStore.apiKeyConfigured) {
        localData[PREFERENCE_KEYS.ONBOARDING_API_KEY_CONFIGURED] =
          onboardingStore.apiKeyConfigured
      }
      if (onboardingStore.sampleEvaluationRun) {
        localData[PREFERENCE_KEYS.ONBOARDING_SAMPLE_EVALUATION_RUN] =
          onboardingStore.sampleEvaluationRun
      }

      // Check UI store
      if (uiStore.isSidebarOpen !== undefined) {
        localData[PREFERENCE_KEYS.UI_SIDEBAR_OPEN] = uiStore.isSidebarOpen
      }

      // Check theme store - migrate theme from localStorage
      const themeStore = useThemeStore.getState()
      if (themeStore.theme) {
        localData[PREFERENCE_KEYS.UI_THEME] = themeStore.theme
      }

      // Check settings store - TTS settings
      localData[SETTINGS_PREFERENCE_KEYS.TTS_ENABLED] = settingsStore.tts.enabled
      localData[SETTINGS_PREFERENCE_KEYS.TTS_AUTO_READ] = settingsStore.tts.autoRead
      localData[SETTINGS_PREFERENCE_KEYS.TTS_VOICE_ID] = settingsStore.tts.voiceId
      localData[SETTINGS_PREFERENCE_KEYS.TTS_VOICE_NAME] = settingsStore.tts.voiceName
      localData[SETTINGS_PREFERENCE_KEYS.TTS_LANGUAGE] = settingsStore.tts.language
      localData[SETTINGS_PREFERENCE_KEYS.TTS_MODEL] = settingsStore.tts.ttsModel
      localData[SETTINGS_PREFERENCE_KEYS.TTS_STABILITY] = settingsStore.tts.stability
      localData[SETTINGS_PREFERENCE_KEYS.TTS_SIMILARITY_BOOST] = settingsStore.tts.similarityBoost
      localData[SETTINGS_PREFERENCE_KEYS.TTS_STYLE] = settingsStore.tts.style
      localData[SETTINGS_PREFERENCE_KEYS.TTS_SPEED] = settingsStore.tts.speed
      localData[SETTINGS_PREFERENCE_KEYS.TTS_USE_SPEAKER_BOOST] = settingsStore.tts.useSpeakerBoost

      // Chat settings
      localData[SETTINGS_PREFERENCE_KEYS.CHAT_COMPACT_MODE] = settingsStore.chat.compactMode
      localData[SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_TIMESTAMPS] = settingsStore.chat.showTimestamps
      localData[SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_MODEL_NAME] = settingsStore.chat.showModelName
      localData[SETTINGS_PREFERENCE_KEYS.CHAT_ENTER_TO_SEND] = settingsStore.chat.enterToSend
      localData[SETTINGS_PREFERENCE_KEYS.CHAT_STREAM_RESPONSES] = settingsStore.chat.streamResponses

      // Accessibility settings
      localData[SETTINGS_PREFERENCE_KEYS.ACCESSIBILITY_FONT_SIZE] = settingsStore.accessibility.fontSize
      localData[SETTINGS_PREFERENCE_KEYS.ACCESSIBILITY_REDUCE_MOTION] = settingsStore.accessibility.reduceMotion
      localData[SETTINGS_PREFERENCE_KEYS.ACCESSIBILITY_HIGH_CONTRAST] = settingsStore.accessibility.highContrast

      // Privacy settings
      localData[SETTINGS_PREFERENCE_KEYS.PRIVACY_SAVE_HISTORY] = settingsStore.privacy.saveConversationHistory
      localData[SETTINGS_PREFERENCE_KEYS.PRIVACY_ANALYTICS] = settingsStore.privacy.analyticsEnabled

      // Instructions settings
      localData[SETTINGS_PREFERENCE_KEYS.INSTRUCTIONS_ENABLED] = settingsStore.instructions.enabled
      localData[SETTINGS_PREFERENCE_KEYS.INSTRUCTIONS_CONTENT] = settingsStore.instructions.content

      // STT settings
      localData[SETTINGS_PREFERENCE_KEYS.STT_LANGUAGE] = settingsStore.stt.language

      // Watermark settings
      localData[SETTINGS_PREFERENCE_KEYS.WATERMARK_ENABLED] = settingsStore.watermark.enabled
      localData[SETTINGS_PREFERENCE_KEYS.WATERMARK_POSITION] = settingsStore.watermark.position

      // Code theme
      localData[SETTINGS_PREFERENCE_KEYS.CODE_THEME] = settingsStore.codeTheme

      // Chat settings - additional fields
      localData[SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_MODEL_ICON] = settingsStore.chat.showModelIcon
      localData[SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_USER_AVATAR] = settingsStore.chat.showUserAvatar

      // If we have local data, migrate it to backend
      if (Object.keys(localData).length > 0) {
        await preferencesSync.syncLocalToBackend(localData, 'general')
      }
    } catch (err) {
      console.error('[PreferencesLoader] Migration failed:', err)
      // Don't throw - migration failure shouldn't block login
    }
  }

  /**
   * Force sync current state to backend
   */
  const syncCurrentState = useCallback(async () => {
    await preferencesSync.flush()
  }, [])

  return {
    loadAllPreferences,
    syncCurrentState,
    isLoading,
    error,
  }
}
