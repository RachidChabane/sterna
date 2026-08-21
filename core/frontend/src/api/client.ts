import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/store/authStore'
import { useAuthModalStore } from '@/store/authModalStore'
import { getAuthModalVariant } from '@/lib/sessionDetection'

/**
 * Orchestrator URL - routes through API gateway to sandbox service
 * Works in both dev (vite proxy) and prod (same origin)
 */
export const ORCHESTRATOR_URL = import.meta.env.VITE_ORCHESTRATOR_URL || '/api/v1/sandbox'

// Track if we're already handling a 401 to prevent multiple modals
let isHandling401 = false

/**
 * Centralized 401 handler - shows session expired modal
 * Use this from any API client when a 401 cannot be recovered via token refresh
 */
export const handleUnauthorized = () => {
  // Prevent multiple simultaneous handlers
  if (isHandling401) return

  const currentPath = window.location.pathname
  const publicPaths = ['/login', '/signup', '/register', '/onboarding', '/']
  const isPublicPath = publicPaths.some(path =>
    currentPath === path || (path === '/' && currentPath === '/')
  )

  // Don't show modal on public pages
  if (isPublicPath) return

  isHandling401 = true
  clearTokens()

  // Update auth state to reflect logout
  useAuthStore.setState({
    user: null,
    isAuthenticated: false,
    isLoading: false
  })

  // Show session expired modal
  setTimeout(() => {
    isHandling401 = false
    const variant = getAuthModalVariant()
    const returnUrl = currentPath + window.location.search
    
    useAuthModalStore.getState().openModal(variant, returnUrl)
  }, 100)
}

// Create axios instance
const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Token management
let accessToken: string | null = localStorage.getItem('access_token')
let refreshToken: string | null = localStorage.getItem('refresh_token')
let lastLoginTimestamp: number = 0

// Grace period after login (in ms) - don't show session expired modal during this time
const LOGIN_GRACE_PERIOD = 5000

export const setTokens = (access: string, refresh: string) => {
  accessToken = access
  refreshToken = refresh
  lastLoginTimestamp = Date.now()
  localStorage.setItem('access_token', access)
  localStorage.setItem('refresh_token', refresh)
}

/**
 * Check if we're within the grace period after a recent login
 */
const isWithinLoginGracePeriod = () => {
  return Date.now() - lastLoginTimestamp < LOGIN_GRACE_PERIOD
}

export const clearTokens = () => {
  accessToken = null
  refreshToken = null
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

export const getAccessToken = () => accessToken
export const getRefreshToken = () => refreshToken

// Request interceptor
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Add auth token to request if available
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`
    }

    // Add project context if available
    const projectId = localStorage.getItem('current_project_id')
    if (projectId) {
      config.headers['X-Project-ID'] = projectId
    }

    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor
apiClient.interceptors.response.use(
  (response) => {
    return response
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean
    }

    // Handle 401 errors - try to refresh token
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      // If we have a refresh token, try to refresh
      if (refreshToken) {
        try {
          const response = await axios.post('/api/auth/token/refresh/', {
            refresh_token: refreshToken,
          })

          // Backend returns access_token, normalize the key
          const access = response.data.access || response.data.access_token
          // Backend rotates the refresh token on each use; fall back to the
          // presented token only if the response omits it
          const refresh = response.data.refresh || response.data.refresh_token || refreshToken
          setTokens(access, refresh)

          // Retry original request with new token
          originalRequest.headers.Authorization = `Bearer ${access}`
          return apiClient(originalRequest)
        } catch {
          // Refresh failed - fall through to show session expired modal
        }
      }

      // If we just logged in and immediately got a 401, redirect to login instead of showing modal
      // This handles cases where login succeeded on frontend but backend has issues
      if (isWithinLoginGracePeriod()) {
        
        clearTokens()
        window.location.href = '/login'
      } else {
        // Use centralized 401 handler to show session expired modal
        handleUnauthorized()
      }

      return Promise.reject(error)
    }

    // Handle other errors
    if (error.response?.status === 403) {
      console.error('Permission denied')
    }

    if (error.response?.status === 402) {
      // Tier enforcement: feature_not_available or quota_exceeded.
      // Body shape: { error, message, details: { feature, plan_slug,
      // upgrade_url, used?, limit?, reset_at? } }
      const body = error.response.data as
        | {
            error?: string
            message?: string
            details?: {
              feature?: string
              plan_slug?: string
              upgrade_url?: string
              used?: number
              limit?: number
              reset_at?: string
              resets_in_seconds?: number
            }
          }
        | undefined

      const goToPricing = {
        label: 'Upgrade',
        onClick: () => {
          window.location.href = body?.details?.upgrade_url ?? '/pricing'
        },
      }

      // Dynamic import to avoid bundler pulling sonner into hot paths
      // that don't need it.
      void import('sonner').then(({ toast }) => {
        if (body?.error === 'feature_not_available') {
          toast(body.message ?? 'Feature not in your plan', {
            description:
              'This feature is not available on your current plan.',
            action: goToPricing,
          })
        } else if (body?.error === 'quota_exceeded') {
          const resetAt = body.details?.reset_at
          toast(body.message ?? 'Quota exceeded', {
            description: resetAt
              ? `Resets at ${new Date(resetAt).toLocaleString()}`
              : undefined,
            action: goToPricing,
          })
        }
      })
    }

    if (error.response?.status === 500) {
      console.error('Server error')
    }

    return Promise.reject(error)
  }
)

// Named export for compatibility
export const api = apiClient

export default apiClient