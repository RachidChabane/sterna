import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { LucideIcon } from 'lucide-react'
import { createUserScopedStorage } from '../lib/userScopedStorage'
import { preferencesSync } from '../lib/preferencesSync'
import { PREFERENCE_KEYS } from '../hooks/usePreferencesLoader'
import { defaultNavigation } from '../config/navigation'

export interface NavigationItem {
  id: string
  name: string
  href: string
  icon: LucideIcon
  keywords?: string[]
  comingSoon?: boolean
  beta?: boolean
}

interface NavigationState {
  navigationOrder: string[]
  setNavigationOrder: (order: string[]) => void
  reorderNavigation: (activeId: string, overId: string) => void
  isCollapsed: boolean
  setIsCollapsed: (collapsed: boolean) => void
  // Mobile sidebar state (not persisted)
  isMobileSidebarOpen: boolean
  setMobileSidebarOpen: (open: boolean) => void
  openMobileSidebar: () => void
  closeMobileSidebar: () => void
}

export const useNavigationStore = create<NavigationState>()(
  persist(
    (set, get) => ({
      navigationOrder: [],
      isCollapsed: false,
      isMobileSidebarOpen: false,

      setMobileSidebarOpen: (open: boolean) => set({ isMobileSidebarOpen: open }),
      openMobileSidebar: () => set({ isMobileSidebarOpen: true }),
      closeMobileSidebar: () => set({ isMobileSidebarOpen: false }),

      setNavigationOrder: (order: string[]) => {
        // Validate against current defaults — if items were added/removed, reset to defaults
        const defaultIds = new Set(defaultNavigation.map(item => item.id))
        const orderIds = new Set(order)
        const hasMissing = [...defaultIds].some(id => !orderIds.has(id))
        const hasStale = [...orderIds].some(id => !defaultIds.has(id))
        const finalOrder = (hasMissing || hasStale)
          ? defaultNavigation.map(item => item.id)
          : order

        set({ navigationOrder: finalOrder })

        // Sync to backend
        preferencesSync.update(PREFERENCE_KEYS.UI_NAVIGATION_ORDER, finalOrder, 'ui')
      },

      reorderNavigation: (activeId: string, overId: string) => {
        const { navigationOrder } = get()

        if (activeId === overId) return

        const oldIndex = navigationOrder.indexOf(activeId)
        const newIndex = navigationOrder.indexOf(overId)

        const newOrder = [...navigationOrder]
        newOrder.splice(oldIndex, 1)
        newOrder.splice(newIndex, 0, activeId)

        set({ navigationOrder: newOrder })

        // Sync to backend
        preferencesSync.update(PREFERENCE_KEYS.UI_NAVIGATION_ORDER, newOrder, 'ui')
      },

      setIsCollapsed: (collapsed: boolean) => {
        set({ isCollapsed: collapsed })
        // Note: Only persisted to localStorage - no backend sync needed for UI state
      },
    }),
    {
      name: 'navigation-storage',
      storage: createUserScopedStorage('navigation-storage'),
      // Don't persist mobile sidebar state
      partialize: (state) => ({
        navigationOrder: state.navigationOrder,
        isCollapsed: state.isCollapsed,
      }),
      // Validate navigation order on hydration — reset if defaults changed
      merge: (persisted, current) => {
        const state = { ...current, ...(persisted as Partial<NavigationState>) }
        if (state.navigationOrder.length > 0) {
          const defaultIds = new Set(defaultNavigation.map(item => item.id))
          const storedIds = new Set(state.navigationOrder)
          const hasMissing = [...defaultIds].some(id => !storedIds.has(id))
          const hasStale = [...storedIds].some(id => !defaultIds.has(id))
          if (hasMissing || hasStale) {
            state.navigationOrder = defaultNavigation.map(item => item.id)
          }
        }
        return state
      },
    }
  )
)
