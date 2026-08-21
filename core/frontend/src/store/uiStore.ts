import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { createUserScopedStorage } from '../lib/userScopedStorage'
import { preferencesSync } from '../lib/preferencesSync'
import { PREFERENCE_KEYS } from '../hooks/usePreferencesLoader'

interface UIState {
  // Sidebar state
  isSidebarOpen: boolean
  isMobile: boolean

  // Notifications
  notifications: Notification[]

  // Actions
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  setMobile: (mobile: boolean) => void
  addNotification: (notification: Omit<Notification, 'id'>) => void
  removeNotification: (id: string) => void
  clearNotifications: () => void
}

interface Notification {
  id: string
  type: 'success' | 'error' | 'warning' | 'info'
  title: string
  message?: string
  duration?: number
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      // Initial state
      isSidebarOpen: true,
      isMobile: false,
      notifications: [],

      // Actions
      toggleSidebar: () => {
        set((state) => {
          const newValue = !state.isSidebarOpen

          // Sync to backend
          preferencesSync.update(PREFERENCE_KEYS.UI_SIDEBAR_OPEN, newValue, 'ui')

          return { isSidebarOpen: newValue }
        })
      },

      setSidebarOpen: (open) => {
        set({ isSidebarOpen: open })

        // Sync to backend
        preferencesSync.update(PREFERENCE_KEYS.UI_SIDEBAR_OPEN, open, 'ui')
      },

      setMobile: (mobile) => set({ isMobile: mobile }),

      addNotification: (notification) => {
        const id = Math.random().toString(36).substring(7)
        const newNotification = { ...notification, id }

        set((state) => ({
          notifications: [...state.notifications, newNotification]
        }))

        // Auto-remove notification after duration
        if (notification.duration !== 0) {
          setTimeout(() => {
            set((state) => ({
              notifications: state.notifications.filter((n) => n.id !== id)
            }))
          }, notification.duration || 5000)
        }
      },

      removeNotification: (id) => set((state) => ({
        notifications: state.notifications.filter((n) => n.id !== id)
      })),

      clearNotifications: () => set({ notifications: [] }),
    }),
    {
      name: 'ui-storage',
      storage: createUserScopedStorage('ui-storage'),
      partialize: (state) => ({
        isSidebarOpen: state.isSidebarOpen,
      }),
    }
  )
)