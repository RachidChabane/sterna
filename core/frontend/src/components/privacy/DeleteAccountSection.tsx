import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import apiClient, { clearTokens } from '@/api/client'
import { useAuthStore } from '@/store/authStore'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Loader2, Trash2 } from 'lucide-react'

interface ApiError {
  response?: { data?: { error?: string }; status?: number }
}

export function DeleteAccountSection() {
  const user = useAuthStore((s) => s.user)
  const navigate = useNavigate()
  // The auth API's User payload does not expose password-usability
  // (authentication/serializers.py UserSerializer), so we always show the
  // password field. AccountDeletionRequestView only verifies the password
  // when the account has a usable one, so OAuth-only users can submit with
  // the field left empty.
  const hasPassword = true
  const expectedEmail = (user?.email || '').toLowerCase()

  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [confirmEmail, setConfirmEmail] = useState('')
  const [understood, setUnderstood] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    setError('')
    if (!understood) {
      setError('Please confirm you understand this is permanent.')
      return
    }
    if (confirmEmail.trim().toLowerCase() !== expectedEmail) {
      setError('Email confirmation does not match.')
      return
    }
    setSubmitting(true)
    try {
      const body: Record<string, string> = { confirm_email: confirmEmail }
      if (hasPassword) body.password = password
      const res = await apiClient.post(
        '/auth/account/delete-request/',
        body,
      )
      // Clear local session and redirect to login with a scheduled flag.
      clearTokens()
      const scheduledFor = res.data?.scheduled_for
      const qs = scheduledFor
        ? `?account_deletion=scheduled&scheduled_for=${encodeURIComponent(scheduledFor)}`
        : '?account_deletion=scheduled'
      navigate({ to: `/login${qs}` })
    } catch (e) {
      const err = e as ApiError
      setError(err.response?.data?.error || 'Failed to schedule deletion.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Delete your account</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Schedule permanent deletion of your account and personal data.
          You have <strong>7 days</strong> to cancel via the link we email
          you. After 7 days the account is purged and cannot be restored.
        </p>
        <Button
          variant="destructive"
          onClick={() => setOpen(true)}
          className="gap-2"
        >
          <Trash2 className="h-4 w-4" />
          Schedule account deletion
        </Button>
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm account deletion</DialogTitle>
            <DialogDescription>
              This will mark your account inactive and schedule it for
              permanent deletion in 7 days. You will be signed out.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {hasPassword && (
              <div className="space-y-1">
                <Label htmlFor="del-pw">Password</Label>
                <Input
                  id="del-pw"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                />
              </div>
            )}
            <div className="space-y-1">
              <Label htmlFor="del-email">
                Type your email to confirm:{' '}
                <span className="font-mono">{expectedEmail}</span>
              </Label>
              <Input
                id="del-email"
                type="email"
                value={confirmEmail}
                onChange={(e) => setConfirmEmail(e.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="flex items-start gap-2">
              <Checkbox
                id="del-understood"
                checked={understood}
                onCheckedChange={(v) => setUnderstood(Boolean(v))}
              />
              <Label htmlFor="del-understood" className="text-sm">
                I understand this is permanent after the 7-day grace
                period.
              </Label>
            </div>
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={submit}
              disabled={submitting}
              className="gap-2"
            >
              {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
              Schedule deletion
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
