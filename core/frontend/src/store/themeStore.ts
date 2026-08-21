import { create } from 'zustand'
import { preferencesSync } from '@/lib/preferencesSync'

type Theme = 'light' | 'dark' | 'system'

interface ThemeState {
  theme: Theme
  setTheme: (theme: Theme, skipSync?: boolean) => void
  toggleTheme: () => void
}

const THEME_STORAGE_KEY = 'sterna-theme'
const THEME_PREFERENCE_KEY = 'ui.theme'

/**
 * Get initial theme from localStorage synchronously
 * This prevents flash of wrong theme on page load
 */
const getInitialTheme = (): Theme => {
  if (typeof window === 'undefined') return 'system'

  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'system') {
      return stored
    }
  } catch (e) {
    console.warn('[ThemeStore] Failed to read theme from localStorage:', e)
  }

  return 'system'
}

/**
 * Sync theme to backend (debounced via preferencesSync)
 */
const syncThemeToBackend = (theme: Theme) => {
  try {
    preferencesSync.update(THEME_PREFERENCE_KEY, theme, 'ui')
  } catch (e) {
    console.error('[ThemeStore] Failed to sync theme to backend:', e)
  }
}

/**
 * Theme store with localStorage for instant access + backend sync for persistence
 *
 * - localStorage: Prevents flash of wrong theme on initial load
 * - Backend sync: Ensures theme persists across devices/browsers
 */
export const useThemeStore = create<ThemeState>((set) => ({
  theme: getInitialTheme(),

  setTheme: (theme, skipSync = false) => {
    set({ theme })
    try {
      // Always update localStorage for instant access on next page load
      localStorage.setItem(THEME_STORAGE_KEY, theme)
      // Sync to backend unless explicitly skipped (e.g., when loading from backend)
      if (!skipSync) {
        syncThemeToBackend(theme)
      }
    } catch (e) {
      console.error('[ThemeStore] Failed to save theme:', e)
    }
  },

  toggleTheme: () => {
    set((state) => {
      const newTheme = state.theme === 'dark' ? 'light' : 'dark'
      try {
        localStorage.setItem(THEME_STORAGE_KEY, newTheme)
        syncThemeToBackend(newTheme)
      } catch (e) {
        console.error('[ThemeStore] Failed to save theme:', e)
      }
      return { theme: newTheme }
    })
  },
}))
