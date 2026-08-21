import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, renderHook, act } from '@testing-library/react'
import '@testing-library/jest-dom'
import { useVerificationGuard, VerificationGate } from '../VerificationGate'
import { VerificationGateModal } from '../VerificationGateModal'
import { useVerificationGateStore } from '@/store/verificationGateStore'

const mockToast = vi.fn()
const mockResend = vi.fn()

vi.mock('@/hooks/use-toast', () => ({
  toast: (...args: any[]) => mockToast(...args),
  useToast: () => ({ toast: mockToast }),
}))

vi.mock('@/api/endpoints', () => ({
  authApi: {
    resendVerification: (...args: any[]) => mockResend(...args),
  },
}))

interface AuthLikeUser {
  email: string
  is_verified: boolean
}
let authUser: AuthLikeUser | null = null

vi.mock('@/store/authStore', () => {
  const sel = (selector: (s: any) => any) =>
    selector({ user: authUser })
  return {
    useAuthStore: Object.assign(sel, {
      getState: () => ({ user: authUser }),
      setState: vi.fn(),
    }),
  }
})

function resetGateStore() {
  useVerificationGateStore.setState({ isOpen: false, reason: 'continue' })
}

beforeEach(() => {
  vi.clearAllMocks()
  resetGateStore()
  authUser = { email: 'alice@example.com', is_verified: true }
})

describe('useVerificationGuard / VerificationGate', () => {
  it('calls the wrapped fn through when the user is verified', () => {
    authUser = { email: 'alice@example.com', is_verified: true }
    const spy = vi.fn()
    render(
      <VerificationGate reason="send messages">
        <button onClick={spy}>Send</button>
      </VerificationGate>,
    )
    fireEvent.click(screen.getByRole('button', { name: /send/i }))
    expect(spy).toHaveBeenCalledTimes(1)
    expect(useVerificationGateStore.getState().isOpen).toBe(false)
  })

  it('opens the gate store and skips the wrapped fn when unverified', () => {
    authUser = { email: 'alice@example.com', is_verified: false }
    const spy = vi.fn()
    render(
      <VerificationGate reason="send messages">
        <button onClick={spy}>Send</button>
      </VerificationGate>,
    )
    fireEvent.click(screen.getByRole('button', { name: /send/i }))
    expect(spy).not.toHaveBeenCalled()
    expect(useVerificationGateStore.getState().isOpen).toBe(true)
  })

  it('shows the modal with the supplied reason after an unverified click', () => {
    authUser = { email: 'alice@example.com', is_verified: false }
    const spy = vi.fn()
    render(
      <>
        <VerificationGate reason="send messages">
          <button onClick={spy}>Send</button>
        </VerificationGate>
        <VerificationGateModal />
      </>,
    )
    fireEvent.click(screen.getByRole('button', { name: /send/i }))
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent(/verify your email first/i)
    expect(dialog).toHaveTextContent(/send messages/i)
  })

  it('closes the modal when "Not now" is pressed', () => {
    authUser = { email: 'alice@example.com', is_verified: false }
    useVerificationGateStore.setState({ isOpen: true, reason: 'send messages' })
    render(<VerificationGateModal />)
    fireEvent.click(screen.getByRole('button', { name: /not now/i }))
    expect(useVerificationGateStore.getState().isOpen).toBe(false)
  })

  it('returns a stable guard function across renders when verification state is unchanged', () => {
    authUser = { email: 'alice@example.com', is_verified: true }
    const { result, rerender } = renderHook(() => useVerificationGuard())
    const before = result.current.guard
    rerender()
    const after = result.current.guard
    expect(before).toBe(after)
  })

  it('passes through the guard when no user is logged in', () => {
    authUser = null
    const spy = vi.fn()
    render(
      <VerificationGate>
        <button onClick={spy}>Click</button>
      </VerificationGate>,
    )
    fireEvent.click(screen.getByRole('button', { name: /click/i }))
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it('calls authApi.resendVerification with the user email when Resend is clicked', async () => {
    authUser = { email: 'alice@example.com', is_verified: false }
    mockResend.mockResolvedValueOnce({})
    useVerificationGateStore.setState({ isOpen: true, reason: 'send messages' })
    render(<VerificationGateModal />)
    fireEvent.click(screen.getByRole('button', { name: /resend verification/i }))
    await waitFor(() => expect(mockResend).toHaveBeenCalledWith('alice@example.com'))
  })

  it('allows the action again once verification flips back to true', () => {
    authUser = { email: 'alice@example.com', is_verified: false }
    const spy = vi.fn()
    const { rerender } = render(
      <VerificationGate>
        <button onClick={spy}>Run</button>
      </VerificationGate>,
    )
    fireEvent.click(screen.getByRole('button', { name: /run/i }))
    expect(spy).not.toHaveBeenCalled()

    authUser = { email: 'alice@example.com', is_verified: true }
    act(() => {
      useVerificationGateStore.setState({ isOpen: false, reason: 'continue' })
    })
    rerender(
      <VerificationGate>
        <button onClick={spy}>Run</button>
      </VerificationGate>,
    )
    fireEvent.click(screen.getByRole('button', { name: /run/i }))
    expect(spy).toHaveBeenCalledTimes(1)
  })
})
