/**
 * Artifacts Panel Store
 *
 * Manages the state for the unified artifacts side panel that displays
 * Sparks, Images, and Videos from the current chat.
 */

import { create } from 'zustand'
import { useNavigationStore } from './navigationStore'

export type ArtifactSection = 'sparks' | 'images' | 'videos' | 'apps'

interface ArtifactsPanelState {
  // Panel visibility
  isPanelOpen: boolean
  setPanelOpen: (open: boolean) => void

  // Active section (tab)
  activeSection: ArtifactSection
  setActiveSection: (section: ArtifactSection) => void

  // Selected item within a section
  selectedSparkId: string | null
  selectedImageId: string | null
  selectedVideoId: string | null
  selectedAppId: string | null
  setSelectedSparkId: (id: string | null) => void
  setSelectedImageId: (id: string | null) => void
  setSelectedVideoId: (id: string | null) => void
  setSelectedAppId: (id: string | null) => void

  // Asset counts (for header button display)
  imageCount: number
  videoCount: number
  setAssetCounts: (images: number, videos: number) => void

  // Convenience methods
  openPanel: (section?: ArtifactSection) => void
  closePanel: () => void
  backToList: () => void

  // Legacy compatibility (for SparkDisplay component)
  openSparkInPanel: (sparkId: string) => void
  openAppInPanel: (appId: string) => void
}

export const useArtifactsPanelStore = create<ArtifactsPanelState>()((set, get) => ({
  isPanelOpen: false,
  activeSection: 'sparks',
  selectedSparkId: null,
  selectedImageId: null,
  selectedVideoId: null,
  selectedAppId: null,
  imageCount: 0,
  videoCount: 0,

  setPanelOpen: (open: boolean) => {
    set({ isPanelOpen: open })
    if (open) {
      // Auto-collapse sidebar when panel opens
      useNavigationStore.getState().setIsCollapsed(true)
    }
  },

  setActiveSection: (section: ArtifactSection) => {
    set({ activeSection: section })
  },

  setSelectedSparkId: (id: string | null) => {
    set({ selectedSparkId: id })
  },

  setSelectedImageId: (id: string | null) => {
    set({ selectedImageId: id })
  },

  setSelectedVideoId: (id: string | null) => {
    set({ selectedVideoId: id })
  },

  setSelectedAppId: (id: string | null) => {
    set({ selectedAppId: id })
  },

  setAssetCounts: (images: number, videos: number) => {
    set({ imageCount: images, videoCount: videos })
  },

  openPanel: (section?: ArtifactSection) => {
    set({
      isPanelOpen: true,
      ...(section && { activeSection: section }),
    })
    useNavigationStore.getState().setIsCollapsed(true)
  },

  closePanel: () => {
    set({
      isPanelOpen: false,
      selectedSparkId: null,
      selectedImageId: null,
      selectedVideoId: null,
      selectedAppId: null,
    })
  },

  backToList: () => {
    const { activeSection } = get()
    if (activeSection === 'sparks') {
      set({ selectedSparkId: null })
    } else if (activeSection === 'images') {
      set({ selectedImageId: null })
    } else if (activeSection === 'videos') {
      set({ selectedVideoId: null })
    } else if (activeSection === 'apps') {
      set({ selectedAppId: null })
    }
  },

  // Legacy compatibility
  openSparkInPanel: (sparkId: string) => {
    set({
      isPanelOpen: true,
      activeSection: 'sparks',
      selectedSparkId: sparkId,
    })
    useNavigationStore.getState().setIsCollapsed(true)
  },

  openAppInPanel: (appId: string) => {
    set({
      isPanelOpen: true,
      activeSection: 'apps',
      selectedAppId: appId,
    })
    useNavigationStore.getState().setIsCollapsed(true)
  },
}))
