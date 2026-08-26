/**
 * Persists whether a conversation is shown in immersive mode, keyed per
 * conversation id. Backed by localStorage only (no backend API call) so the
 * preference is available instantly without a network round trip.
 */
import { useCallback } from 'react'

function getImmersiveModeKey(conversationId: string) {
  return `models.immersive_mode.${conversationId}`
}

export function useImmersiveModePreference() {
  const saveImmersiveMode = useCallback((conversationId: string, isImmersive: boolean) => {
    try {
      localStorage.setItem(getImmersiveModeKey(conversationId), JSON.stringify(isImmersive))
    } catch (e) {
      // localStorage might be full or disabled
    }
  }, [])

  const loadImmersiveMode = useCallback((conversationId: string, defaultValue: boolean): boolean => {
    const key = getImmersiveModeKey(conversationId)

    try {
      const saved = localStorage.getItem(key)
      if (saved !== null) {
        return JSON.parse(saved)
      }
    } catch (e) {
      // Parse error or localStorage disabled
    }

    return defaultValue
  }, [])

  return { saveImmersiveMode, loadImmersiveMode }
}
