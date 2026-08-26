import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { AlertCircle, ExternalLink, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { billingApi } from '@/api/billing'
import type { BillingStatus, Invoice } from '@/api/types'
import { getApiErrorData } from '@/utils/errorMessages'

const INVOICES_PER_PAGE = 12

export const Route = createFileRoute('/settings/billing')({
  component: () => (
    <ProtectedRoute>
      <SettingsBilling />
    </ProtectedRoute>
  ),
})

function formatRenewalDate(unix: number | null): string | null {
  if (!unix) return null
  return new Date(unix * 1000).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

function formatInvoiceDate(unix: number): string {
  return new Date(unix * 1000).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function formatMinorUnits(amount: number, currency: string): string {
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: (currency || 'usd').toUpperCase(),
  }).format(amount / 100)
}

function SettingsBilling() {
  const [billing, setBilling] = useState<BillingStatus | null>(null)
  const [opening, setOpening] = useState(false)
  const [invoices, setInvoices] = useState<Invoice[] | null>(null)
  const [invoicesLoading, setInvoicesLoading] = useState(false)
  const [invoicesError, setInvoicesError] = useState<string | null>(null)
  const [invoicesPage, setInvoicesPage] = useState(0)

  useEffect(() => {
    billingApi.getBillingStatus().then(setBilling).catch(() => {})
  }, [])

  useEffect(() => {
    if (!billing?.is_paid) return
    setInvoicesLoading(true)
    setInvoicesError(null)
    billingApi
      .listInvoices()
      .then(({ results }) => setInvoices(results))
      .catch(() => setInvoicesError('Could not load invoices.'))
      .finally(() => setInvoicesLoading(false))
  }, [billing?.is_paid])

  const openPortal = async () => {
    setOpening(true)
    try {
      const { url } = await billingApi.createPortalSession()
      window.location.href = url
    } catch (err) {
      setOpening(false)
      const code = getApiErrorData(err)?.error
      if (code === 'no_subscription') {
        toast('You need a paid plan first.', {
          description: 'Upgrade from the pricing page to manage billing.',
          action: {
            label: 'See pricing',
            onClick: () => {
              window.location.href = '/pricing'
            },
          },
        })
      } else {
        toast('Could not open billing portal.')
      }
    }
  }

  if (!billing) {
    return (
      <div className="p-8">
        <Loader2 className="animate-spin" />
      </div>
    )
  }

  const renewalDate = formatRenewalDate(billing.current_period_end)
  const showCancellation =
    billing.is_paid && billing.cancel_at_period_end && renewalDate

  return (
    <div className="max-w-2xl mx-auto p-8 space-y-8">
      <header>
        <h1 className="text-2xl font-semibold">Billing</h1>
        <p className="text-muted-foreground mt-1">
          Manage your subscription, payment method, and invoices.
        </p>
      </header>

      {showCancellation && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium text-amber-900 dark:text-amber-200">
              Your plan ends on {renewalDate}
            </p>
            <p className="text-amber-800/80 dark:text-amber-200/80 mt-1">
              You'll keep access to {billing.plan_display_name} features until
              then, and then return to the Free plan. You can resume your
              subscription anytime from the portal.
            </p>
          </div>
        </div>
      )}

      <section className="border rounded-lg p-6 space-y-3">
        <div className="flex items-baseline justify-between">
          <div>
            <p className="text-sm text-muted-foreground">Current plan</p>
            <h2 className="text-xl font-medium">{billing.plan_display_name}</h2>
          </div>
          {!billing.is_paid && (
            <a href="/pricing" className="text-sm text-primary hover:underline">
              See plans →
            </a>
          )}
        </div>
        {billing.plan_description && (
          <p className="text-sm text-muted-foreground">
            {billing.plan_description}
          </p>
        )}
        {billing.is_paid &&
          renewalDate &&
          !billing.cancel_at_period_end && (
            <p className="text-sm text-muted-foreground">
              Next renewal:{' '}
              <span className="font-medium text-foreground">{renewalDate}</span>
            </p>
          )}
      </section>

      {billing.is_paid && (
        <>
          <section className="border rounded-lg p-6 space-y-4">
            <h3 className="font-medium">Subscription management</h3>
            <p className="text-sm text-muted-foreground">
              Update your payment method, view invoices, change billing cycle, or
              cancel your subscription via Stripe's secure portal.
            </p>
            <button
              type="button"
              onClick={openPortal}
              disabled={opening}
              className="inline-flex items-center gap-2 rounded-md bg-primary text-primary-foreground px-4 py-2 text-sm font-medium disabled:opacity-50"
            >
              {opening ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ExternalLink className="h-4 w-4" />
              )}
              Manage subscription
            </button>
          </section>

          <section className="border rounded-lg p-6 space-y-4">
            <h3 className="font-medium">Invoice history</h3>
            {invoicesLoading && (
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            )}
            {invoicesError && (
              <p className="text-sm text-destructive">{invoicesError}</p>
            )}
            {invoices && invoices.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No invoices yet.
              </p>
            )}
            {invoices && invoices.length > 0 && (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-muted-foreground border-b">
                        <th className="py-2 pr-4 font-medium">Date</th>
                        <th className="py-2 pr-4 font-medium">Amount</th>
                        <th className="py-2 pr-4 font-medium">VAT</th>
                        <th className="py-2 pr-4 font-medium">Status</th>
                        <th className="py-2 pr-4 font-medium">Invoice</th>
                      </tr>
                    </thead>
                    <tbody>
                      {invoices
                        .slice(
                          invoicesPage * INVOICES_PER_PAGE,
                          (invoicesPage + 1) * INVOICES_PER_PAGE,
                        )
                        .map((inv) => (
                          <tr
                            key={inv.id}
                            className="border-b last:border-b-0"
                          >
                            <td className="py-2 pr-4">
                              {formatInvoiceDate(inv.created)}
                            </td>
                            <td className="py-2 pr-4">
                              {formatMinorUnits(inv.total, inv.currency)}
                            </td>
                            <td className="py-2 pr-4">
                              {inv.tax > 0
                                ? formatMinorUnits(inv.tax, inv.currency)
                                : '—'}
                            </td>
                            <td className="py-2 pr-4 capitalize">
                              {inv.status}
                            </td>
                            <td className="py-2 pr-4">
                              {inv.hosted_invoice_url ? (
                                <a
                                  href={inv.hosted_invoice_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-primary hover:underline inline-flex items-center gap-1"
                                >
                                  View <ExternalLink className="h-3 w-3" />
                                </a>
                              ) : (
                                <span className="text-muted-foreground">—</span>
                              )}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
                {invoices.length > INVOICES_PER_PAGE && (
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">
                      Page {invoicesPage + 1} of{' '}
                      {Math.ceil(invoices.length / INVOICES_PER_PAGE)}
                    </span>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        disabled={invoicesPage === 0}
                        onClick={() => setInvoicesPage((p) => p - 1)}
                        className="rounded-md border px-3 py-1 disabled:opacity-50"
                      >
                        Previous
                      </button>
                      <button
                        type="button"
                        disabled={
                          (invoicesPage + 1) * INVOICES_PER_PAGE >=
                          invoices.length
                        }
                        onClick={() => setInvoicesPage((p) => p + 1)}
                        className="rounded-md border px-3 py-1 disabled:opacity-50"
                      >
                        Next
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </section>
        </>
      )}
    </div>
  )
}
