import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User } from '@/api/types'
import { setTokens, clearTokens } from '@/api/client'
import { authApi } from '@/api/endpoints'
import { useDevAuth, devLogin, devRegister } from '@/api/dev-auth'
import { clearUserStorage, migrateToUserScopedStorage, cleanupLegacyStorage, clearUserIdCache } from '@/lib/userScopedStorage'
import { preferencesSync } from '@/lib/preferencesSync'
import { clearCurrentUserCache } from '@/utils/attachmentCache'
import { toErrorMessage, hasErrorResponse } from '@/utils/errorMessages'

/**
 * Extract a user-friendly error message from an API error response
 */
function extractErrorMessage(error: unknown, fallback: string): string {
  const data: unknown = hasErrorResponse(error) ? error.response?.data : undefined

  if (!data) {
    // Network error or no response
    if (toErrorMessage(error).includes('Network Error')) {
      return 'Unable to connect to the server. Please check your internet connection.'
    }
    return fallback
  }

  // Handle different error response formats from Django/DRF
  if (typeof data === 'string') {
    return data
  }

  const fields = data as Record<string, unknown>

  // Common DRF error formats
  if (typeof fields.detail === 'string') {
    return fields.detail
  }

  if (typeof fields.message === 'string') {
    return fields.message
  }

  if (typeof fields.error === 'string') {
    return fields.error
  }

  // Non-field errors (e.g., invalid credentials)
  if (fields.non_field_errors) {
    return Array.isArray(fields.non_field_errors)
      ? fields.non_field_errors.join(' ')
      : String(fields.non_field_errors)
  }

  // Field-specific errors - combine them
  const fieldErrors: string[] = []
  for (const [field, errors] of Object.entries(fields)) {
    if (Array.isArray(errors)) {
      const fieldName = field.replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase())
      fieldErrors.push(`${fieldName}: ${errors.join(', ')}`)
    } else if (typeof errors === 'string') {
      const fieldName = field.replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase())
      fieldErrors.push(`${fieldName}: ${errors}`)
    }
  }

  if (fieldErrors.length > 0) {
    return fieldErrors.join('. ')
  }

  return fallback
}

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null

  // Actions
  login: (email: string, password: string) => Promise<void>
  register: (
    email: string,
    password: string,
    firstName: string,
    lastName: string,
    turnstileToken?: string,
  ) => Promise<void>
  logout: () => Promise<void>
  fetchProfile: () => Promise<void>
  setUser: (user: User | null) => void
  clearError: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,
      isLoading: true, // Start true - will be set false after rehydration
      error: null,

      login: async (email, password) => {
        set({ isLoading: true, error: null })
        try {
          let loginData

          // Use dev auth if enabled
          if (useDevAuth()) {
            loginData = await devLogin(email, password)
          } else {
            const response = await authApi.login({ email, password })
            loginData = response.data
          }

          // Backend returns access_token/refresh_token, normalize the keys
          const access = loginData.access || loginData.access_token
          const refresh = loginData.refresh || loginData.refresh_token
          const user = loginData.user

          if (!access || !refresh) {
            throw new Error('Invalid login response: missing tokens')
          }

          setTokens(access, refresh)

          // Migrate old non-scoped storage to user-scoped storage
          if (user?.id) {
            const storeNames = ['model-storage', 'navigation-storage', 'onboarding-storage', 'ui-storage']

            // Migrate any existing data from old keys to user-scoped keys
            migrateToUserScopedStorage(user.id, storeNames)

            // Clean up legacy non-scoped keys after migration
            cleanupLegacyStorage(storeNames)
          }

          set({
            user,
            isAuthenticated: true,
            isLoading: false,
          })

          // Load preferences from backend after successful login
          // This runs async in background - don't await to avoid blocking login
          import('@/store/modelStore').then(({ default: useModelStore }) => {
            // Reset hydration flag before rehydrating
            // This ensures setDefaultModelIfNeeded waits for fresh rehydration
            useModelStore.setState({ _hasHydrated: false })

            // Trigger rehydration of model store now that user is authenticated
            // This ensures we load the correct user's data from localStorage

            useModelStore.persist.rehydrate()

            // Rehydrate settings store too so user-scoped settings (code theme, etc.) are loaded
            import('@/store/settingsStore').then(({ useSettingsStore }) => {
              useSettingsStore.persist.rehydrate()
            })

            // Then load preferences from backend
            import('@/hooks/usePreferencesLoader').then(({ loadPreferencesFromBackend }) => {
              loadPreferencesFromBackend()
                .then(() => {
                  // After preferences are loaded, set a default model if user doesn't have one
                  return useModelStore.getState().setDefaultModelIfNeeded()
                })
                .catch((err) => {
                  console.error('[AuthStore] Failed to load preferences after login:', err)
                })
            })
          })
        } catch (error) {
          const errorMessage = extractErrorMessage(error, 'Unable to sign in. Please check your email and password.')
          set({
            error: errorMessage,
            isLoading: false,
          })
          throw error
        }
      },

      register: async (email, password, firstName, lastName, turnstileToken) => {
        set({ isLoading: true, error: null })
        try {
          // Use dev auth if enabled
          if (useDevAuth()) {
            await devRegister(email, password, firstName, lastName)
          } else {
            await authApi.register({
              email,
              password,
              password_confirm: password,
              full_name: `${firstName} ${lastName}`.trim(),
              ...(turnstileToken ? { turnstile_token: turnstileToken } : {}),
            })
          }
          set({ isLoading: false })
        } catch (error) {
          const errorMessage = extractErrorMessage(error, 'Unable to create account. Please try again.')
          set({
            error: errorMessage,
            isLoading: false,
          })
          throw error
        }
      },

      logout: async () => {
        const currentUser = get().user

        set({ isLoading: true })
        try {
          // Flush preferences sync queue before logging out
          await preferencesSync.flush()

          await authApi.logout()
        } catch (error) {
          console.error('Logout error:', error)
        } finally {
          clearTokens()

          // Clear getUserId cache to avoid stale data
          clearUserIdCache()

          // Clear user-scoped storage if user exists
          if (currentUser?.id) {
            clearUserStorage(currentUser.id, [
              'model-storage',
              'navigation-storage',
              'onboarding-storage',
              'ui-storage',
            ])
          }

          // Clear all stored data to prevent data leakage between users
          localStorage.removeItem('auth-storage')
          localStorage.removeItem('project-storage')
          localStorage.removeItem('current_project_id')
          localStorage.removeItem('consigliere-storage')
          localStorage.removeItem('modelComparisonGroups')
          // Clear conversations cache (user-scoped key)
          try {
            if (currentUser?.id) {
              localStorage.removeItem(`chat-groups-${currentUser.id}`)
            } else {
              localStorage.removeItem('chat-groups')
            }
          } catch {}

          // Clear user attachment cache (IndexedDB)
          try {
            await clearCurrentUserCache()
          } catch (e) {
            console.warn('[AuthStore] Failed to clear attachment cache:', e)
          }

          // Clean up legacy non-scoped keys (fallback)
          localStorage.removeItem('model-storage')
          localStorage.removeItem('navigation-storage')
          localStorage.removeItem('onboarding-storage')

          // Clear session storage items that could cause duplicate actions on re-login
          sessionStorage.removeItem('pending-message')

          // Note: Keep theme preference as it's user preference, not user data

          set({
            user: null,
            isAuthenticated: false,
            isLoading: false,
          })

          // Force reload to reset all stores
          window.location.href = '/login'
        }
      },

      fetchProfile: async () => {
        try {
          
          const response = await authApi.getProfile()
          
          set({
            user: response.data,
            isAuthenticated: true,
          })
        } catch (error) {
          console.error('[AuthStore] Failed to fetch profile:', error)
          console.error('[AuthStore] Error details:', {
            status: hasErrorResponse(error) ? error.response?.status : undefined,
            data: hasErrorResponse(error) ? error.response?.data : undefined,
            message: toErrorMessage(error),
          })

          // Log specific warning for 401 errors
          if (hasErrorResponse(error) && error.response?.status === 401) {
            console.warn('[AuthStore] Received 401 when fetching profile - token may be invalid')
            console.warn('[AuthStore] Axios interceptor will handle token refresh and redirect')
          }

          // Re-throw the error so caller can handle it
          // This ensures .catch() is executed in useAuthInit instead of .then()
          throw error
        }
      },

      setUser: (user) => {
        set({
          user,
          isAuthenticated: user !== null,
        })
      },

      clearError: () => {
        set({ error: null })
      },
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
      onRehydrateStorage: () => (state, error) => {
        // After rehydration completes, set isLoading to false
        // This prevents the race condition where ProtectedRoute
        // sees isLoading=false before auth state is restored
        if (error) {
          console.error('[AuthStore] Rehydration error:', error)
        }
        // Use setTimeout to ensure this runs after the current tick
        // when the store is fully initialized
        setTimeout(() => {
          useAuthStore.setState({ isLoading: false })
        }, 0)
      },
    }
  )
)
