import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import '@testing-library/jest-dom'
import { SignupForm } from '../SignupForm'

const mockNavigate = vi.fn()
const mockToast = vi.fn()
const mockRegister = vi.fn()
const mockClearError = vi.fn()
const mockRequestOAuthState = vi.fn()

// The /signup route exposes an optional `return_to` search param (task-12,
// e990f0d). Tests mutate this to exercise the post-signup redirect logic.
let mockSearch: { return_to?: string } = {}

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
  useSearch: () => mockSearch,
}))

vi.mock('@/hooks/use-toast', () => ({
  toast: (...args: any[]) => mockToast(...args),
  useToast: () => ({ toast: mockToast }),
}))

let authState = {
  register: mockRegister,
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
    // Backend-issued OAuth state nonce (task-19, 1b8ec2a)
    requestOAuthState: (...args: any[]) => mockRequestOAuthState(...args),
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

// The real Turnstile widget renders a Cloudflare iframe; replace it with a
// stub that lets tests trigger the success callback deterministically.
vi.mock('@marsidev/react-turnstile', () => ({
  Turnstile: ({
    siteKey,
    onSuccess,
  }: {
    siteKey: string
    onSuccess?: (token: string) => void
  }) => (
    <div data-testid="turnstile-widget" data-sitekey={siteKey}>
      <button type="button" onClick={() => onSuccess?.('turnstile-test-token')}>
        Solve captcha
      </button>
    </div>
  ),
}))

async function fillRequiredFields(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/first name/i), 'Alice')
  await user.type(screen.getByLabelText(/last name/i), 'Doe')
  await user.type(screen.getByLabelText(/email address/i), 'alice@example.com')
  await user.type(screen.getByLabelText(/^password$/i), 'Abcd1234!')
  await user.type(screen.getByLabelText(/confirm password/i), 'Abcd1234!')
}

