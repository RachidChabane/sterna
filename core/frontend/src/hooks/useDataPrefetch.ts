/**
 * Data Prefetching Hook
 *
 * Prefetches data for common routes after authentication to enable
 * instant navigation (SPA feel). Data is cached in Zustand stores.
 */

import { useEffect, useRef } from 'react'
import { useAuthStore } from '@/store/authStore'
import useModelStore from '@/store/modelStore'
import { useMCPStore } from '@/store/mcpStore'
import useVoiceRoomStore from '@/store/voiceRoomStore'

export function useDataPrefetch() {
  const { isAuthenticated } = useAuthStore()
  const { models, fetchModels } = useModelStore()
  const { servers, preconfiguredServers, fetchAllMCPData } = useMCPStore()
  const { rooms, fetchRooms } = useVoiceRoomStore()
  const hasPrefetched = useRef(false)

  useEffect(() => {
    // Only prefetch once after authentication
    if (!isAuthenticated || hasPrefetched.current) return

    hasPrefetched.current = true

    // Prefetch critical data immediately for instant navigation
    // These run in parallel and don't block the UI
    const prefetchImmediate = () => {
      // Prefetch models (critical for /models page)
      if (!models || models.length === 0) {
        fetchModels().catch(() => {})
      }

      // Prefetch MCP data (critical for /connectors page)
      if ((!servers || servers.length === 0) || (!preconfiguredServers || preconfiguredServers.length === 0)) {
        fetchAllMCPData?.().catch(() => {})
      }

      // Prefetch voice rooms (critical for /voice-rooms page)
      if (!rooms || rooms.length === 0) {
        fetchRooms?.().catch(() => {})
      }
    }

    // Run prefetch immediately (non-blocking, runs in parallel)
    prefetchImmediate()
  }, [isAuthenticated, models, servers, preconfiguredServers, rooms, fetchModels, fetchAllMCPData, fetchRooms])
}
