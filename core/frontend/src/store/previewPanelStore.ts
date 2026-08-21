import { create } from 'zustand'
import { useNavigationStore } from './navigationStore'

interface PreviewPanelState {
  isPanelOpen: boolean
  previewPort: number | null

  openPanel: () => void
  closePanel: () => void
  setPreviewPort: (port: number | null) => void
  reset: () => void
}

export const usePreviewPanelStore = create<PreviewPanelState>((set) => ({
  isPanelOpen: false,
  previewPort: null,

  openPanel: () => {
    set({ isPanelOpen: true })
    useNavigationStore.getState().setIsCollapsed(true)
  },

  closePanel: () => {
    set({ isPanelOpen: false })
  },

  setPreviewPort: (port) => {
    set({ previewPort: port })
  },

  reset: () => {
    set({ isPanelOpen: false, previewPort: null })
  },
}))
