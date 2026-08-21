/**
 * Apps Store
 *
 * Manages ephemeral preview state (running/port) for Apps.
 * Port is NOT persisted — it's transient and tracked only in Zustand.
 */

import { create } from 'zustand'

interface AppPreviewState {
  running: boolean
  port: number | null
  loading: boolean
}

interface AppsStoreState {
  previewStates: Record<string, AppPreviewState>
  setPreviewState: (appId: string, state: Partial<AppPreviewState>) => void
  clearPreviewState: (appId: string) => void
  clearAllPreviews: () => void
}

export const useAppsStore = create<AppsStoreState>()((set) => ({
  previewStates: {},

  setPreviewState: (appId, state) =>
    set((prev) => ({
      previewStates: {
        ...prev.previewStates,
        [appId]: {
          ...{ running: false, port: null, loading: false },
          ...prev.previewStates[appId],
          ...state,
        },
      },
    })),

  clearPreviewState: (appId) =>
    set((prev) => {
      const { [appId]: _, ...rest } = prev.previewStates
      return { previewStates: rest }
    }),

  clearAllPreviews: () => set({ previewStates: {} }),
}))
