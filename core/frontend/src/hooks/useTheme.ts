import { useEffect } from 'react'
import { useThemeStore } from '@/store/themeStore'

type Theme = 'light' | 'dark' | 'system'

export function useTheme() {
  const { theme, setTheme: setStoreTheme, toggleTheme: toggleStoreTheme } = useThemeStore()

  // Get system preference
  const getSystemTheme = (): 'light' | 'dark' => {
    if (typeof window !== 'undefined') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    }
    return 'dark'
  }

  // Get effective theme (resolves 'system' to actual theme)
  const getEffectiveTheme = (): 'light' | 'dark' => {
    return theme === 'system' ? getSystemTheme() : theme
  }

  useEffect(() => {
    const root = window.document.documentElement
    const effectiveTheme = getEffectiveTheme()

    // Only update if the current class doesn't match the effective theme
    // This prevents unnecessary DOM updates and potential flashes
    const hasCorrectClass =
      (effectiveTheme === 'light' && root.classList.contains('light')) ||
      (effectiveTheme === 'dark' && root.classList.contains('dark'))

    if (!hasCorrectClass) {
      // Apply theme class for conditional styles
      // Note: :root has dark variables by default, .light overrides for light mode
      // But we still add .dark/.light classes for conditional utility styles
      if (effectiveTheme === 'light') {
        root.classList.remove('dark')
        root.classList.add('light')
      } else {
        root.classList.remove('light')
        root.classList.add('dark')
      }
    }
  }, [theme])

  // Listen to system theme changes
  useEffect(() => {
    if (theme !== 'system') return

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handleChange = () => {
      const root = window.document.documentElement
      const effectiveTheme = getEffectiveTheme()

      // Only update if the current class doesn't match the effective theme
      const hasCorrectClass =
        (effectiveTheme === 'light' && root.classList.contains('light')) ||
        (effectiveTheme === 'dark' && root.classList.contains('dark'))

      if (!hasCorrectClass) {
        // Apply theme class for conditional styles
        if (effectiveTheme === 'light') {
          root.classList.remove('dark')
          root.classList.add('light')
        } else {
          root.classList.remove('light')
          root.classList.add('dark')
        }
      }
    }

    mediaQuery.addEventListener('change', handleChange)
    return () => mediaQuery.removeEventListener('change', handleChange)
  }, [theme])

  const setTheme = (newTheme: Theme) => {
    setStoreTheme(newTheme)
    // Note: localStorage persistence is handled directly in themeStore
  }

  const toggleTheme = () => {
    toggleStoreTheme()
    // Note: localStorage persistence is handled directly in themeStore
  }

  const effectiveTheme = getEffectiveTheme()

  return {
    theme,
    setTheme,
    toggleTheme,
    isDark: effectiveTheme === 'dark',
    isLight: effectiveTheme === 'light',
    isSystem: theme === 'system'
  }
}
