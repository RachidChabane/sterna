import { useState } from 'react'
import { Loader2, Mail } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/store/authStore'
import { useVerificationGateStore } from '@/store/verificationGateStore'
import { authApi } from '@/api/endpoints'
import { useToast } from '@/hooks/use-toast'
import { getApiErrorMessage } from '@/utils/errorMessages'

export function VerificationGateModal() {
  const isOpen = useVerificationGateStore((s) => s.isOpen)
  const reason = useVerificationGateStore((s) => s.reason)
  const close = useVerificationGateStore((s) => s.close)
  const user = useAuthStore((s) => s.user)
  const [isResending, setIsResending] = useState(false)
  const { toast } = useToast()

  const handleResend = async () => {
    if (!user?.email || isResending) return
    setIsResending(true)
    try {
      await authApi.resendVerification(user.email)
      toast({
        title: 'Verification email sent',
        description: 'Check your inbox for the link.',
      })
      close()
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

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && close()}>
      <DialogContent className="sm:max-w-[440px] rounded-2xl">
        <DialogHeader>
          <Mail className="h-10 w-10 text-accent-brand mx-auto mb-2" />
          <DialogTitle className="text-center">Verify your email first</DialogTitle>
          <DialogDescription className="text-center">
            To {reason}, please verify the email we sent to your inbox. You can resend
            the verification link below.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-end pt-2">
          <Button variant="outline" onClick={close} className="h-11 font-medium">
            Not now
          </Button>
          <Button
            className="btn-premium text-white h-11 font-medium"
            onClick={handleResend}
            disabled={isResending}
          >
            {isResending ? <Loader2 className="h-4 w-4 animate-spin mr-1.5" /> : null}
            Resend verification email
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
