import { create } from 'zustand'

type HelpTab = 'faq' | 'contact' | 'status'

interface HelpDrawerState {
  isOpen: boolean
  activeTab: HelpTab
  open: (tab?: HelpTab) => void
  close: () => void
  setTab: (tab: HelpTab) => void
}

export const useHelpDrawerStore = create<HelpDrawerState>((set) => ({
  isOpen: false,
  activeTab: 'faq',
  open: (tab = 'faq') => set({ isOpen: true, activeTab: tab }),
  close: () => set({ isOpen: false }),
  setTab: (tab) => set({ activeTab: tab }),
}))
