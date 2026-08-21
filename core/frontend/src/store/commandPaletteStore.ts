import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { CommandItem } from '@/components/command-palette/types'

/**
 * Command Palette Store
 *
 * Global store for the command palette state (⌘K / Ctrl+K)
 * Manages open/close state, search query, and recent items history
 */
interface CommandPaletteStore {
  // State
  open: boolean
  query: string
  recentItems: CommandItem[]

  // Actions
  setOpen: (open: boolean) => void
  setQuery: (query: string) => void
  addToRecent: (item: CommandItem) => void
  clearRecent: () => void
}

const MAX_RECENT_ITEMS = 5

const useCommandPaletteStore = create<CommandPaletteStore>()(
  persist(
    (set, get) => ({
      // Initial state
      open: false,
      query: '',
      recentItems: [],

      // Toggle open/close
      setOpen: (open) => {
        set({ open })
        // Clear query when closing
        if (!open) {
          set({ query: '' })
        }
      },

      // Update search query
      setQuery: (query) => {
        set({ query })
      },

      // Add item to recent history
      addToRecent: (item) => {
        const { recentItems } = get()

        // Remove item if already in recent (to move it to top)
        const filtered = recentItems.filter((i) => i.id !== item.id)

        // Add to beginning and limit to MAX_RECENT_ITEMS
        set({
          recentItems: [item, ...filtered].slice(0, MAX_RECENT_ITEMS),
        })
      },

      // Clear all recent items
      clearRecent: () => {
        set({ recentItems: [] })
      },
    }),
    {
      name: 'command-palette-storage',
      // Only persist recent items
      partialize: (state) => ({
        recentItems: state.recentItems,
      }),
    }
  )
)

export default useCommandPaletteStore
