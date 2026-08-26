import { createFileRoute, useNavigate, useSearch } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { CheckCircle2, Loader2 } from 'lucide-react'

import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { billingApi } from '@/api/billing'
import type { SyncFromSessionResponse } from '@/api/types'
import { getApiErrorData } from '@/utils/errorMessages'

type Search = { session_id?: string }

export const Route = createFileRoute('/billing/return')({
  validateSearch: (s: Record<string, unknown>): Search => ({
    session_id: typeof s.session_id === 'string' ? s.session_id : undefined,
  }),
  component: () => (
    <ProtectedRoute>
      <BillingReturn />
    </ProtectedRoute>
  ),
})

type SyncState =
  | { status: 'loading' }
  | { status: 'success'; data: SyncFromSessionResponse }
  | { status: 'error'; message: string }

function BillingReturn() {
  const { session_id } = useSearch({ from: '/billing/return' })
  const navigate = useNavigate()
  const [state, setState] = useState<SyncState>({ status: 'loading' })

  useEffect(() => {
    if (!session_id) {
      setState({ status: 'error', message: 'Missing session ID.' })
      return
    }
    billingApi
      .syncFromSession(session_id)
      .then((data) => setState({ status: 'success', data }))
      .catch((err: unknown) => {
        const data = getApiErrorData(err)
        const message = data?.message || data?.error || 'Could not confirm subscription.'
        setState({ status: 'error', message })
      })
  }, [session_id])

  useEffect(() => {
    if (state.status === 'success') {
      const t = window.setTimeout(
        () => navigate({ to: '/settings/billing' }),
        3000,
      )
      return () => window.clearTimeout(t)
    }
  }, [state.status, navigate])

  return (
    <div className="max-w-md mx-auto mt-20 px-4 text-center">
      {state.status === 'loading' && (
        <>
          <Loader2 className="h-10 w-10 animate-spin mx-auto text-primary" />
          <p className="mt-4 text-muted-foreground">
            Confirming your subscription…
          </p>
        </>
      )}

      {state.status === 'success' && (
        <>
          <CheckCircle2 className="h-12 w-12 mx-auto text-emerald-500" />
          <h1 className="mt-4 text-2xl font-semibold">
            Welcome to {state.data.plan_display_name}!
          </h1>
          <p className="mt-2 text-muted-foreground">
            Your subscription is active. Redirecting to billing settings…
          </p>
        </>
      )}

      {state.status === 'error' && (
        <>
          <h1 className="text-xl font-semibold">Something went wrong</h1>
          <p className="mt-2 text-muted-foreground">{state.message}</p>
          <p className="mt-4 text-sm text-muted-foreground">
            Your payment may still process. If your plan doesn't appear in{' '}
            <a className="underline" href="/settings/billing">
              billing settings
            </a>{' '}
            within a minute, contact support.
          </p>
        </>
      )}
    </div>
  )
}
