import { useState, useEffect } from 'react'
import { openRouterApi } from '@/api/endpoints'

interface ModelStats {
  total: number
  providers: number
  providersList: string[]
}

// Singleton cache to prevent duplicate API calls across components
let cachedStats: ModelStats | null = null
let fetchPromise: Promise<ModelStats> | null = null

async function fetchModelStats(): Promise<ModelStats> {
  // Return cached data if available
  if (cachedStats) {
    return cachedStats
  }

  // If a fetch is already in progress, wait for it
  if (fetchPromise) {
    return fetchPromise
  }

  // Start new fetch
  fetchPromise = openRouterApi.modelStats()
    .then((response) => {
      cachedStats = {
        total: response.data.total_models || 0,
        providers: response.data.total_providers || 0,
        providersList: response.data.providers_list || [],
      }
      return cachedStats
    })
    .catch((error) => {
      console.error('Failed to fetch model stats:', error)
      // Return empty stats on error
      return { total: 0, providers: 0, providersList: [] }
    })
    .finally(() => {
      fetchPromise = null
    })

  return fetchPromise
}

export function useModelStats() {
  const [stats, setStats] = useState<ModelStats>(() =>
    cachedStats || { total: 0, providers: 0, providersList: [] }
  )
  const [loading, setLoading] = useState(!cachedStats)

  useEffect(() => {
    // If we already have cached stats, use them immediately
    if (cachedStats) {
      setStats(cachedStats)
      setLoading(false)
      return
    }

    // Fetch stats
    setLoading(true)
    fetchModelStats().then((data) => {
      setStats(data)
      setLoading(false)
    })
  }, [])

  return { stats, loading }
}

// Function to invalidate cache if needed (e.g., after data changes)
