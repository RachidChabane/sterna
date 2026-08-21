import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

// silence the sonner dynamic import triggered by 402 handling in some tests
vi.mock('sonner', () => ({ toast: vi.fn() }))

describe('api/client — token management', () => {
  beforeEach(() => {
    vi.resetModules()
    localStorage.clear()
    window.history.pushState({}, '', '/chats')
  })

  it('setTokens persists both tokens to localStorage and getAccessToken/getRefreshToken read them back', async () => {
    const { setTokens, getAccessToken, getRefreshToken } = await import('@/api/client')

    setTokens('access-123', 'refresh-456')

    expect(getAccessToken()).toBe('access-123')
    expect(getRefreshToken()).toBe('refresh-456')
    expect(localStorage.getItem('access_token')).toBe('access-123')
    expect(localStorage.getItem('refresh_token')).toBe('refresh-456')
  })

  it('clearTokens removes both tokens', async () => {
    const { setTokens, clearTokens, getAccessToken, getRefreshToken } = await import('@/api/client')
    setTokens('a', 'r')

    clearTokens()

    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('the request interceptor attaches the Bearer token set via setTokens()', async () => {
    const { default: apiClient, setTokens } = await import('@/api/client')
    setTokens('token-abc', 'refresh-abc')

    const config = await apiClient.interceptors.request.handlers[0].fulfilled({
      headers: {},
    } as any)

    expect(config.headers.Authorization).toBe('Bearer token-abc')
  })

  it('the request interceptor omits Authorization when no token is set', async () => {
    const { default: apiClient } = await import('@/api/client')

    const config = await apiClient.interceptors.request.handlers[0].fulfilled({
      headers: {},
    } as any)

    expect(config.headers.Authorization).toBeUndefined()
  })

  it('the request interceptor adds X-Project-ID from localStorage on a per-request basis', async () => {
    const { default: apiClient } = await import('@/api/client')
    localStorage.setItem('current_project_id', 'proj-1')

    const config = await apiClient.interceptors.request.handlers[0].fulfilled({
      headers: {},
    } as any)

    expect(config.headers['X-Project-ID']).toBe('proj-1')
  })

  it('a token seeded into localStorage BEFORE module load is picked up at import time (module-scope initialization)', async () => {
    localStorage.setItem('access_token', 'preloaded-token')

    const { getAccessToken } = await import('@/api/client')

    expect(getAccessToken()).toBe('preloaded-token')
  })
})

describe('api/client — 401 handling', () => {
  beforeEach(() => {
    vi.resetModules()
    localStorage.clear()
    window.history.pushState({}, '', '/chats')
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('refreshes the access token via a bare axios.post call (bypassing the apiClient instance) and retries the original request', async () => {
    // Import axios from the SAME fresh module registry as client.ts (after
    // vi.resetModules()) — a statically-hoisted top-level `import axios` would
    // resolve to a different module instance than the one client.ts uses,
    // and spying on it would silently no-op (a real network call is issued instead).
    const { default: axios } = await import('axios')
    const { default: apiClient, setTokens, getAccessToken } = await import('@/api/client')
    setTokens('old-access', 'old-refresh')

    const refreshSpy = vi.spyOn(axios, 'post').mockResolvedValue({
      data: { access: 'new-access', refresh: 'new-refresh' },
    } as any)

    const rejectedHandler = apiClient.interceptors.response.handlers[0].rejected
    const originalRequest: any = { headers: {}, _retry: false }
    const error: any = {
      response: { status: 401 },
      config: originalRequest,
    }

    // The interceptor retries the original request through the real apiClient
    // instance afterwards, which has no server to talk to in jsdom and rejects
    // with a network error — that retry itself isn't under test here, only
    // that the refresh happened and the original request was rewritten first.
    await rejectedHandler(error).catch(() => {})

    expect(refreshSpy).toHaveBeenCalledWith('/api/auth/token/refresh/', { refresh_token: 'old-refresh' })
    expect(getAccessToken()).toBe('new-access')
    expect(originalRequest.headers.Authorization).toBe('Bearer new-access')
  })

  it('falls back to the presented refresh token when the refresh response omits one (rotation not always present)', async () => {
    const { default: axios } = await import('axios')
    const { default: apiClient, setTokens, getRefreshToken } = await import('@/api/client')
    setTokens('old-access', 'stable-refresh')

    vi.spyOn(axios, 'post').mockResolvedValue({ data: { access: 'new-access' } } as any)

    const rejectedHandler = apiClient.interceptors.response.handlers[0].rejected
    const originalRequest: any = { headers: {}, _retry: false }
    await rejectedHandler({ response: { status: 401 }, config: originalRequest }).catch(() => {})

    expect(getRefreshToken()).toBe('stable-refresh')
  })

  it('opens the session-expired modal when refresh fails and we are outside the login grace period', async () => {
    vi.useFakeTimers()
    const { default: axios } = await import('axios')
    const { default: apiClient, setTokens } = await import('@/api/client')
    const { useAuthModalStore } = await import('@/store/authModalStore')
    setTokens('old-access', 'old-refresh')

    vi.spyOn(axios, 'post').mockRejectedValue(new Error('refresh failed'))
    const openModalSpy = vi.spyOn(useAuthModalStore.getState(), 'openModal')

    // setTokens() stamps a login timestamp; move well past the 5s login
    // grace period so the interceptor takes the "show session expired
    // modal" branch instead of the "just logged in" redirect branch.
    await vi.advanceTimersByTimeAsync(6000)

    const rejectedHandler = apiClient.interceptors.response.handlers[0].rejected
    const originalRequest: any = { headers: {}, _retry: false }

    await rejectedHandler({ response: { status: 401 }, config: originalRequest }).catch(() => {})
    await vi.advanceTimersByTimeAsync(200)

    expect(openModalSpy).toHaveBeenCalled()
  })

  it('does not attempt a second refresh when the request has already been retried (_retry flag)', async () => {
    const { default: axios } = await import('axios')
    const { default: apiClient, setTokens } = await import('@/api/client')
    setTokens('old-access', 'old-refresh')
    const refreshSpy = vi.spyOn(axios, 'post')

    const rejectedHandler = apiClient.interceptors.response.handlers[0].rejected
    const originalRequest: any = { headers: {}, _retry: true }

    await rejectedHandler({ response: { status: 401 }, config: originalRequest }).catch(() => {})

    expect(refreshSpy).not.toHaveBeenCalled()
  })

  it('skips the refresh call entirely and opens the session-expired modal when there is no refresh token to try', async () => {
    const { default: axios } = await import('axios')
    const { default: apiClient, getAccessToken, getRefreshToken } = await import('@/api/client')
    const { useAuthModalStore } = await import('@/store/authModalStore')
    // No setTokens() call — a fresh module has no access/refresh token and
    // no recent login timestamp, so this exercises a 401 with nothing to
    // refresh and outside the login grace period (the common "session went
    // stale in a background tab" case, as opposed to the already-covered
    // "refresh call itself failed" case). handleUnauthorized() synchronously
    // clears access/refresh tokens *and* resets authStore's `user` to null
    // (which the persist middleware immediately writes through to the
    // 'auth-storage' key) before sessionDetection ever runs — so seeding
    // auth-storage here wouldn't survive to be read. `current_project_id`
    // is untouched by that path, so it's what actually lets
    // sessionDetection recognize a previous session and pick the
    // 'session-expired' variant rather than 'sign-up-prompt'.
    localStorage.setItem('current_project_id', 'proj-1')
    const refreshSpy = vi.spyOn(axios, 'post')
    const openModalSpy = vi.spyOn(useAuthModalStore.getState(), 'openModal')

    const rejectedHandler = apiClient.interceptors.response.handlers[0].rejected
    const originalRequest: any = { headers: {}, _retry: false }

    await rejectedHandler({ response: { status: 401 }, config: originalRequest }).catch(() => {})
    await new Promise((r) => setTimeout(r, 150)) // handleUnauthorized's setTimeout(..., 100)

    expect(refreshSpy).not.toHaveBeenCalled()
    expect(openModalSpy).toHaveBeenCalledWith('session-expired', expect.any(String))
    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
  })

  it('clears tokens and skips the session-expired modal when refresh fails within the just-logged-in grace period', async () => {
    const { default: axios } = await import('axios')
    const { default: apiClient, setTokens, getAccessToken, getRefreshToken } = await import('@/api/client')
    const { useAuthModalStore } = await import('@/store/authModalStore')
    setTokens('old-access', 'old-refresh')

    vi.spyOn(axios, 'post').mockRejectedValue(new Error('refresh failed'))
    const openModalSpy = vi.spyOn(useAuthModalStore.getState(), 'openModal')

    // No time advance here (unlike the "outside grace period" test above) —
    // this 401 arrives right after setTokens(), inside the 5s grace period,
    // so a failed refresh should redirect to /login instead of showing the
    // session-expired modal.
    const rejectedHandler = apiClient.interceptors.response.handlers[0].rejected
    const originalRequest: any = { headers: {}, _retry: false }

    await rejectedHandler({ response: { status: 401 }, config: originalRequest }).catch(() => {})
    // jsdom doesn't implement real navigation, so `window.location.href`
    // assignment can't be asserted on directly here — wait past
    // handleUnauthorized's setTimeout(..., 100) instead, so a regression
    // that fell through to the modal branch would be caught by openModal
    // actually firing, rather than this passing vacuously on a not-yet.
    await new Promise((r) => setTimeout(r, 150))

    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
    expect(openModalSpy).not.toHaveBeenCalled()
  })
})
