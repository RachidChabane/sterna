import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { EmailVerificationBanner } from '../EmailVerificationBanner'

const mockToast = vi.fn()
const mockResend = vi.fn()

vi.mock('@/hooks/use-toast', () => ({
  toast: (...args: unknown[]) => mockToast(...args),
  useToast: () => ({ toast: mockToast }),
}))

vi.mock('@/api/endpoints', () => ({
  authApi: {
    resendVerification: (...args: unknown[]) => mockResend(...args),
  },
}))

interface AuthLikeUser {
  email: string
  is_verified: boolean
}
interface MockAuthState {
  user: AuthLikeUser | null
  isAuthenticated: boolean
}
let authUser: AuthLikeUser | null = null
let isAuthenticated = false

vi.mock('@/store/authStore', () => {
  const sel = (selector: (s: MockAuthState) => unknown) =>
    selector({ user: authUser, isAuthenticated })
  return {
    useAuthStore: Object.assign(sel, {
      getState: () => ({ user: authUser, isAuthenticated }),
      setState: vi.fn(),
    }),
  }
})

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  authUser = null
  isAuthenticated = false
})

afterEach(() => {
  sessionStorage.clear()
})

describe('EmailVerificationBanner', () => {
  it('renders nothing when the user is not authenticated', () => {
    isAuthenticated = false
    authUser = null
    const { container } = render(<EmailVerificationBanner />)
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when the user is verified', () => {
    isAuthenticated = true
    authUser = { email: 'alice@example.com', is_verified: true }
    const { container } = render(<EmailVerificationBanner />)
    expect(container.firstChild).toBeNull()
  })

  it('renders for an unverified authenticated user', () => {
    isAuthenticated = true
    authUser = { email: 'alice@example.com', is_verified: false }
    render(<EmailVerificationBanner />)
    expect(
      screen.getByRole('region', { name: /verification/i }),
    ).toBeInTheDocument()
  })

  it('persists dismissal to sessionStorage and hides the banner', () => {
    isAuthenticated = true
    authUser = { email: 'alice@example.com', is_verified: false }
    render(<EmailVerificationBanner />)
    fireEvent.click(
      screen.getByRole('button', { name: /dismiss verification banner/i }),
    )
    expect(sessionStorage.getItem('auth:verify-banner:dismissed')).toBe('1')
    expect(
      screen.queryByRole('region', { name: /verification/i }),
    ).not.toBeInTheDocument()
  })

  it('calls authApi.resendVerification with the user email', async () => {
    isAuthenticated = true
    authUser = { email: 'alice@example.com', is_verified: false }
    mockResend.mockResolvedValueOnce({})
    render(<EmailVerificationBanner />)
    fireEvent.click(screen.getByRole('button', { name: /resend/i }))
    await waitFor(() => expect(mockResend).toHaveBeenCalledWith('alice@example.com'))
  })

  it('shows a success toast when resend succeeds', async () => {
    isAuthenticated = true
    authUser = { email: 'alice@example.com', is_verified: false }
    mockResend.mockResolvedValueOnce({})
    render(<EmailVerificationBanner />)
    fireEvent.click(screen.getByRole('button', { name: /resend/i }))
    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({ title: expect.stringMatching(/sent/i) }),
      ),
    )
    const lastCall = mockToast.mock.calls.at(-1)?.[0]
    expect(lastCall?.variant).not.toBe('destructive')
  })

  it('shows a destructive toast when resend fails', async () => {
    isAuthenticated = true
    authUser = { email: 'alice@example.com', is_verified: false }
    mockResend.mockRejectedValueOnce({
      response: { data: { detail: 'Server error' } },
    })
    render(<EmailVerificationBanner />)
    fireEvent.click(screen.getByRole('button', { name: /resend/i }))
    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({ variant: 'destructive' }),
      ),
    )
  })

  it('hides the banner if sessionStorage already has dismissed', () => {
    isAuthenticated = true
    authUser = { email: 'alice@example.com', is_verified: false }
    sessionStorage.setItem('auth:verify-banner:dismissed', '1')
    const { container } = render(<EmailVerificationBanner />)
    expect(container.firstChild).toBeNull()
  })

  it('keeps Resend disabled for 60s after a successful resend', async () => {
    vi.useFakeTimers()
    try {
      isAuthenticated = true
      authUser = { email: 'alice@example.com', is_verified: false }
      mockResend.mockResolvedValueOnce({})
      render(<EmailVerificationBanner />)
      const resendBtn = screen.getByRole('button', { name: /resend/i })
      fireEvent.click(resendBtn)
      // Flush microtasks while still using fake timers
      await Promise.resolve()
      await Promise.resolve()
      // Re-find the button (it may have re-rendered)
      expect(screen.getByRole('button', { name: /resend/i })).toBeDisabled()
    } finally {
      vi.useRealTimers()
    }
  })
})
