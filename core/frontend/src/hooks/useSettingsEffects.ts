/**
 * useSettingsEffects
 *
 * Centralized hook that applies all global settings effects to the app.
 * This hook should be called once at the app root level.
 *
 * Effects applied:
 * - Font size (CSS custom property)
 * - Reduce motion (CSS class + prefers-reduced-motion)
 * - High contrast (CSS class)
 *
 * Also persists visual settings to a simple localStorage key for
 * instant application on page load (before React hydrates).
 */

import { useEffect } from 'react'
import { useSettingsStore } from '@/store/settingsStore'

// localStorage key for visual settings (read by inline script in index.html)
const VISUAL_SETTINGS_KEY = 'sterna-visual-settings'

// Font size mappings
const FONT_SIZE_SCALE = {
  small: 0.875,   // 87.5% - 14px base
  medium: 1,      // 100% - 16px base
  large: 1.125,   // 112.5% - 18px base
} as const

/**
 * Save visual settings to simple localStorage for instant load
 */
function saveVisualSettings(settings: {
  fontSize: string
  reduceMotion: boolean
  highContrast: boolean
}) {
  try {
    localStorage.setItem(VISUAL_SETTINGS_KEY, JSON.stringify(settings))
  } catch (e) {
    // Ignore storage errors
  }
}

/**
 * Apply global settings effects to the document
 * Call this hook once at the root of your app
 */
export function useSettingsEffects() {
  const { accessibility } = useSettingsStore()
  const { fontSize, reduceMotion, highContrast } = accessibility

  // Save visual settings to localStorage whenever they change
  // This allows the inline script to read them on next page load
  useEffect(() => {
    saveVisualSettings({ fontSize, reduceMotion, highContrast })
  }, [fontSize, reduceMotion, highContrast])

  // Apply font size
  useEffect(() => {
    const scale = FONT_SIZE_SCALE[fontSize]
    document.documentElement.style.setProperty('--settings-font-scale', String(scale))
    document.documentElement.style.fontSize = `${scale * 100}%`
    document.documentElement.dataset.fontSize = fontSize

    return () => {
      document.documentElement.style.removeProperty('--settings-font-scale')
      document.documentElement.style.fontSize = ''
      delete document.documentElement.dataset.fontSize
    }
  }, [fontSize])

  // Apply reduce motion
  useEffect(() => {
    if (reduceMotion) {
      document.documentElement.classList.add('reduce-motion')
      document.documentElement.dataset.reduceMotion = 'true'
    } else {
      document.documentElement.classList.remove('reduce-motion')
      delete document.documentElement.dataset.reduceMotion
    }

    return () => {
      document.documentElement.classList.remove('reduce-motion')
      delete document.documentElement.dataset.reduceMotion
    }
  }, [reduceMotion])

  // Apply high contrast
  useEffect(() => {
    if (highContrast) {
      document.documentElement.classList.add('high-contrast')
      document.documentElement.dataset.highContrast = 'true'
    } else {
      document.documentElement.classList.remove('high-contrast')
      delete document.documentElement.dataset.highContrast
    }

    return () => {
      document.documentElement.classList.remove('high-contrast')
      delete document.documentElement.dataset.highContrast
    }
  }, [highContrast])
}

export default useSettingsEffects
