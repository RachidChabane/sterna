import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { hasErrorResponse } from '@/utils/errorMessages'
import { useState } from 'react'
import { AlertCircle, CheckCircle2, Eye, EyeOff, Lock, Loader2 } from 'lucide-react'
import { AuthShell } from '@/components/auth/AuthShell'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PasswordStrength, isPasswordStrong } from '@/components/auth/PasswordStrength'
import { authApi } from '@/api/endpoints'

const MAX_PASSWORD_LENGTH = 128

type ResetState = 'form' | 'submitting' | 'success' | 'error'

export const Route = createFileRoute('/reset-password')({
  component: ResetPasswordPage,
  validateSearch: (search: Record<string, unknown>) => ({
    token: typeof search.token === 'string' ? search.token : undefined,
  }),
})

function ResetPasswordPage() {
  const { token } = Route.useSearch()
  const navigate = useNavigate()

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [state, setState] = useState<ResetState>('form')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [submitError, setSubmitError] = useState<string | null>(null)

  if (!token) {
    return (
      <AuthShell
        title="Set a new password"
        showAside={false}
      >
        <div
          role="alert"
          className="rounded-2xl border border-destructive/30 bg-destructive/10 p-6 space-y-4"
        >
          <div className="flex items-start gap-3">
            <AlertCircle className="h-5 w-5 mt-0.5 text-destructive shrink-0" />
            <div className="space-y-1">
              <h2 className="text-base font-semibold text-destructive">
                Invalid or missing reset token
              </h2>
              <p className="text-sm text-muted-foreground">
                The reset link is missing a token. Request a new link.
              </p>
            </div>
          </div>
          <Button
            onClick={() => navigate({ to: '/forgot-password' })}
            className="btn-premium text-white h-11 w-full font-medium"
          >
            Request a new link
          </Button>
        </div>
      </AuthShell>
    )
  }

  const validate = () => {
    const errors: Record<string, string> = {}
    if (!password) {
      errors.password = 'Password is required'
    } else if (password.length > MAX_PASSWORD_LENGTH) {
      errors.password = `Password must be ${MAX_PASSWORD_LENGTH} characters or less`
    } else if (!isPasswordStrong(password)) {
      errors.password = 'Password does not meet the requirements'
    }
    if (!confirmPassword) {
      errors.confirmPassword = 'Please confirm your password'
    } else if (password !== confirmPassword) {
      errors.confirmPassword = 'Passwords do not match'
    }
    setFieldErrors(errors)
    return Object.keys(errors).length === 0
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitError(null)
    if (!validate()) return

    setState('submitting')
    try {
      await authApi.confirmPasswordReset(token, password, confirmPassword)
      setState('success')
    } catch (err) {
      const data = hasErrorResponse(err) ? (err.response?.data as Record<string, unknown> | undefined) : undefined
      const message =
        (typeof data?.detail === 'string' && data.detail) ||
        (typeof data?.message === 'string' && data.message) ||
        (Array.isArray(data?.token) && data.token[0]) ||
        (Array.isArray(data?.password) && data.password[0]) ||
        'We could not reset your password. The link may have expired.'
      setSubmitError(message)
      setState('error')
    }
  }

  if (state === 'success') {
    return (
      <AuthShell title="Password updated" showAside={false}>
        <div className="rounded-2xl border border-border/60 bg-card p-8 card-elevated text-center space-y-5">
          <CheckCircle2 className="h-10 w-10 mx-auto text-accent-brand" />
          <div className="space-y-2">
            <h2 className="text-xl font-semibold">All set</h2>
            <p className="text-sm text-muted-foreground">
              Password updated. Sign in with your new password.
            </p>
          </div>
          <Button
            onClick={() => navigate({ to: '/login' })}
            className="btn-premium text-white h-11 w-full font-medium"
          >
            Continue to sign in
          </Button>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell title="Set a new password" showAside={false}>
      <div className="rounded-2xl border border-border/60 bg-card p-8 card-elevated space-y-5">
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          {submitError && (
            <div
              role="alert"
              aria-live="polite"
              className="flex items-start gap-3 p-3.5 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm"
            >
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>{submitError}</span>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="password" className="text-sm font-medium">
              New password
            </Label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                id="password"
                type={showPassword ? 'text' : 'password'}
                placeholder="Create a strong password"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value)
                  if (fieldErrors.password) {
                    setFieldErrors({ ...fieldErrors, password: '' })
                  }
                }}
                className="h-11 pl-10 pr-10"
                autoComplete="new-password"
                required
                maxLength={MAX_PASSWORD_LENGTH}
                aria-invalid={!!fieldErrors.password}
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
              <p className="text-xs text-destructive">{fieldErrors.password}</p>
            )}
            <PasswordStrength password={password} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="confirmPassword" className="text-sm font-medium">
              Confirm new password
            </Label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                id="confirmPassword"
                type={showConfirmPassword ? 'text' : 'password'}
                placeholder="Re-enter your new password"
                value={confirmPassword}
                onChange={(e) => {
                  setConfirmPassword(e.target.value)
                  if (fieldErrors.confirmPassword) {
                    setFieldErrors({ ...fieldErrors, confirmPassword: '' })
                  }
                }}
                className="h-11 pl-10 pr-10"
                autoComplete="new-password"
                required
                maxLength={MAX_PASSWORD_LENGTH}
                aria-invalid={!!fieldErrors.confirmPassword}
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                aria-label={showConfirmPassword ? 'Hide password' : 'Show password'}
              >
                {showConfirmPassword ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </button>
              {confirmPassword && password === confirmPassword && (
                <CheckCircle2 className="absolute right-10 top-1/2 -translate-y-1/2 h-4 w-4 text-accent-brand" />
              )}
            </div>
            {fieldErrors.confirmPassword && (
              <p className="text-xs text-destructive">{fieldErrors.confirmPassword}</p>
            )}
          </div>

          <Button
            type="submit"
            className="w-full h-11 btn-premium text-white font-medium"
            disabled={state === 'submitting'}
          >
            {state === 'submitting' ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Updating password…
              </>
            ) : (
              'Update password'
            )}
          </Button>
        </form>
      </div>
    </AuthShell>
  )
}
