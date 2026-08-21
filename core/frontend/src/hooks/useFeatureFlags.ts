import { useEffect } from 'react'
import { create } from 'zustand'
import { featureFlagsApi, getReleaseStage, type ReleaseStage } from '@/api/featureFlags'

interface FeatureFlagsStore {
  flags: Record<string, ReleaseStage>
  loaded: boolean
  fetch: () => Promise<void>
}

export const useFeatureFlagsStore = create<FeatureFlagsStore>((set, get) => ({
  flags: {},
  loaded: false,
  fetch: async () => {
    if (get().loaded) return
    try {
      const flags = await featureFlagsApi.get()
      set({ flags, loaded: true })
    } catch {
      // On error default all features to GA — no badges shown
      set({ loaded: true })
    }
  },
}))

export function useFeatureFlags() {
  const { flags, loaded, fetch } = useFeatureFlagsStore()
  useEffect(() => { fetch() }, [fetch])
  return {
    loaded,
    getStage: (key: string): ReleaseStage => getReleaseStage(flags, key),
  }
}
