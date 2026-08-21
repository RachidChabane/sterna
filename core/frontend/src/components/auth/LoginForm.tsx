import { Link, useNavigate } from '@tanstack/react-router'
import { useState, useEffect } from 'react'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Separator } from '@/components/ui/separator'
import { Eye, EyeOff, Mail, Lock, Github, Loader2 } from 'lucide-react'
import { GoogleIcon } from '@/components/icons/GoogleIcon'
import { useToast } from '@/hooks/use-toast'
import { authApi } from '@/api/endpoints'
import { setTokens } from '@/api/client'

const MAX_EMAIL_LENGTH = 254
const MAX_PASSWORD_LENGTH = 128

function sanitizeEmail(input: string): string {
  return input
    .replace(/<[^>]*>/g, '')
    .replace(/[<>"]/g, '')
    .trim()
    .toLowerCase()
}

export interface LoginFormProps {
  onSuccess?: () => void
}

export function LoginForm({ onSuccess }: LoginFormProps) {
  const navigate = useNavigate()
  const { login, isLoading, error, clearError } = useAuthStore()
  const { toast } = useToast()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [rememberMe, setRememberMe] = useState(false)
  const [isGoogleInitialized, setIsGoogleInitialized] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  const navigateAfterAuth = () => {
    if (onSuccess) {
      onSuccess()
      return
    }
    const searchParams = new URLSearchParams(window.location.search)
    const returnUrl = searchParams.get('from') || '/chats'
    if (typeof returnUrl === 'string' && returnUrl.startsWith('/')) {
      navigate({ to: returnUrl })
    } else {
      navigate({ to: '/chats' })
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    clearError()
    setFieldErrors({})

    const sanitizedEmail = sanitizeEmail(email)

    if (!sanitizedEmail || !password) {
      toast({
        title: 'Validation error',
        description: 'Please enter both email and password',
        variant: 'destructive',
      })
      return
    }

    if (sanitizedEmail.length > MAX_EMAIL_LENGTH) {
      toast({
        title: 'Validation error',
        description: `Email must be ${MAX_EMAIL_LENGTH} characters or less`,
        variant: 'destructive',
      })
      return
    }

    if (password.length > MAX_PASSWORD_LENGTH) {
      toast({
        title: 'Validation error',
        description: `Password must be ${MAX_PASSWORD_LENGTH} characters or less`,
        variant: 'destructive',
      })
      return
    }

    try {
      await login(sanitizedEmail, password)
      toast({
        title: 'Welcome back!',
        description: 'You have successfully signed in.',
      })
      navigateAfterAuth()
    } catch (err: any) {
      const data = err.response?.data
      if (data && typeof data === 'object') {
        const next: Record<string, string> = {}
        if (Array.isArray(data.email)) next.email = data.email[0]
        if (Array.isArray(data.password)) next.password = data.password[0]
        if (Object.keys(next).length) setFieldErrors(next)
      }
      const message =
        err.response?.data?.detail ||
        err.response?.data?.message ||
        'Please check your credentials and try again.'
      toast({
        title: 'Sign in failed',
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
    const maxAttempts = 20
    const pollInterval = setInterval(() => {
      attempts++
      if (tryInitialize() || attempts >= maxAttempts) {
        clearInterval(pollInterval)
      }
    }, 500)

    return () => clearInterval(pollInterval)
  }, [])

  const handleGoogleCallback = async (response: any) => {
    if (!response.credential) {
      toast({
        title: 'Google authentication failed',
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
        title: 'Welcome!',
        description: 'Successfully signed in with Google.',
      })
      navigateAfterAuth()
    } catch (err: any) {
      console.error('Google auth error:', err)
      toast({
        title: 'Authentication failed',
        description:
          err.response?.data?.error ||
          'Could not authenticate with Google. Please try again.',
        variant: 'destructive',
      })
    }
  }

  const handleGoogleLogin = () => {
    if (isGoogleInitialized && window.google) {
      window.google.accounts.id.prompt()
    } else {
      toast({
        title: 'Google Sign-In not ready',
        description: 'Please wait a moment and try again.',
        variant: 'destructive',
      })
    }
  }

  const handleGitHubLogin = async () => {
    const clientId = import.meta.env.VITE_GITHUB_CLIENT_ID
    if (!clientId) {
      toast({
        title: 'GitHub login not configured',
        description: 'Please configure GitHub OAuth credentials.',
        variant: 'destructive',
      })
      return
    }

    // Backend-issued OAuth state (task 19). Defends against CSRF and
    // stale-callback replay; the backend consumes the nonce on the
    // /auth/github/ POST.
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

    const searchParams = new URLSearchParams(window.location.search)
    const returnUrl = searchParams.get('from') || '/chats'
    sessionStorage.setItem('github_auth_return_url', returnUrl)

    const redirectUri = `${window.location.origin}/oauth/callback`
    const scope = 'user:email'
    const githubAuthUrl = `https://github.com/login/oauth/authorize?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=${encodeURIComponent(scope)}&state=${state}`

    window.location.href = githubAuthUrl
  }

  useEffect(() => {
    clearError()
  }, [clearError])

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
      window.history.replaceState({}, document.title, '/login')
    }
  }, [toast])

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3">
        <Button
          type="button"
          variant="outline"
          onClick={handleGoogleLogin}
          className="h-11 gap-2.5 font-medium"
        >
          <GoogleIcon className="h-5 w-5" />
          <span>Google</span>
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={handleGitHubLogin}
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
            or sign in with email
          </span>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {error && (
          <div
            role="alert"
            aria-live="polite"
            className="flex items-start gap-3 p-3.5 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm"
          >
            <span>{error}</span>
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="email" className="text-sm font-medium">
            Email address
          </Label>
          <div className="relative">
            <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              id="email"
              type="email"
              placeholder="name@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="h-11 pl-10"
              autoComplete="email"
              autoFocus
              required
              maxLength={MAX_EMAIL_LENGTH}
              aria-invalid={!!fieldErrors.email}
              aria-describedby={fieldErrors.email ? 'email-error' : undefined}
            />
          </div>
          {fieldErrors.email && (
            <p id="email-error" className="text-xs text-destructive">
              {fieldErrors.email}
            </p>
          )}
        </div>

        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <Label htmlFor="password" className="text-sm font-medium">
              Password
            </Label>
            <Link
              to="/forgot-password"
              className="text-sm text-accent-brand hover:text-accent-brand/80"
            >
              Forgot password?
            </Link>
          </div>
          <div className="relative">
            <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              id="password"
              type={showPassword ? 'text' : 'password'}
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="h-11 pl-10 pr-10"
              autoComplete="current-password"
              required
              maxLength={MAX_PASSWORD_LENGTH}
              aria-invalid={!!fieldErrors.password}
              aria-describedby={fieldErrors.password ? 'password-error' : undefined}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          {fieldErrors.password && (
            <p id="password-error" className="text-xs text-destructive">
              {fieldErrors.password}
            </p>
          )}
        </div>

        <div className="flex items-center space-x-2">
          <Checkbox
            id="remember"
            checked={rememberMe}
            onCheckedChange={(checked) => setRememberMe(checked as boolean)}
          />
          <Label htmlFor="remember" className="text-sm text-muted-foreground cursor-pointer">
            Remember me for 30 days
          </Label>
        </div>

        <Button
          type="submit"
          className="w-full h-11 btn-premium text-white font-medium"
          disabled={isLoading}
        >
          {isLoading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Signing in...
            </>
          ) : (
            'Sign in'
          )}
        </Button>
      </form>

      <p className="text-center text-sm text-muted-foreground">
        Don't have an account?{' '}
        <Link
          to="/signup"
          className="font-medium text-accent-brand hover:text-accent-brand/80"
        >
          Sign up for free
        </Link>
      </p>
    </div>
  )
}
