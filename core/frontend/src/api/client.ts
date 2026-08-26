import axios, { type AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/store/authStore'
import { useAuthModalStore } from '@/store/authModalStore'
import { getAuthModalVariant } from '@/lib/sessionDetection'

declare module 'axios' {
  export interface AxiosRequestConfig {
    /**
     * Opt out of the session-expired modal on an unrecoverable 401 for
     * this one request — for a background poll (e.g. a readiness check)
     * where interrupting the user is worse than the poll silently
     * failing. The request still rejects normally either way.
     */
    suppressUnauthorizedModal?: boolean
  }
}

/**
 * Orchestrator URL - routes through API gateway to sandbox service
 * Works in both dev (vite proxy) and prod (same origin)
 */
export const ORCHESTRATOR_URL = import.meta.env.VITE_ORCHESTRATOR_URL || '/api/v1/sandbox'

// Sandbox operations (code execution, workspace save/restore) can legitimately
// run far longer than a typical JSON request; the request body's own
// `timeout`/`sync_mode` fields are the operation-level limit. No HTTP-level
// timeout is imposed here, matching the unbounded `fetch()` calls this
// instance replaces.
const ORCHESTRATOR_TIMEOUT_MS = 0

/**
 * Per-call override for apiClient requests slower than its 30s default:
 * document text extraction, audio transcription, LLM-backed generation.
 * 30s is too tight for them, so callers pass
 * `{ timeout: LONG_RUNNING_TIMEOUT_MS }` explicitly. Matches
 * consigliereClient's own 3-minute default, set for the same class of
 * AI-generation request.
 */
export const LONG_RUNNING_TIMEOUT_MS = 180000

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

/**
 * Attach the shared auth/error interceptor pair to an axios instance.
 * Both `apiClient` (Django API, same-origin `/api`) and `orchestratorClient`
 * (sandbox service, possibly cross-origin) need identical bearer-token
 * injection, 401-triggered token refresh, and tiered-plan error handling —
 * defined once here so the two instances cannot drift.
 *
 * `X-Project-ID` is intentionally NOT part of that shared set: it's a
 * Django-API-only header the sandbox orchestrator never reads. Sending it
 * to the orchestrator would add a non-simple header to a request that can
 * be cross-origin (`VITE_ORCHESTRATOR_URL` pointed directly at the
 * orchestrator), forcing a CORS preflight the orchestrator's own
 * `allow_headers` list (core/sandbox/orchestrator/main.py) does not
 * include — so only `includeProjectHeader: true` (apiClient) adds it.
 */
function attachAuthInterceptors(
  instance: AxiosInstance,
  options: { includeProjectHeader: boolean }
): AxiosInstance {
  instance.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      if (accessToken) {
        config.headers.Authorization = `Bearer ${accessToken}`
      }

      if (options.includeProjectHeader) {
        const projectId = localStorage.getItem('current_project_id')
        if (projectId) {
          config.headers['X-Project-ID'] = projectId
        }
      }

      return config
    },
    (error) => {
      return Promise.reject(error)
    }
  )

  instance.interceptors.response.use(
    (response) => {
      return response
    },
    async (error: AxiosError) => {
      const originalRequest = error.config as InternalAxiosRequestConfig & {
        _retry?: boolean
        suppressUnauthorizedModal?: boolean
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
            return instance(originalRequest)
          } catch {
            // Refresh failed - fall through to show session expired modal
          }
        }

        // If we just logged in and immediately got a 401, redirect to login instead of showing modal
        // This handles cases where login succeeded on frontend but backend has issues
        if (isWithinLoginGracePeriod()) {

          clearTokens()
          window.location.href = '/login'
        } else if (!originalRequest.suppressUnauthorizedModal) {
          // Use centralized 401 handler to show session expired modal.
          // Opt out with `suppressUnauthorizedModal: true` for a background
          // poll where an expired session should fail silently rather than
          // interrupt the user (e.g. a readiness poll) — the caller's own
          // catch still runs either way.
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

  return instance
}

// Central client for the Django API (same-origin, JSON).
const apiClient = attachAuthInterceptors(
  axios.create({
    baseURL: '/api',
    timeout: 30000,
    headers: {
      'Content-Type': 'application/json',
    },
  }),
  { includeProjectHeader: true }
)

// Central client for the sandbox orchestrator service. Its base URL can be a
// distinct origin (VITE_ORCHESTRATOR_URL), so it cannot be expressed as a
// path under apiClient's `/api` baseURL — it gets its own instance sharing
// the same auth/error interceptors.
export const orchestratorClient = attachAuthInterceptors(
  axios.create({
    baseURL: ORCHESTRATOR_URL,
    timeout: ORCHESTRATOR_TIMEOUT_MS,
    headers: {
      'Content-Type': 'application/json',
    },
  }),
  { includeProjectHeader: false }
)

// Named export for compatibility
export const api = apiClient

export default apiClient
