import { create } from 'zustand'

interface NewConversation {
  id: string
  name: string
}

interface ActiveConversationStore {
  activeConversationId: string | null
  setActiveConversationId: (id: string | null) => void

  // Streaming title generation state
  generatingTitleForId: string | null
  generatingTitleText: string
  newConversation: NewConversation | null  // For showing new conversation before localStorage updates
  startGeneratingTitle: (conversationId: string, initialName?: string) => void
  updateGeneratingTitle: (text: string) => void
  finishGeneratingTitle: (finalTitle?: string) => void

  // Refresh trigger for sidebar
  refreshTrigger: number
  triggerRefresh: () => void
}

export const useActiveConversationStore = create<ActiveConversationStore>((set, get) => ({
  activeConversationId: null,
  setActiveConversationId: (id) => set({ activeConversationId: id }),

  // Streaming title generation
  generatingTitleForId: null,
  generatingTitleText: '',
  newConversation: null,
  startGeneratingTitle: (conversationId, initialName = 'New Conversation') => set({
    generatingTitleForId: conversationId,
    generatingTitleText: '',
    newConversation: { id: conversationId, name: initialName }
  }),
  updateGeneratingTitle: (text) => set((state) => ({
    generatingTitleText: text,
    // Also update newConversation.name so it stays in sync
    // This prevents any flash if there's a gap between streaming and finishGeneratingTitle
    newConversation: state.newConversation
      ? { ...state.newConversation, name: text || state.newConversation.name }
      : null
  })),
  finishGeneratingTitle: (finalTitle) => {
    const current = get()
    // Update newConversation with final title, keep it around for a bit
    // so sidebar doesn't flash back to "New Conversation" from stale localStorage
    if (finalTitle && current.newConversation) {
      set({
        generatingTitleForId: null,
        generatingTitleText: '',
        newConversation: { ...current.newConversation, name: finalTitle }
      })
      // Clear newConversation after localStorage has been updated
      // Note: localStorage saves are deferred via requestIdleCallback, which can take 30+ seconds
      // when the browser is busy. Using a longer timeout to ensure localStorage has caught up.
      setTimeout(() => {
        set({ newConversation: null })
      }, 60000)
    } else {
      set({
        generatingTitleForId: null,
        generatingTitleText: '',
        newConversation: null
      })
    }
  },

  // Refresh trigger - increment to force sidebar to reload conversations
  refreshTrigger: 0,
  triggerRefresh: () => set((state) => ({ refreshTrigger: state.refreshTrigger + 1 })),
}))
