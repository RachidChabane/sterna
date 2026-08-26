import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom'
import { LoginForm } from '../LoginForm'

const mockNavigate = vi.fn()
const mockToast = vi.fn()
const mockLogin = vi.fn()
const mockClearError = vi.fn()

vi.mock('@tanstack/react-router', () => ({
  Link: ({
    children,
    to,
    ...rest
  }: {
    children: React.ReactNode
    to: string
  } & React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
  useNavigate: () => mockNavigate,
}))

vi.mock('@/hooks/use-toast', () => ({
  toast: (...args: unknown[]) => mockToast(...args),
  useToast: () => ({ toast: mockToast }),
}))

let authState = {
  login: mockLogin,
  isLoading: false,
  error: null as string | null,
  clearError: mockClearError,
}

vi.mock('@/store/authStore', () => ({
  useAuthStore: Object.assign(
    () => authState,
    {
      setState: vi.fn(),
      getState: () => authState,
    },
  ),
}))

vi.mock('@/api/endpoints', () => ({
  authApi: {
    googleAuth: vi.fn(),
  },
}))

vi.mock('@/api/client', () => ({
  setTokens: vi.fn(),
}))

vi.mock('@/components/icons/GoogleIcon', () => ({
  GoogleIcon: ({ className }: { className?: string }) => (
    <svg data-testid="google-icon" className={className} />
  ),
}))

describe('LoginForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authState = {
      login: mockLogin,
      isLoading: false,
      error: null,
      clearError: mockClearError,
    }
  })

  it('renders email and password fields with labels', () => {
    render(<LoginForm />)
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument()
  })

  it('renders a "Sign in" submit button', () => {
    render(<LoginForm />)
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('renders Google and GitHub OAuth buttons', () => {
    render(<LoginForm />)
    expect(screen.getByRole('button', { name: /google/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /github/i })).toBeInTheDocument()
  })

  it('toasts a validation error when email + password are empty', async () => {
    render(<LoginForm />)
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({ variant: 'destructive' }),
      ),
    )
    expect(mockLogin).not.toHaveBeenCalled()
  })

  it('toasts a validation error for an email above 254 chars and does not call login', async () => {
    render(<LoginForm />)
    const longEmail = 'a'.repeat(260) + '@example.com'
    const emailInput = screen.getByLabelText(/email address/i) as HTMLInputElement
    const passwordInput = screen.getByLabelText(/^password$/i) as HTMLInputElement

    // fireEvent.change bypasses input maxLength so the validation path fires.
    fireEvent.change(emailInput, { target: { value: longEmail } })
    fireEvent.change(passwordInput, { target: { value: 'password123' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({ variant: 'destructive' }),
      ),
    )
    expect(mockLogin).not.toHaveBeenCalled()
  })

  it('calls login and navigates to /chats on a successful submit', async () => {
    mockLogin.mockResolvedValueOnce(undefined)
    render(<LoginForm />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/email address/i), 'user@example.com')
    await user.type(screen.getByLabelText(/^password$/i), 'password123')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(mockLogin).toHaveBeenCalled())
    expect(mockNavigate).toHaveBeenCalledWith({ to: '/chats' })
  })

  it('shows a banner alert when the auth store has an error', () => {
    authState = { ...authState, error: 'Invalid credentials' }
    render(<LoginForm />)
    expect(screen.getByRole('alert')).toHaveTextContent(/invalid credentials/i)
  })

  it('toggles password visibility when the eye toggle is clicked', async () => {
    render(<LoginForm />)
    const passwordInput = screen.getByLabelText(/^password$/i) as HTMLInputElement
    expect(passwordInput.type).toBe('password')

    const toggle = screen.getByRole('button', { name: /show password/i })
    fireEvent.click(toggle)
    expect(passwordInput.type).toBe('text')
  })

  it('renders a Forgot password link pointing to /forgot-password', () => {
    render(<LoginForm />)
    const link = screen.getByRole('link', { name: /forgot/i }) as HTMLAnchorElement
    expect(link.getAttribute('href')).toBe('/forgot-password')
  })
})
