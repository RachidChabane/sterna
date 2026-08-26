import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { CheckCircle2, Loader2, Mail } from 'lucide-react'
import { AuthShell } from '@/components/auth/AuthShell'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { authApi } from '@/api/endpoints'
import { useToast } from '@/hooks/use-toast'

const MAX_EMAIL_LENGTH = 254

function sanitizeEmail(input: string): string {
  return input
    .replace(/<[^>]*>/g, '')
    .replace(/[<>"]/g, '')
    .trim()
    .toLowerCase()
}

type ForgotState = 'idle' | 'submitting' | 'submitted'

export const Route = createFileRoute('/forgot-password')({
  component: ForgotPasswordPage,
})

function ForgotPasswordPage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [email, setEmail] = useState('')
  const [state, setState] = useState<ForgotState>('idle')
  const [fieldError, setFieldError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFieldError(null)
    const sanitized = sanitizeEmail(email)
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!sanitized) {
      setFieldError('Please enter your email address')
      return
    }
    if (!emailRegex.test(sanitized)) {
      setFieldError('Please enter a valid email address')
      return
    }
    if (sanitized.length > MAX_EMAIL_LENGTH) {
      setFieldError(`Email must be ${MAX_EMAIL_LENGTH} characters or less`)
      return
    }

    setState('submitting')
    try {
      await authApi.resetPassword(sanitized)
    } catch (err) {
      // Backend always returns 200 to avoid email enumeration, but log
      // anything unexpected without leaking it to the user.
      console.error('Password reset request failed:', err)
    } finally {
      setState('submitted')
    }
  }

  return (
    <AuthShell
      title="Reset your password"
      subtitle="Enter your email and we'll send you a link to reset your password."
      showAside={false}
    >
      <div className="rounded-2xl border border-border/60 bg-card p-8 card-elevated space-y-5">
        {state === 'submitted' ? (
          <div className="text-center space-y-5">
            <CheckCircle2 className="h-10 w-10 mx-auto text-accent-brand" />
            <div className="space-y-2">
              <h2 className="text-xl font-semibold">Check your inbox</h2>
              <p className="text-sm text-muted-foreground">
                If an account exists with that email, we sent a reset link.
              </p>
            </div>
            <Button
              onClick={() => navigate({ to: '/login' })}
              variant="outline"
              className="h-11 w-full font-medium"
            >
              Back to sign in
            </Button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
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
                  onChange={(e) => {
                    setEmail(e.target.value)
                    if (fieldError) setFieldError(null)
                  }}
                  className="h-11 pl-10"
                  autoComplete="email"
                  autoFocus
                  required
                  maxLength={MAX_EMAIL_LENGTH}
                  aria-invalid={!!fieldError}
                  aria-describedby={fieldError ? 'email-error' : undefined}
                />
              </div>
              {fieldError && (
                <p id="email-error" className="text-xs text-destructive">
                  {fieldError}
                </p>
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
                  Sending…
                </>
              ) : (
                'Send reset link'
              )}
            </Button>

            <p className="text-center text-sm text-muted-foreground">
              Remember your password?{' '}
              <Link
                to="/login"
                className="font-medium text-accent-brand hover:text-accent-brand/80"
              >
                Sign in
              </Link>
            </p>
          </form>
        )}
      </div>
    </AuthShell>
  )
}
