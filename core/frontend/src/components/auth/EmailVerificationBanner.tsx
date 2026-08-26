import { useState } from 'react'
import { Loader2, Mail, X } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { authApi } from '@/api/endpoints'
import { useToast } from '@/hooks/use-toast'
import { getApiErrorMessage } from '@/utils/errorMessages'

const STORAGE_KEY = 'auth:verify-banner:dismissed'
const RESEND_COOLDOWN_MS = 60_000

function readDismissed(): boolean {
  if (typeof window === 'undefined') return false
  try {
    return sessionStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export function EmailVerificationBanner() {
  const user = useAuthStore((s) => s.user)
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const [dismissed, setDismissed] = useState<boolean>(readDismissed)
  const [isResending, setIsResending] = useState(false)
  const [resentAt, setResentAt] = useState<number | null>(null)
  const { toast } = useToast()

  const handleDismiss = () => {
    try {
      sessionStorage.setItem(STORAGE_KEY, '1')
    } catch {
      // sessionStorage may be unavailable (private mode, SSR) — fall back to memory only
    }
    setDismissed(true)
  }

  const handleResend = async () => {
    if (!user?.email || isResending) return
    if (resentAt && Date.now() - resentAt < RESEND_COOLDOWN_MS) return
    setIsResending(true)
    try {
      await authApi.resendVerification(user.email)
      setResentAt(Date.now())
      toast({
        title: 'Verification email sent',
        description: 'Check your inbox for the link.',
      })
    } catch (err) {
      toast({
        title: 'Could not resend',
        description: getApiErrorMessage(err, 'Try again in a moment.'),
        variant: 'destructive',
      })
    } finally {
      setIsResending(false)
    }
  }

  if (!isAuthenticated || !user || user.is_verified || dismissed) return null

  const resendDisabled =
    isResending || (resentAt !== null && Date.now() - resentAt < RESEND_COOLDOWN_MS)

  return (
    <div
      role="region"
      aria-label="Email verification required"
      className="w-full bg-accent-brand/10 border-b border-accent-brand/20 px-4 py-2.5 flex items-center gap-3"
    >
      <Mail className="h-4 w-4 text-accent-brand shrink-0" />
      <p className="text-sm text-foreground/90 flex-1">
        Verify your email <span className="font-medium">{user.email}</span> to unlock all
        features.
      </p>
      <Button
        variant="ghost"
        size="sm"
        onClick={handleResend}
        disabled={resendDisabled}
      >
        {isResending ? <Loader2 className="h-3 w-3 animate-spin mr-1.5" /> : null}
        Resend
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7"
        onClick={handleDismiss}
        aria-label="Dismiss verification banner"
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  )
}
