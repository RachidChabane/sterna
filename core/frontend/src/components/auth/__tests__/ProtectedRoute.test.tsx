import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom'
import { ProtectedRoute } from '../ProtectedRoute'

let authState = { isAuthenticated: false, isLoading: false }
let modalState = { isRedirecting: false }
const openModalSpy = vi.fn()

vi.mock('@/store/authStore', () => ({
  useAuthStore: () => authState,
}))

vi.mock('@/store/authModalStore', () => ({
  useAuthModalStore: () => ({ ...modalState, openModal: openModalSpy }),
}))

vi.mock('@/lib/sessionDetection', () => ({
  getAuthModalVariant: () => 'session-expired',
}))

// TanStack Router's `location.search` is a *parsed*, null-prototype object
// (see @tanstack/router-core's qss decoder) — it has no toString/valueOf.
// `location.href` is the pre-stringified pathname + search + hash. Route
// location returned here mirrors that shape so the test fails the same way
// the real crash did if the component regresses to `pathname + search`.
function nullProtoSearch(entries: Record<string, unknown> = {}) {
  return Object.assign(Object.create(null), entries)
}

let mockLocation: { pathname: string; search: unknown; href: string }

vi.mock('@tanstack/react-router', () => ({
  useRouterState: () => ({ location: mockLocation }),
}))

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState = { isAuthenticated: false, isLoading: false }
    modalState = { isRedirecting: false }
    mockLocation = { pathname: '/chats', search: nullProtoSearch(), href: '/chats' }
  })

  it('does not crash and opens the session-expired modal with a stringified returnUrl when the router search object has a null prototype', () => {
    expect(() => render(<ProtectedRoute><div>secret</div></ProtectedRoute>)).not.toThrow()

    expect(openModalSpy).toHaveBeenCalledWith('session-expired', '/chats')
  })

  it('builds the returnUrl from location.href (not pathname + search) even when search has entries', () => {
    mockLocation = {
      pathname: '/chats',
      search: nullProtoSearch({ new: 'true' }),
      href: '/chats?new=true',
    }

    render(<ProtectedRoute><div>secret</div></ProtectedRoute>)

    expect(openModalSpy).toHaveBeenCalledWith('session-expired', '/chats?new=true')
  })

  it('does not open the modal while still redirecting', () => {
    modalState = { isRedirecting: true }

    render(<ProtectedRoute><div>secret</div></ProtectedRoute>)

    expect(openModalSpy).not.toHaveBeenCalled()
  })

  it('shows a loading state and skips the modal while auth is still resolving', () => {
    authState = { isAuthenticated: false, isLoading: true }

    render(<ProtectedRoute><div>secret</div></ProtectedRoute>)

    expect(openModalSpy).not.toHaveBeenCalled()
    expect(screen.queryByText('secret')).not.toBeInTheDocument()
  })

  it('renders children once authenticated', () => {
    authState = { isAuthenticated: true, isLoading: false }

    render(<ProtectedRoute><div>secret</div></ProtectedRoute>)

    expect(screen.getByText('secret')).toBeInTheDocument()
    expect(openModalSpy).not.toHaveBeenCalled()
  })
})
