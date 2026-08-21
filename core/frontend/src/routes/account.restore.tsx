import { createFileRoute, useSearch } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import apiClient from '@/api/client'
import { Loader2 } from 'lucide-react'

interface ApiError {
  response?: { data?: { error?: string } }
}

export const Route = createFileRoute('/account/restore')({
  validateSearch: (s: Record<string, unknown>): { token: string } => ({
    token: typeof s.token === 'string' ? s.token : '',
  }),
  component: RestorePage,
})

function RestorePage() {
  const { token } = useSearch({ from: '/account/restore' })
  const [state, setState] = useState<'pending' | 'ok' | 'err'>('pending')
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!token) {
      setState('err')
      setErr('Missing token.')
      return
    }
    apiClient
      .post('/auth/account/delete-request/cancel/', { token })
      .then(() => setState('ok'))
      .catch((e) => {
        const apiErr = e as ApiError
        setState('err')
        setErr(apiErr?.response?.data?.error || 'Cancellation failed.')
      })
  }, [token])

  if (state === 'pending') {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-2">
        <Loader2 className="h-6 w-6 animate-spin" />
        <p>Restoring your account…</p>
      </div>
    )
  }

  if (state === 'ok') {
    return (
      <div className="mx-auto max-w-md p-8 space-y-4">
        <h1 className="text-2xl font-semibold">Account restored</h1>
        <p>
          Your deletion request has been canceled. Sign in to continue
          using your account.
        </p>
        <a href="/login" className="underline">
          Sign in
        </a>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-md p-8 space-y-4">
      <h1 className="text-2xl font-semibold">Could not restore</h1>
      <p className="text-destructive">{err}</p>
      <p className="text-sm text-muted-foreground">
        If the grace period has expired, the account is permanently
        deleted and cannot be recovered.
      </p>
    </div>
  )
}
