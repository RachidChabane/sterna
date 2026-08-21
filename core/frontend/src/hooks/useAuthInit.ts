import { useEffect, useRef } from 'react'
import { useRouterState } from '@tanstack/react-router'
import { useAuthStore } from '@/store/authStore'

/**
 * Hook to initialize auth state on app load.
 * Fetches fresh user profile data and loads user preferences if user is authenticated.
 */
export function useAuthInit() {
  const { isAuthenticated, fetchProfile } = useAuthStore()
  const routerState = useRouterState()
  const pathname = routerState.location.pathname
  const hasInitialized = useRef(false)

  useEffect(() => {
    // Don't run on public/auth pages to avoid redirect loops
    const publicPaths = ['/login', '/register', '/signup', '/']
    const isPublicPage = publicPaths.some(path =>
      pathname === path || (path === '/' && pathname === '/')
    )

    if (isPublicPage) {
      
      return
    }

    // Only fetch profile and preferences once on mount if authenticated
    if (isAuthenticated && !hasInitialized.current) {
      hasInitialized.current = true

      // ALWAYS fetch profile to validate tokens, even if user data exists
      // This ensures tokens are still valid after page refresh
      // If tokens are invalid, the API interceptor will handle refresh or redirect
      

      fetchProfile()
        .then(() => {
          // Only load preferences after successful profile fetch (token validation)
          // This ensures we have valid tokens before making preferences API calls
          

          return import('@/hooks/usePreferencesLoader')
            .then(({ loadPreferencesFromBackend }) => {
              
              return loadPreferencesFromBackend()
            })
            .then(() => {
              // After preferences are loaded, set a default model if user doesn't have one
              return import('@/store/modelStore').then(({ default: useModelStore }) => {
                return useModelStore.getState().setDefaultModelIfNeeded()
              })
            })
        })
        .catch((err) => {
          console.error('[useAuthInit] Failed to validate profile or load preferences:', err)
          // Don't throw - the interceptor will handle invalid tokens and redirect
        })
    }
  }, [isAuthenticated, fetchProfile, pathname])
}
