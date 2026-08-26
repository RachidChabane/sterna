/**
 * Custom hook for the "open port in preview" panel: tracks the active
 * preview port and fetches/refreshes its short-lived preview token.
 */

import { useEffect, useState } from 'react'
import { fetchPreviewToken } from '@/api/sandbox'

// Refresh token every 4 minutes (before 5-min expiry)
const TOKEN_REFRESH_INTERVAL_MS = 240_000

interface UsePreviewPanelParams {
  userId?: string
}

export function usePreviewPanel({ userId }: UsePreviewPanelParams) {
  const [previewPort, setPreviewPort] = useState<number | null>(null)
  const [previewToken, setPreviewToken] = useState<string | null>(null)
  const [previewTokenLoading, setPreviewTokenLoading] = useState(false)

  // Preview token lifecycle: fetch on port change, auto-refresh before expiry
  useEffect(() => {
    if (!previewPort || !userId) {
      setPreviewToken(null)
      setPreviewTokenLoading(false)
      return
    }

    let cancelled = false
    let refreshTimer: ReturnType<typeof setInterval> | null = null

    const fetchToken = async () => {
      try {
        setPreviewTokenLoading(true)
        const token = await fetchPreviewToken(userId, previewPort)
        if (!cancelled) {
          setPreviewToken(token)
          setPreviewTokenLoading(false)
        }
      } catch (e) {
        if (!cancelled) {
          console.error('Failed to fetch preview token:', e)
          setPreviewTokenLoading(false)
        }
      }
    }

    fetchToken()
    refreshTimer = setInterval(fetchToken, TOKEN_REFRESH_INTERVAL_MS)

    return () => {
      cancelled = true
      if (refreshTimer) clearInterval(refreshTimer)
    }
  }, [previewPort, userId])

  return {
    previewPort,
    setPreviewPort,
    previewToken,
    previewTokenLoading,
  }
}
