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
import { useThemeStore } from '../store/themeStore'

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
    if (backendPrefs[PREFERENCE_KEYS.MODELS_FAVORITES]) {
      useModelStore.setState({
        favorites: backendPrefs[PREFERENCE_KEYS.MODELS_FAVORITES]
      })
      
    }

    if (backendPrefs[PREFERENCE_KEYS.MODELS_RECENT]) {
      useModelStore.setState({
        recentModels: backendPrefs[PREFERENCE_KEYS.MODELS_RECENT]
      })
      
    }

    if (backendPrefs[PREFERENCE_KEYS.MODELS_RECENT_CHAT]) {
      useModelStore.setState({
        recentChatModels: backendPrefs[PREFERENCE_KEYS.MODELS_RECENT_CHAT]
      })
      
    }

    if (backendPrefs[PREFERENCE_KEYS.MODELS_CURRENT]) {
      useModelStore.setState({
        currentModel: backendPrefs[PREFERENCE_KEYS.MODELS_CURRENT]
      })
      
    }

    // UI
    if (backendPrefs[PREFERENCE_KEYS.UI_SIDEBAR_OPEN] !== undefined) {
      useUIStore.getState().setSidebarOpen(backendPrefs[PREFERENCE_KEYS.UI_SIDEBAR_OPEN])
    }

    // Note: UI_SIDEBAR_COLLAPSED is only stored in localStorage, not synced to backend

    if (backendPrefs[PREFERENCE_KEYS.UI_NAVIGATION_ORDER]) {
      useNavigationStore.getState().setNavigationOrder(backendPrefs[PREFERENCE_KEYS.UI_NAVIGATION_ORDER])
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
    if (backendPrefs[PREFERENCE_KEYS.ONBOARDING_CURRENT_STEP] !== undefined) {
      useOnboardingStore.getState().setCurrentStep(backendPrefs[PREFERENCE_KEYS.ONBOARDING_CURRENT_STEP])
    }

    if (backendPrefs[PREFERENCE_KEYS.ONBOARDING_COMPLETED] !== undefined) {
      if (backendPrefs[PREFERENCE_KEYS.ONBOARDING_COMPLETED]) {
        useOnboardingStore.getState().completeOnboarding()
      }
    }

    if (backendPrefs[PREFERENCE_KEYS.ONBOARDING_SKIPPED_AT]) {
      useOnboardingStore.getState().skipOnboarding()
    }

    if (backendPrefs[PREFERENCE_KEYS.ONBOARDING_API_KEY_CONFIGURED] !== undefined) {
      useOnboardingStore.getState().setApiKeyConfigured(
        backendPrefs[PREFERENCE_KEYS.ONBOARDING_API_KEY_CONFIGURED]
      )
    }

    if (backendPrefs[PREFERENCE_KEYS.ONBOARDING_SAMPLE_EVALUATION_RUN] !== undefined) {
      useOnboardingStore.getState().setSampleEvaluationRun(
        backendPrefs[PREFERENCE_KEYS.ONBOARDING_SAMPLE_EVALUATION_RUN]
      )
    }

    // Settings - Load from backend using setState() to avoid triggering sync
    const settingsState: Record<string, any> = {}

    // TTS Settings
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_ENABLED] !== undefined) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.enabled = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_ENABLED]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_AUTO_READ] !== undefined) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.autoRead = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_AUTO_READ]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_VOICE_ID]) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.voiceId = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_VOICE_ID]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_VOICE_NAME]) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.voiceName = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_VOICE_NAME]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_LANGUAGE]) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.language = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_LANGUAGE]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_MODEL]) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.ttsModel = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_MODEL]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_STABILITY] !== undefined) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.stability = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_STABILITY]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_SIMILARITY_BOOST] !== undefined) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.similarityBoost = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_SIMILARITY_BOOST]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_STYLE] !== undefined) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.style = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_STYLE]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_SPEED] !== undefined) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.speed = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_SPEED]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_USE_SPEAKER_BOOST] !== undefined) {
      settingsState.tts = settingsState.tts || { ...useSettingsStore.getState().tts }
      settingsState.tts.useSpeakerBoost = backendPrefs[SETTINGS_PREFERENCE_KEYS.TTS_USE_SPEAKER_BOOST]
    }

    // Chat Settings
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_COMPACT_MODE] !== undefined) {
      settingsState.chat = settingsState.chat || { ...useSettingsStore.getState().chat }
      settingsState.chat.compactMode = backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_COMPACT_MODE]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_TIMESTAMPS] !== undefined) {
      settingsState.chat = settingsState.chat || { ...useSettingsStore.getState().chat }
      settingsState.chat.showTimestamps = backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_TIMESTAMPS]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_MODEL_NAME] !== undefined) {
      settingsState.chat = settingsState.chat || { ...useSettingsStore.getState().chat }
      settingsState.chat.showModelName = backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_MODEL_NAME]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_ENTER_TO_SEND] !== undefined) {
      settingsState.chat = settingsState.chat || { ...useSettingsStore.getState().chat }
      settingsState.chat.enterToSend = backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_ENTER_TO_SEND]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_STREAM_RESPONSES] !== undefined) {
      settingsState.chat = settingsState.chat || { ...useSettingsStore.getState().chat }
      settingsState.chat.streamResponses = backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_STREAM_RESPONSES]
    }

    // Accessibility Settings
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.ACCESSIBILITY_FONT_SIZE]) {
      settingsState.accessibility = settingsState.accessibility || { ...useSettingsStore.getState().accessibility }
      settingsState.accessibility.fontSize = backendPrefs[SETTINGS_PREFERENCE_KEYS.ACCESSIBILITY_FONT_SIZE]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.ACCESSIBILITY_REDUCE_MOTION] !== undefined) {
      settingsState.accessibility = settingsState.accessibility || { ...useSettingsStore.getState().accessibility }
      settingsState.accessibility.reduceMotion = backendPrefs[SETTINGS_PREFERENCE_KEYS.ACCESSIBILITY_REDUCE_MOTION]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.ACCESSIBILITY_HIGH_CONTRAST] !== undefined) {
      settingsState.accessibility = settingsState.accessibility || { ...useSettingsStore.getState().accessibility }
      settingsState.accessibility.highContrast = backendPrefs[SETTINGS_PREFERENCE_KEYS.ACCESSIBILITY_HIGH_CONTRAST]
    }

    // Privacy Settings
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.PRIVACY_SAVE_HISTORY] !== undefined) {
      settingsState.privacy = settingsState.privacy || { ...useSettingsStore.getState().privacy }
      settingsState.privacy.saveConversationHistory = backendPrefs[SETTINGS_PREFERENCE_KEYS.PRIVACY_SAVE_HISTORY]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.PRIVACY_ANALYTICS] !== undefined) {
      settingsState.privacy = settingsState.privacy || { ...useSettingsStore.getState().privacy }
      settingsState.privacy.analyticsEnabled = backendPrefs[SETTINGS_PREFERENCE_KEYS.PRIVACY_ANALYTICS]
    }

    // Instructions Settings
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.INSTRUCTIONS_ENABLED] !== undefined) {
      settingsState.instructions = settingsState.instructions || { ...useSettingsStore.getState().instructions }
      settingsState.instructions.enabled = backendPrefs[SETTINGS_PREFERENCE_KEYS.INSTRUCTIONS_ENABLED]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.INSTRUCTIONS_CONTENT]) {
      settingsState.instructions = settingsState.instructions || { ...useSettingsStore.getState().instructions }
      settingsState.instructions.content = backendPrefs[SETTINGS_PREFERENCE_KEYS.INSTRUCTIONS_CONTENT]
    }

    // STT Settings
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.STT_LANGUAGE]) {
      settingsState.stt = settingsState.stt || { ...useSettingsStore.getState().stt }
      settingsState.stt.language = backendPrefs[SETTINGS_PREFERENCE_KEYS.STT_LANGUAGE]
    }

    // Watermark Settings
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.WATERMARK_ENABLED] !== undefined) {
      settingsState.watermark = settingsState.watermark || { ...useSettingsStore.getState().watermark }
      settingsState.watermark.enabled = backendPrefs[SETTINGS_PREFERENCE_KEYS.WATERMARK_ENABLED]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.WATERMARK_POSITION]) {
      settingsState.watermark = settingsState.watermark || { ...useSettingsStore.getState().watermark }
      settingsState.watermark.position = backendPrefs[SETTINGS_PREFERENCE_KEYS.WATERMARK_POSITION]
    }

    // Code Theme
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.CODE_THEME]) {
      settingsState.codeTheme = backendPrefs[SETTINGS_PREFERENCE_KEYS.CODE_THEME]
    }

    // Chat Settings - additional fields
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_MODEL_ICON] !== undefined) {
      settingsState.chat = settingsState.chat || { ...useSettingsStore.getState().chat }
      settingsState.chat.showModelIcon = backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_MODEL_ICON]
    }
    if (backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_USER_AVATAR] !== undefined) {
      settingsState.chat = settingsState.chat || { ...useSettingsStore.getState().chat }
      settingsState.chat.showUserAvatar = backendPrefs[SETTINGS_PREFERENCE_KEYS.CHAT_SHOW_USER_AVATAR]
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
    backendPrefs: Record<string, any>
  ): Promise<void> => {
    // Models
    if (backendPrefs[PREFERENCE_KEYS.MODELS_FAVORITES]) {
      // Note: Zustand persist middleware will handle this automatically
      // We just need to ensure the data is in the right format
      const favorites = backendPrefs[PREFERENCE_KEYS.MODELS_FAVORITES]
      
    }

    if (backendPrefs[PREFERENCE_KEYS.MODELS_RECENT]) {
      const recent = backendPrefs[PREFERENCE_KEYS.MODELS_RECENT]
      
    }

    if (backendPrefs[PREFERENCE_KEYS.MODELS_RECENT_CHAT]) {
      const recentChat = backendPrefs[PREFERENCE_KEYS.MODELS_RECENT_CHAT]
      
    }

    if (backendPrefs[PREFERENCE_KEYS.MODELS_CURRENT]) {
      const currentModel = backendPrefs[PREFERENCE_KEYS.MODELS_CURRENT]
      
    }

    // UI
    if (backendPrefs[PREFERENCE_KEYS.UI_SIDEBAR_OPEN] !== undefined) {
      uiStore.setSidebarOpen(backendPrefs[PREFERENCE_KEYS.UI_SIDEBAR_OPEN])
    }

    // Note: UI_SIDEBAR_COLLAPSED is only stored in localStorage, not synced to backend

    if (backendPrefs[PREFERENCE_KEYS.UI_NAVIGATION_ORDER]) {
      navigationStore.setNavigationOrder(backendPrefs[PREFERENCE_KEYS.UI_NAVIGATION_ORDER])
    }

    // Theme - Load from backend and apply (skipSync=true to avoid re-syncing)
    if (backendPrefs[PREFERENCE_KEYS.UI_THEME]) {
      const theme = backendPrefs[PREFERENCE_KEYS.UI_THEME]
      if (theme === 'light' || theme === 'dark' || theme === 'system') {
        useThemeStore.getState().setTheme(theme, true) // skipSync=true
      }
    }

    // Onboarding
    if (backendPrefs[PREFERENCE_KEYS.ONBOARDING_CURRENT_STEP] !== undefined) {
      onboardingStore.setCurrentStep(backendPrefs[PREFERENCE_KEYS.ONBOARDING_CURRENT_STEP])
    }

    if (backendPrefs[PREFERENCE_KEYS.ONBOARDING_COMPLETED] !== undefined) {
      // Only update if completed
      if (backendPrefs[PREFERENCE_KEYS.ONBOARDING_COMPLETED]) {
        onboardingStore.completeOnboarding()
      }
    }

    if (backendPrefs[PREFERENCE_KEYS.ONBOARDING_SKIPPED_AT]) {
      onboardingStore.skipOnboarding()
    }

    if (backendPrefs[PREFERENCE_KEYS.ONBOARDING_API_KEY_CONFIGURED] !== undefined) {
      onboardingStore.setApiKeyConfigured(
        backendPrefs[PREFERENCE_KEYS.ONBOARDING_API_KEY_CONFIGURED]
      )
    }

    if (backendPrefs[PREFERENCE_KEYS.ONBOARDING_SAMPLE_EVALUATION_RUN] !== undefined) {
      onboardingStore.setSampleEvaluationRun(
        backendPrefs[PREFERENCE_KEYS.ONBOARDING_SAMPLE_EVALUATION_RUN]
      )
    }
  }

  /**
   * Migrate localStorage data to backend (one-time migration)
   */
  const migrateLocalDataToBackend = async (): Promise<void> => {
    try {
      // Get current store states (which are from localStorage)
      const localData: Record<string, any> = {}

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
      } else {
        
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