describe('SignupForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockSearch = {}
    authState = {
      register: mockRegister,
      isLoading: false,
      error: null,
      clearError: mockClearError,
    }
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('renders all five fields', () => {
    render(<SignupForm />)
    expect(screen.getByLabelText(/first name/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/last name/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument()
  })

  it('shows the password-strength meter when the user types', async () => {
    render(<SignupForm />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/^password$/i), 'a')
    expect(screen.getByText(/password strength/i)).toBeInTheDocument()
  })

  it('reports Strong strength for a fully-compliant password', async () => {
    render(<SignupForm />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/^password$/i), 'Abcd1234!')
    expect(await screen.findByText('Strong')).toBeInTheDocument()
  })

  it('reports a validation error when confirmation does not match', async () => {
    render(<SignupForm />)
    const user = userEvent.setup()
    await user.type(screen.getByLabelText(/first name/i), 'Alice')
    await user.type(screen.getByLabelText(/last name/i), 'Doe')
    await user.type(screen.getByLabelText(/email address/i), 'alice@example.com')
    await user.type(screen.getByLabelText(/^password$/i), 'Abcd1234!')
    await user.type(screen.getByLabelText(/confirm password/i), 'Different1!')
    const termsCheckbox = screen.getByLabelText(/terms of service/i)
    await user.click(termsCheckbox)
    await user.click(screen.getByRole('button', { name: /create account/i }))
    expect(await screen.findByText(/passwords do not match/i)).toBeInTheDocument()
    expect(mockRegister).not.toHaveBeenCalled()
  })

  it('shows a validation error when terms are not accepted', async () => {
    render(<SignupForm />)
    const user = userEvent.setup()
    await fillRequiredFields(user)
    await user.click(screen.getByRole('button', { name: /create account/i }))
    expect(await screen.findByText(/must accept the terms/i)).toBeInTheDocument()
    expect(mockRegister).not.toHaveBeenCalled()
  })

  it('renders Google and GitHub OAuth buttons', () => {
    render(<SignupForm />)
    expect(screen.getByRole('button', { name: /google/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /github/i })).toBeInTheDocument()
  })

  it('registers with sanitized values and navigates to /verify-email?pending=1 after successful submit', async () => {
    mockRegister.mockResolvedValueOnce(undefined)
    render(<SignupForm />)
    const user = userEvent.setup()
    await fillRequiredFields(user)
    await user.click(screen.getByLabelText(/terms of service/i))
    await user.click(screen.getByRole('button', { name: /create account/i }))
    await waitFor(() => expect(mockRegister).toHaveBeenCalled())
    // authStore.register(email, password, firstName, lastName, turnstileToken)
    // — the store composes `full_name` from the two name fields for the API.
    // No Turnstile site key is configured here, so the token is undefined.
    expect(mockRegister).toHaveBeenCalledWith(
      'alice@example.com',
      'Abcd1234!',
      'Alice',
      'Doe',
      undefined,
    )
    expect(mockNavigate).toHaveBeenCalledWith({
      to: '/verify-email',
      search: expect.objectContaining({ pending: 1, email: 'alice@example.com' }),
    })
  })

  it('redirects to a same-origin return_to path after successful signup', async () => {
    mockSearch = { return_to: '/pricing' }
    mockRegister.mockResolvedValueOnce(undefined)
    render(<SignupForm />)
    const user = userEvent.setup()
    await fillRequiredFields(user)
    await user.click(screen.getByLabelText(/terms of service/i))
    await user.click(screen.getByRole('button', { name: /create account/i }))
    await waitFor(() => expect(mockRegister).toHaveBeenCalled())
    expect(mockNavigate).toHaveBeenCalledWith({ to: '/pricing' })
  })

  it('ignores a protocol-relative return_to and falls back to /verify-email', async () => {
    mockSearch = { return_to: '//evil.example.com/phish' }
    mockRegister.mockResolvedValueOnce(undefined)
    render(<SignupForm />)
    const user = userEvent.setup()
    await fillRequiredFields(user)
    await user.click(screen.getByLabelText(/terms of service/i))
    await user.click(screen.getByRole('button', { name: /create account/i }))
    await waitFor(() => expect(mockRegister).toHaveBeenCalled())
    expect(mockNavigate).toHaveBeenCalledWith({
      to: '/verify-email',
      search: expect.objectContaining({ pending: 1, email: 'alice@example.com' }),
    })
  })

  it('requires the Turnstile token when a site key is configured and passes it to register', async () => {
    vi.stubEnv('VITE_TURNSTILE_SITE_KEY', 'test-site-key')
    mockRegister.mockResolvedValue(undefined)
    render(<SignupForm />)
    expect(screen.getByTestId('turnstile-widget')).toHaveAttribute(
      'data-sitekey',
      'test-site-key',
    )

    const user = userEvent.setup()
    await fillRequiredFields(user)
    await user.click(screen.getByLabelText(/terms of service/i))

    // Submit without solving the captcha: blocked by validation
    await user.click(screen.getByRole('button', { name: /create account/i }))
    expect(
      await screen.findByText(/complete the security check/i),
    ).toBeInTheDocument()
    expect(mockRegister).not.toHaveBeenCalled()

    // Solve the captcha, then submit again: token is forwarded to register
    await user.click(screen.getByRole('button', { name: /solve captcha/i }))
    await user.click(screen.getByRole('button', { name: /create account/i }))
    await waitFor(() =>
      expect(mockRegister).toHaveBeenCalledWith(
        'alice@example.com',
        'Abcd1234!',
        'Alice',
        'Doe',
        'turnstile-test-token',
      ),
    )
  })

  it('toasts and stores no OAuth state when the backend state request fails', async () => {
    vi.stubEnv('VITE_GITHUB_CLIENT_ID', 'test-github-client')
    mockRequestOAuthState.mockRejectedValueOnce(new Error('network down'))
    render(<SignupForm />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: /github/i }))
    await waitFor(() =>
      expect(mockToast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Could not start sign-in',
          variant: 'destructive',
        }),
      ),
    )
    expect(mockRequestOAuthState).toHaveBeenCalledTimes(1)
    expect(sessionStorage.getItem('github_oauth_state')).toBeNull()
  })

  it('surfaces backend email errors as an inline error', async () => {
    const error = {
      response: { data: { email: ['Email already exists'] } },
    }
    mockRegister.mockRejectedValueOnce(error)
    render(<SignupForm />)
    const user = userEvent.setup()
    await fillRequiredFields(user)
    await user.click(screen.getByLabelText(/terms of service/i))
    await user.click(screen.getByRole('button', { name: /create account/i }))
    expect(await screen.findByText(/email already exists/i)).toBeInTheDocument()
  })
})
