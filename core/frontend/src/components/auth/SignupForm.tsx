import { Link, useNavigate, useSearch } from '@tanstack/react-router'
import { hasErrorResponse } from '@/utils/errorMessages'
import { useState, useEffect } from 'react'
import { Turnstile } from '@marsidev/react-turnstile'
import { useAuthStore } from '@/store/authStore'
import { PasswordStrength, isPasswordStrong } from '@/components/auth/PasswordStrength'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Separator } from '@/components/ui/separator'
import {
  Eye,
  EyeOff,
  Mail,
  Lock,
  User as UserIcon,
  Github,
  Loader2,
  CheckCircle2,
} from 'lucide-react'
import { GoogleIcon } from '@/components/icons/GoogleIcon'
import { useToast } from '@/hooks/use-toast'
import { authApi } from '@/api/endpoints'
import { setTokens } from '@/api/client'
import { cn } from '@/lib/utils'

const MAX_NAME_LENGTH = 50
const MAX_EMAIL_LENGTH = 254
const MAX_PASSWORD_LENGTH = 128

function sanitizeInput(input: string): string {
  return input
    .replace(/<[^>]*>/g, '')
    .replace(/[<>'"&]/g, '')
    .trim()
}

function sanitizeEmail(input: string): string {
  return input
    .replace(/<[^>]*>/g, '')
    .replace(/[<>"]/g, '')
    .trim()
    .toLowerCase()
}

export interface SignupFormProps {
  onSuccess?: (email: string) => void
}

export function SignupForm({ onSuccess }: SignupFormProps) {
  const navigate = useNavigate()
  // ``useSearch`` from the /signup route exposes the optional ``return_to``
  // query (e.g. set by Pricing's unauthenticated-upgrade redirect). We
  // accept only same-origin paths in the success handler.
  const { return_to } = useSearch({ from: '/signup' })
  const { register, isLoading, error, clearError } = useAuthStore()
  const { toast } = useToast()

  const [formData, setFormData] = useState({
    firstName: '',
    lastName: '',
    email: '',
    password: '',
    confirmPassword: '',
  })
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [acceptTerms, setAcceptTerms] = useState(false)
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({})
  const [isGoogleInitialized, setIsGoogleInitialized] = useState(false)
  const [focusedField, setFocusedField] = useState<string | null>(null)
  // Turnstile widget — only rendered when the public site key is set.
  // Dev environments without keys skip the widget; the backend
  // bypasses verification when DEBUG=True or the secret is empty.
  const turnstileSiteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY as string | undefined
  const [turnstileToken, setTurnstileToken] = useState<string>('')

  useEffect(() => {
    clearError()
  }, [clearError])

  const validateForm = () => {
    const errors: Record<string, string> = {}

    const sanitizedFirstName = sanitizeInput(formData.firstName)
    const sanitizedLastName = sanitizeInput(formData.lastName)
    const sanitizedEmail = sanitizeEmail(formData.email)

    if (!sanitizedFirstName) {
      errors.firstName = 'First name is required'
    } else if (sanitizedFirstName.length < 2) {
      errors.firstName = 'First name must be at least 2 characters'
    } else if (sanitizedFirstName.length > MAX_NAME_LENGTH) {
      errors.firstName = `First name must be ${MAX_NAME_LENGTH} characters or less`
    }

    if (!sanitizedLastName) {
      errors.lastName = 'Last name is required'
    } else if (sanitizedLastName.length < 2) {
      errors.lastName = 'Last name must be at least 2 characters'
    } else if (sanitizedLastName.length > MAX_NAME_LENGTH) {
      errors.lastName = `Last name must be ${MAX_NAME_LENGTH} characters or less`
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!sanitizedEmail) {
      errors.email = 'Email is required'
    } else if (!emailRegex.test(sanitizedEmail)) {
      errors.email = 'Please enter a valid email address'
    } else if (sanitizedEmail.length > MAX_EMAIL_LENGTH) {
      errors.email = `Email must be ${MAX_EMAIL_LENGTH} characters or less`
    }

    if (!formData.password) {
      errors.password = 'Password is required'
    } else if (formData.password.length > MAX_PASSWORD_LENGTH) {
      errors.password = `Password must be ${MAX_PASSWORD_LENGTH} characters or less`
    } else if (!isPasswordStrong(formData.password)) {
      errors.password = 'Password does not meet the requirements'
    }

    if (!formData.confirmPassword) {
      errors.confirmPassword = 'Please confirm your password'
    } else if (formData.password !== formData.confirmPassword) {
      errors.confirmPassword = 'Passwords do not match'
    }

    if (!acceptTerms) {
      errors.terms = 'You must accept the terms and conditions'
    }

    if (turnstileSiteKey && !turnstileToken) {
      errors.turnstile = 'Please complete the security check'
    }

    setValidationErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    clearError()

    if (!validateForm()) {
      toast({
        title: 'Validation error',
        description: 'Please fix the errors in the form',
        variant: 'destructive',
      })
      return
    }

    const sanitizedEmail = sanitizeEmail(formData.email)
    const sanitizedFirstName = sanitizeInput(formData.firstName)
    const sanitizedLastName = sanitizeInput(formData.lastName)

    try {
      await register(
        sanitizedEmail,
        formData.password,
        sanitizedFirstName,
        sanitizedLastName,
        turnstileToken || undefined,
      )
      toast({
        title: 'Account created!',
        description: 'Check your inbox to verify your email.',
      })
      if (onSuccess) {
        onSuccess(sanitizedEmail)
      } else if (
        // Same-origin path only — never trust an absolute or
        // protocol-relative URL from a query string.
        return_to &&
        return_to.startsWith('/') &&
        !return_to.startsWith('//')
      ) {
        navigate({ href: return_to })
      } else {
        navigate({
          to: '/verify-email',
          search: { pending: 1 as const, email: sanitizedEmail, token: undefined },
        })
      }
    } catch (err) {
      // Map field errors from backend response
      const data = hasErrorResponse(err) ? (err.response?.data as Record<string, unknown> | undefined) : undefined
      if (data && typeof data === 'object') {
        const next: Record<string, string> = {}
        if (Array.isArray(data.email)) next.email = data.email[0]
        if (Array.isArray(data.password)) next.password = data.password[0]
        if (Array.isArray(data.first_name)) next.firstName = data.first_name[0]
        if (Array.isArray(data.last_name)) next.lastName = data.last_name[0]
        if (Object.keys(next).length) {
          setValidationErrors({ ...validationErrors, ...next })
        }
      }
      const message =
        (typeof data?.detail === 'string' && data.detail) ||
        (Array.isArray(data?.email) && data.email[0]) ||
        (typeof data?.message === 'string' && data.message) ||
        'An error occurred while creating your account. Please try again.'
      toast({
        title: 'Sign up failed',
        description: message,
        variant: 'destructive',
      })
    }
  }

  useEffect(() => {
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID
    if (!clientId) return

    const tryInitialize = () => {
      if (window.google?.accounts?.id) {
        try {
          window.google.accounts.id.initialize({
            client_id: clientId,
            callback: handleGoogleCallback,
          })
          setIsGoogleInitialized(true)
          return true
        } catch (err) {
          console.error('Google Sign-In initialization failed:', err)
          return false
        }
      }
      return false
    }

    if (tryInitialize()) return

    let attempts = 0
    const maxAttempts = 50
    const interval = setInterval(() => {
      attempts++
      if (tryInitialize() || attempts >= maxAttempts) {
        clearInterval(interval)
      }
    }, 100)

    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search)
    const errParam = urlParams.get('error')
    const message = urlParams.get('message')

    if (errParam && message) {
      toast({
        title: 'Authentication failed',
        description: message,
        variant: 'destructive',
      })
      window.history.replaceState({}, document.title, '/signup')
    }
  }, [toast])

  const handleGoogleCallback = async (response: { credential?: string }) => {
    if (!response.credential) {
      toast({
        title: 'Authentication failed',
        description: 'No credential received from Google',
        variant: 'destructive',
      })
      return
    }

    try {
      const apiResponse = await authApi.googleAuth(response.credential)
      const data = apiResponse.data

      const accessToken = data.access || data.access_token
      const refreshToken = data.refresh || data.refresh_token
      if (!accessToken || !refreshToken) {
        throw new Error('Missing access or refresh token in response')
      }
      setTokens(accessToken, refreshToken)
      useAuthStore.setState({
        user: data.user,
        isAuthenticated: true,
      })

      toast({
        title: data.created ? 'Account created!' : 'Welcome back!',
        description: data.created
          ? 'Your account has been created successfully with Google.'
          : 'Successfully signed in with Google.',
      })

      navigate({ to: '/chats' })
    } catch (err) {
      console.error('Google auth error:', err)
      toast({
        title: 'Authentication failed',
        description: 'Could not authenticate with Google. Please try again.',
        variant: 'destructive',
      })
    }
  }

  const handleGoogleLogin = () => {
    if (isGoogleInitialized && window.google) {
      window.google.accounts.id.prompt()
    } else {
      toast({
        title: 'Google Sign-In not available',
        description: 'Please configure Google OAuth credentials or use email/password signup.',
        variant: 'destructive',
      })
    }
  }

  const handleGitHubSignup = async () => {
    const clientId = import.meta.env.VITE_GITHUB_CLIENT_ID
    if (!clientId) {
      toast({
        title: 'GitHub signup not configured',
        description: 'Please configure GitHub OAuth credentials.',
        variant: 'destructive',
      })
      return
    }

    // Mint the OAuth state nonce server-side (task 19). The backend
    // stores it in Redis with a 5-minute TTL and consumes it on the
    // callback — defends against CSRF and stale-callback replay.
    let state: string
    try {
      const { data } = await authApi.requestOAuthState()
      state = data.state
    } catch {
      toast({
        title: 'Could not start sign-in',
        description: 'Please try again in a moment.',
        variant: 'destructive',
      })
      return
    }

    sessionStorage.setItem('github_oauth_state', state)
    sessionStorage.setItem('github_auth_return_url', '/')

    const redirectUri = `${window.location.origin}/oauth/callback`
    const scope = 'user:email'
    const githubAuthUrl = `https://github.com/login/oauth/authorize?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=${encodeURIComponent(scope)}&state=${state}`

    window.location.href = githubAuthUrl
  }

  const handleInputChange =
    (field: keyof typeof formData) => (e: React.ChangeEvent<HTMLInputElement>) => {
      setFormData({ ...formData, [field]: e.target.value })
      if (validationErrors[field]) {
        setValidationErrors({ ...validationErrors, [field]: '' })
      }
    }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3">
        <Button
          type="button"
          variant="outline"
          onClick={handleGoogleLogin}
          disabled={!isGoogleInitialized}
          className="h-11 gap-2.5 font-medium"
        >
          <GoogleIcon className="h-5 w-5" />
          <span>Google</span>
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={handleGitHubSignup}
          className="h-11 gap-2.5 font-medium"
        >
          <Github className="h-5 w-5" />
          <span>GitHub</span>
        </Button>
      </div>

      <div className="relative">
        <div className="absolute inset-0 flex items-center">
          <Separator className="w-full border-border/60" />
        </div>
        <div className="relative flex justify-center">
          <span className="bg-background px-4 text-sm text-muted-foreground">
            or continue with email
          </span>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5" noValidate>
        {error && (
          <div
            role="alert"
            aria-live="polite"
            className="p-3.5 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm"
          >
            {error}
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <FormField
            id="firstName"
            label="First name"
            error={validationErrors.firstName}
            focused={focusedField === 'firstName'}
          >
            <div className="relative">
              <UserIcon className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              <Input
                id="firstName"
                type="text"
                placeholder="First name"
                value={formData.firstName}
                onChange={handleInputChange('firstName')}
                onFocus={() => setFocusedField('firstName')}
                onBlur={() => setFocusedField(null)}
                className={cn(
                  'h-11 pl-10 transition-all',
                  validationErrors.firstName &&
                    'border-destructive focus-visible:ring-destructive/30',
                )}
                autoComplete="given-name"
                autoFocus
                maxLength={MAX_NAME_LENGTH}
                aria-invalid={!!validationErrors.firstName}
              />
            </div>
          </FormField>

          <FormField
            id="lastName"
            label="Last name"
            error={validationErrors.lastName}
            focused={focusedField === 'lastName'}
          >
            <div className="relative">
              <UserIcon className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              <Input
                id="lastName"
                type="text"
                placeholder="Last name"
                value={formData.lastName}
                onChange={handleInputChange('lastName')}
                onFocus={() => setFocusedField('lastName')}
                onBlur={() => setFocusedField(null)}
                className={cn(
                  'h-11 pl-10 transition-all',
                  validationErrors.lastName &&
                    'border-destructive focus-visible:ring-destructive/30',
                )}
                autoComplete="family-name"
                maxLength={MAX_NAME_LENGTH}
                aria-invalid={!!validationErrors.lastName}
              />
            </div>
          </FormField>
        </div>

        <FormField
          id="email"
          label="Email address"
          error={validationErrors.email}
          focused={focusedField === 'email'}
        >
          <div className="relative">
            <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              id="email"
              type="email"
              placeholder="name@company.com"
              value={formData.email}
              onChange={handleInputChange('email')}
              onFocus={() => setFocusedField('email')}
              onBlur={() => setFocusedField(null)}
              className={cn(
                'h-11 pl-10 transition-all',
                validationErrors.email &&
                  'border-destructive focus-visible:ring-destructive/30',
              )}
              autoComplete="email"
              maxLength={MAX_EMAIL_LENGTH}
              aria-invalid={!!validationErrors.email}
            />
          </div>
        </FormField>

        <FormField
          id="password"
          label="Password"
          error={validationErrors.password}
          focused={focusedField === 'password'}
        >
          <div className="relative">
            <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              id="password"
              type={showPassword ? 'text' : 'password'}
              placeholder="Create a strong password"
              value={formData.password}
              onChange={handleInputChange('password')}
              onFocus={() => setFocusedField('password')}
              onBlur={() => setFocusedField(null)}
              className={cn(
                'h-11 pl-10 pr-10 transition-all',
                validationErrors.password &&
                  'border-destructive focus-visible:ring-destructive/30',
              )}
              autoComplete="new-password"
              maxLength={MAX_PASSWORD_LENGTH}
              aria-invalid={!!validationErrors.password}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          <PasswordStrength password={formData.password} />
        </FormField>

        <FormField
          id="confirmPassword"
          label="Confirm password"
          error={validationErrors.confirmPassword}
          focused={focusedField === 'confirmPassword'}
        >
          <div className="relative">
            <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <Input
              id="confirmPassword"
              type={showConfirmPassword ? 'text' : 'password'}
              placeholder="Re-enter your password"
              value={formData.confirmPassword}
              onChange={handleInputChange('confirmPassword')}
              onFocus={() => setFocusedField('confirmPassword')}
              onBlur={() => setFocusedField(null)}
              className={cn(
                'h-11 pl-10 pr-10 transition-all',
                validationErrors.confirmPassword &&
                  'border-destructive focus-visible:ring-destructive/30',
              )}
              autoComplete="new-password"
              maxLength={MAX_PASSWORD_LENGTH}
              aria-invalid={!!validationErrors.confirmPassword}
            />
            <button
              type="button"
              onClick={() => setShowConfirmPassword(!showConfirmPassword)}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
            >
              {showConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
            {formData.confirmPassword &&
              formData.password === formData.confirmPassword && (
                <CheckCircle2 className="absolute right-10 top-1/2 -translate-y-1/2 h-4 w-4 text-accent-brand" />
              )}
          </div>
        </FormField>

        <div className="space-y-2">
          <div className="flex items-start gap-3">
            <Checkbox
              id="terms"
              checked={acceptTerms}
              onCheckedChange={(checked) => {
                setAcceptTerms(checked as boolean)
                if (validationErrors.terms) {
                  setValidationErrors({ ...validationErrors, terms: '' })
                }
              }}
              className="mt-0.5"
            />
            <Label
              htmlFor="terms"
              className="text-sm text-muted-foreground cursor-pointer leading-relaxed"
            >
              I agree to the{' '}
              <a
                href="/legal/terms"
                className="text-accent-brand hover:text-accent-brand/80 underline-offset-4 hover:underline"
              >
                Terms of Service
              </a>{' '}
              and{' '}
              <a
                href="/legal/privacy"
                className="text-accent-brand hover:text-accent-brand/80 underline-offset-4 hover:underline"
              >
                Privacy Policy
              </a>
            </Label>
          </div>
          {validationErrors.terms && (
            <p className="text-xs text-destructive pl-7">{validationErrors.terms}</p>
          )}
        </div>

        {turnstileSiteKey && (
          <div className="flex flex-col items-center gap-2">
            <Turnstile
              siteKey={turnstileSiteKey}
              onSuccess={(token) => {
                setTurnstileToken(token)
                if (validationErrors.turnstile) {
                  setValidationErrors({ ...validationErrors, turnstile: '' })
                }
              }}
              onExpire={() => setTurnstileToken('')}
              onError={() => setTurnstileToken('')}
              options={{ theme: 'auto', size: 'normal' }}
            />
            {validationErrors.turnstile && (
              <p className="text-xs text-destructive">{validationErrors.turnstile}</p>
            )}
          </div>
        )}

        <Button
          type="submit"
          className="w-full h-11 btn-premium text-white font-medium"
          disabled={isLoading}
        >
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Creating account...
            </>
          ) : (
            'Create account'
          )}
        </Button>
      </form>

      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{' '}
        <Link
          to="/login"
          className="font-medium text-accent-brand hover:text-accent-brand/80 transition-colors"
        >
          Sign in
        </Link>
      </p>
    </div>
  )
}

function FormField({
  id,
  label,
  error,
  focused,
  children,
}: {
  id: string
  label: string
  error?: string
  focused?: boolean
  children: React.ReactNode
}) {
  return (
    <div className="space-y-2">
      <Label
        htmlFor={id}
        className={cn(
          'text-sm font-medium transition-colors',
          focused && 'text-accent-brand',
        )}
      >
        {label}
      </Label>
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}
