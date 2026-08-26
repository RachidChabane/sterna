import { useState, useEffect } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useAuthModalStore } from '@/store/authModalStore'
import { useAuthStore } from '@/store/authStore'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { SternaLogo } from '@/components/icons/SternaLogo'
import { GoogleIcon } from '@/components/icons/GoogleIcon'
import { Mail, Lock, Eye, EyeOff, Loader2, Github, AlertCircle } from 'lucide-react'
import { useToast } from '@/hooks/use-toast'
import { authApi } from '@/api/endpoints'
import { setTokens } from '@/api/client'
import { getApiErrorMessage } from '@/utils/errorMessages'

/**
 * Authentication modal that appears instead of redirecting to login page.
 * Shows contextual messaging based on whether user had a previous session.
 */
export function AuthModal() {
  const { isOpen, variant, returnUrl, closeModal, setRedirecting } = useAuthModalStore()
  const { login, isLoading, error, clearError } = useAuthStore()
  const { toast } = useToast()
  const navigate = useNavigate()

  // Form state
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [isGoogleInitialized, setIsGoogleInitialized] = useState(false)

  // Reset form when modal opens/closes
  useEffect(() => {
    if (!isOpen) {
      setEmail('')
      setPassword('')
      setShowPassword(false)
      clearError()
    }
  }, [isOpen, clearError])

  // Initialize Google Sign-In
  useEffect(() => {
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID
    if (!clientId || !isOpen) return

    const tryInitialize = () => {
      if (window.google?.accounts?.id) {
        try {
          window.google.accounts.id.initialize({
            client_id: clientId,
            callback: handleGoogleCallback,
          })
          setIsGoogleInitialized(true)
          return true
        } catch (error) {
          console.error('[AuthModal] Google Sign-In initialization failed:', error)
          return false
        }
      }
      return false
    }

    if (tryInitialize()) return

    // Poll for Google SDK
    let attempts = 0
    const maxAttempts = 20
    const pollInterval = setInterval(() => {
      attempts++
      if (tryInitialize() || attempts >= maxAttempts) {
        clearInterval(pollInterval)
      }
    }, 500)

    return () => clearInterval(pollInterval)
  }, [isOpen])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    clearError()

    try {
      await login(email, password)
      toast({
        title: 'Welcome back!',
        description: 'You have successfully signed in.',
      })

      // Set redirecting flag to prevent handleModalClose from redirecting
      setRedirecting(true)

      closeModal()

      // Navigate to return URL if provided
      if (returnUrl && returnUrl.startsWith('/')) {
        navigate({ to: returnUrl })
      }

      // Reset redirecting flag after a short delay
      setTimeout(() => {
        setRedirecting(false)
      }, 500)
    } catch (error) {
      toast({
        title: 'Login failed',
        description: 'Please check your credentials and try again.',
        variant: 'destructive',
      })
    }
  }

  const handleGoogleCallback = async (response: { credential?: string }) => {
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

      // Set redirecting flag to prevent handleModalClose from redirecting
      setRedirecting(true)

      closeModal()

      if (returnUrl && returnUrl.startsWith('/')) {
        navigate({ to: returnUrl })
      }

      // Reset redirecting flag after a short delay
      setTimeout(() => {
        setRedirecting(false)
      }, 500)
    } catch (error) {
      console.error('[AuthModal] Google auth error:', error)
      toast({
        title: 'Authentication failed',
        description: getApiErrorMessage(error, 'Could not authenticate with Google.'),
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

  const handleGitHubLogin = () => {
    const clientId = import.meta.env.VITE_GITHUB_CLIENT_ID
    if (!clientId) {
      toast({
        title: 'GitHub login not configured',
        description: 'Please configure GitHub OAuth credentials.',
        variant: 'destructive',
      })
      return
    }

    const state = Math.random().toString(36).substring(7)
    

    sessionStorage.setItem('github_oauth_state', state)
    sessionStorage.setItem('github_auth_return_url', returnUrl || '/voice-rooms')

    

    const redirectUri = `${window.location.origin}/oauth/callback`
    const scope = 'user:email'
    const githubAuthUrl = `https://github.com/login/oauth/authorize?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=${encodeURIComponent(scope)}&state=${state}`

    

    closeModal()
    window.location.href = githubAuthUrl
  }

  const handleGoToSignup = () => {
    closeModal()
    navigate({
      to: '/signup',
      // The /signup route's search schema (and SignupForm) use `return_to`,
      // not `from` — a `from` param would be dropped by validateSearch.
      search: returnUrl ? { return_to: returnUrl } : undefined
    })
  }

  const handleGoToLogin = () => {
    closeModal()
    navigate({
      to: '/login',
      search: returnUrl ? { from: returnUrl } : undefined
    })
  }

  const isSessionExpired = variant === 'session-expired'

  // Protected routes that require authentication
  const protectedRoutes = ['/chats', '/voice-rooms']

  /**
   * Handle modal close with redirection logic
   * If user closes modal without authenticating from a protected route,
   * redirect them to /models (unless already there)
   */
  const handleModalClose = (open: boolean) => {
    if (!open) {
      // Check if user is still not authenticated after closing
      const { isAuthenticated } = useAuthStore.getState()
      const { isRedirecting: currentlyRedirecting } = useAuthModalStore.getState()

      // Don't redirect if user just logged in successfully (isRedirecting = true)
      if (!isAuthenticated && !currentlyRedirecting) {
        const currentPath = window.location.pathname

        // Check if we're on a protected route
        const isProtectedRoute = protectedRoutes.some(route => currentPath.startsWith(route))

        // Redirect to /models if on protected route and not already there
        if (isProtectedRoute && !currentPath.startsWith('/models')) {
          

          // Set redirecting flag to prevent modal from reopening
          setRedirecting(true)

          // Close modal first
          closeModal()

          // Then navigate after a brief delay to ensure modal closes
          setTimeout(() => {
            navigate({ to: '/models' })

            // Reset redirecting flag after navigation completes
            setTimeout(() => {
              setRedirecting(false)
            }, 500)
          }, 100)
          return
        }
      }

      // Normal close without redirect
      closeModal()
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleModalClose}>
      <DialogContent className="sm:max-w-[450px] rounded-2xl">
        <DialogHeader>
          <div className="flex justify-center mb-4">
            <SternaLogo size={48} className="text-accent-brand" />
          </div>
          <DialogTitle className="text-center text-2xl">
            {isSessionExpired ? 'Session Expired' : 'Sign In Required'}
          </DialogTitle>
          <DialogDescription className="text-center">
            {isSessionExpired
              ? 'Your session has expired. Please sign in again to continue.'
              : 'Please sign in or create an account to continue.'}
          </DialogDescription>
        </DialogHeader>

        {/* Login Form for Session Expired */}
        {isSessionExpired ? (
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div
                role="alert"
                aria-live="polite"
                className="flex items-start gap-3 p-3.5 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm"
              >
                <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* Email Field */}
            <div className="space-y-2">
              <Label htmlFor="modal-email" className="text-sm font-medium">
                Email address
              </Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="modal-email"
                  type="email"
                  placeholder="name@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="pl-10"
                  autoComplete="email"
                  autoFocus
                  required
                />
              </div>
            </div>

            {/* Password Field */}
            <div className="space-y-2">
              <Label htmlFor="modal-password" className="text-sm font-medium">
                Password
              </Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="modal-password"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pl-10 pr-10"
                  autoComplete="current-password"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {/* Submit Button */}
            <Button
              type="submit"
              className="w-full btn-premium text-white h-11 font-medium"
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

            {/* Social Login */}
            <div className="mt-4">
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <Separator className="w-full" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-background px-2 text-muted-foreground">Or continue with</span>
                </div>
              </div>

              <div className="mt-4 flex gap-3 justify-center">
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={handleGoogleLogin}
                  className="w-10 h-10"
                  title="Continue with Google"
                >
                  <GoogleIcon className="h-5 w-5" />
                </Button>

                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={handleGitHubLogin}
                  className="w-10 h-10"
                  title="Continue with GitHub"
                >
                  <Github className="h-5 w-5" />
                </Button>
              </div>
            </div>

            {/* Link to signup */}
            <div className="text-center text-sm text-muted-foreground">
              Need a different account?{' '}
              <button
                type="button"
                onClick={handleGoToSignup}
                className="font-medium text-accent-brand hover:text-accent-brand/80"
              >
                Create new account
              </button>
            </div>
          </form>
        ) : (
          /* Sign Up Prompt for New Users */
          <div className="space-y-4">
            <div className="space-y-3">
              <Button
                onClick={handleGoToSignup}
                className="w-full btn-premium text-white h-11 font-medium"
              >
                Create Account
              </Button>

              <Button
                onClick={handleGoToLogin}
                variant="outline"
                className="w-full h-11 font-medium"
              >
                Sign In
              </Button>
            </div>

            {/* Social Login */}
            <div>
              <div className="relative mb-4">
                <div className="absolute inset-0 flex items-center">
                  <Separator className="w-full" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-background px-2 text-muted-foreground">Or continue with</span>
                </div>
              </div>

              <div className="flex gap-3 justify-center">
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={handleGoogleLogin}
                  className="w-10 h-10"
                  title="Continue with Google"
                >
                  <GoogleIcon className="h-5 w-5" />
                </Button>

                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={handleGitHubLogin}
                  className="w-10 h-10"
                  title="Continue with GitHub"
                >
                  <Github className="h-5 w-5" />
                </Button>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
