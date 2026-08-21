import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle2, Loader2, Mail } from 'lucide-react'
import { AuthShell } from '@/components/auth/AuthShell'
import { Button } from '@/components/ui/button'
import { authApi } from '@/api/endpoints'
import { useToast } from '@/hooks/use-toast'

type VerifyStatus = 'loading' | 'success' | 'error' | 'pending'

const RESEND_COOLDOWN_MS = 60_000

export const Route = createFileRoute('/verify-email')({
  component: VerifyEmailPage,
  validateSearch: (search: Record<string, unknown>) => ({
    token: typeof search.token === 'string' ? search.token : undefined,
    pending:
      search.pending === '1' || search.pending === 1
        ? (1 as const)
        : undefined,
    email: typeof search.email === 'string' ? search.email : undefined,
  }),
})

function VerifyEmailPage() {
  const { token, pending, email } = Route.useSearch()
  const navigate = useNavigate()
  const { toast } = useToast()

  const [status, setStatus] = useState<VerifyStatus>(() => {
    if (token) return 'loading'
    return 'pending'
  })
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isResending, setIsResending] = useState(false)
  const [resentAt, setResentAt] = useState<number | null>(null)

  useEffect(() => {
    if (!token) {
      // Already in pending or no-token state, nothing to verify.
      if (!pending) setStatus('pending')
      return
    }

    let cancelled = false
    setStatus('loading')

    authApi
      .verifyEmail(token)
      .then(() => {
        if (cancelled) return
        setStatus('success')
      })
      .catch((err: any) => {
        if (cancelled) return
        const message =
          err.response?.data?.detail ||
          err.response?.data?.message ||
          'We could not verify your email. The link may have expired.'
        setErrorMessage(message)
        setStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [token, pending])

  const handleResend = async () => {
    if (!email) {
      toast({
        title: 'Email required',
        description:
          'We need your email to send a new verification link. Sign in first to resend.',
        variant: 'destructive',
      })
      return
    }
    if (resentAt && Date.now() - resentAt < RESEND_COOLDOWN_MS) return
    setIsResending(true)
    try {
      await authApi.resendVerification(email)
      setResentAt(Date.now())
      toast({
        title: 'Verification email sent',
        description: 'Check your inbox for the link.',
      })
    } catch (err: any) {
      toast({
        title: 'Could not resend',
        description:
          err.response?.data?.detail ||
          err.response?.data?.message ||
          'Try again in a moment.',
        variant: 'destructive',
      })
    } finally {
      setIsResending(false)
    }
  }

  const resendDisabled =
    isResending || (resentAt !== null && Date.now() - resentAt < RESEND_COOLDOWN_MS)

  return (
    <AuthShell title="Verify your email" showAside={false}>
      <div className="rounded-2xl border border-border/60 bg-card p-8 card-elevated text-center space-y-5">
        {status === 'loading' && (
          <>
            <Loader2 className="h-10 w-10 mx-auto text-accent-brand animate-spin" />
            <p className="text-base text-foreground">Verifying your email…</p>
          </>
        )}

        {status === 'success' && (
          <>
            <CheckCircle2 className="h-10 w-10 mx-auto text-accent-brand" />
            <div className="space-y-2">
              <h2 className="text-xl font-semibold">Email verified</h2>
              <p className="text-sm text-muted-foreground">
                You can now sign in to Sterna.
              </p>
            </div>
            <Button
              onClick={() => navigate({ to: '/login' })}
              className="btn-premium text-white h-11 w-full font-medium"
            >
              Continue to sign in
            </Button>
          </>
        )}

        {status === 'error' && (
          <>
            <AlertCircle className="h-10 w-10 mx-auto text-destructive" />
            <div className="space-y-2">
              <h2 className="text-xl font-semibold">Verification failed</h2>
              <p className="text-sm text-muted-foreground">
                {errorMessage || 'The verification link is invalid or expired.'}
              </p>
            </div>
            <Button
              onClick={() =>
                navigate({
                  to: '/verify-email',
                  search: { pending: 1 as const, token: undefined, email: undefined },
                })
              }
              className="btn-premium text-white h-11 w-full font-medium"
            >
              Request a new link
            </Button>
          </>
        )}

        {status === 'pending' && (
          <>
            <Mail className="h-10 w-10 mx-auto text-accent-brand" />
            <div className="space-y-2">
              <h2 className="text-xl font-semibold">Check your inbox</h2>
              <p className="text-sm text-muted-foreground">
                {email ? (
                  <>
                    We sent a verification link to{' '}
                    <span className="font-medium text-foreground">{email}</span>.
                  </>
                ) : (
                  <>We sent you a verification link. Click it to activate your account.</>
                )}
              </p>
            </div>
            <Button
              onClick={handleResend}
              disabled={resendDisabled}
              variant="outline"
              className="h-11 w-full font-medium"
            >
              {isResending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Sending…
                </>
              ) : (
                'Resend verification email'
              )}
            </Button>
            <p className="text-xs text-muted-foreground">
              Already verified?{' '}
              <button
                type="button"
                onClick={() => navigate({ to: '/login' })}
                className="text-accent-brand hover:text-accent-brand/80 font-medium"
              >
                Sign in
              </button>
            </p>
          </>
        )}
      </div>
    </AuthShell>
  )
}
