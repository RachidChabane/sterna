import { useEffect, useState } from 'react'
import { Check, Loader2 } from 'lucide-react'
import { Link, useNavigate } from '@tanstack/react-router'
import { toast } from 'sonner'

import { billingApi } from '@/api/billing'
import { subscriptionApi } from '@/api/subscription'
import type { SubscriptionPlan } from '@/api/types'
import { useAuthStore } from '@/store/authStore'
import { TIERS, yearlyTotal, type Tier, type TierSlug } from '@/lib/pricingData'
import { getApiErrorData } from '@/utils/errorMessages'

interface PricingCardsProps {
  billing: 'monthly' | 'yearly'
}

export function PricingCards({ billing }: PricingCardsProps) {
  const user = useAuthStore((s) => s.user)
  const navigate = useNavigate()
  const [currentPlan, setCurrentPlan] = useState<SubscriptionPlan | null>(null)
  const [upgrading, setUpgrading] = useState<TierSlug | null>(null)
  const [openingPortal, setOpeningPortal] = useState(false)

  useEffect(() => {
    if (!user) return
    subscriptionApi
      .getPlan()
      .then(setCurrentPlan)
      .catch(() => {})
  }, [user])

  const displayPrice = (tier: Tier) => {
    if (tier.monthlyPrice === 0) return '$0'
    if (billing === 'yearly') {
      const perMonth = Math.floor(yearlyTotal(tier) / 12)
      return `$${perMonth}`
    }
    return `$${tier.monthlyPrice}`
  }

  // Plan changes for users with an active paid subscription (including
  // the free-tier "Downgrade" button) go through the Stripe Customer
  // Portal — a new Checkout Session would create a second subscription.
  const openPortal = async () => {
    setOpeningPortal(true)
    try {
      const { url } = await billingApi.createPortalSession()
      window.location.href = url
    } catch {
      setOpeningPortal(false)
      toast('Could not open the billing portal.', {
        description: 'Please try again.',
      })
    }
  }

  const handleUpgrade = async (targetSlug: TierSlug) => {
    if (currentPlan?.name === targetSlug) return
    if (targetSlug === 'free') return

    if (!user) {
      navigate({
        to: '/signup',
        search: {
          return_to: `/pricing?intent=upgrade&plan=${targetSlug}&cycle=${billing}`,
        },
      })
      return
    }

    if (!user.is_verified) {
      toast('Verify your email to upgrade', {
        description: 'Check your inbox for the verification link.',
      })
      return
    }

    setUpgrading(targetSlug)
    try {
      const { url } = await billingApi.createCheckoutSession({
        plan_slug: targetSlug as 'plus' | 'pro',
        billing_cycle: billing,
      })
      window.location.href = url
    } catch (err) {
      setUpgrading(null)
      const code = getApiErrorData(err)?.error
      if (code === 'use_portal') {
        // Paid→paid plan changes are handled by the Customer Portal
        // (the backend refuses a second Checkout with 409 USE_PORTAL).
        void openPortal()
      } else if (code === 'already_on_plan') {
        toast('You are already on this plan.')
      } else if (
        code === 'billing_unavailable' ||
        code === 'stripe_misconfigured'
      ) {
        toast('Billing is temporarily unavailable.', {
          description:
            'Please try again in a minute or contact support.',
        })
      } else {
        toast('Could not start checkout.', {
          description: 'Please try again.',
        })
      }
    }
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl mx-auto">
      {TIERS.map((tier) => {
        const isCurrent = currentPlan?.name === tier.slug
        const price = displayPrice(tier)

        return (
          <div
            key={tier.slug}
            data-testid={`tier-card-${tier.slug}`}
            className={`relative rounded-md p-6 flex flex-col bg-background ${
              tier.highlighted
                ? 'border-2 border-foreground/80 shadow-hard'
                : isCurrent
                  ? 'border-2 border-primary'
                  : 'border-2 border-foreground/15'
            }`}
          >
            {tier.highlighted && (
              <span className="absolute -top-4 left-1/2 -translate-x-1/2 -rotate-2 rounded-sm border-2 border-foreground/80 bg-highlight px-3 py-1 font-mono text-[10px] font-bold uppercase tracking-widest text-highlight-foreground shadow-hard-sm">
                Most popular
              </span>
            )}

            <div className="mb-4">
              <h2 className="font-display text-2xl font-bold">{tier.name}</h2>
              <div className="mt-2 flex items-end gap-1">
                <span className="text-3xl font-semibold">{price}</span>
                {tier.monthlyPrice > 0 && (
                  <span className="text-sm text-muted-foreground mb-0.5">/mo</span>
                )}
              </div>
              {billing === 'yearly' && tier.monthlyPrice > 0 && (
                <p className="text-xs text-muted-foreground mt-1">
                  billed ${yearlyTotal(tier)}/yr
                </p>
              )}
              <p className="text-sm text-muted-foreground mt-2">{tier.description}</p>
            </div>

            <ul className="space-y-2 flex-1">
              {tier.features.map((row, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <Check className="h-4 w-4 mt-0.5 text-brand-500 flex-shrink-0" />
                  {row}
                </li>
              ))}
            </ul>

            <div className="mt-6">
              {tier.slug === 'free' ? (
                user ? (
                  <button
                    type="button"
                    disabled={isCurrent || openingPortal}
                    title={
                      isCurrent
                        ? 'You are already on the Free plan'
                        : 'Downgrades are handled in the billing portal'
                    }
                    onClick={() => !isCurrent && openPortal()}
                    className="w-full py-2.5 rounded-md border-2 border-foreground/25 text-sm font-medium disabled:opacity-50 hover:border-foreground/60 transition-colors inline-flex items-center justify-center gap-2"
                  >
                    {openingPortal && !isCurrent && (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    )}
                    {isCurrent ? 'Current plan' : 'Downgrade'}
                  </button>
                ) : (
                  <Link
                    to="/signup"
                    className="block w-full text-center py-2.5 rounded-md border-2 border-foreground/25 text-sm font-medium hover:border-foreground/60 transition-colors"
                  >
                    Get started
                  </Link>
                )
              ) : user ? (
                <button
                  type="button"
                  disabled={isCurrent || upgrading !== null}
                  onClick={() => !isCurrent && handleUpgrade(tier.slug)}
                  className="btn-premium w-full py-2.5 rounded-md text-sm font-semibold disabled:opacity-50 inline-flex items-center justify-center gap-2"
                >
                  {upgrading === tier.slug && (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  )}
                  {isCurrent ? 'Current plan' : 'Upgrade'}
                </button>
              ) : (
                <Link
                  to="/signup"
                  className="btn-premium block w-full text-center py-2.5 rounded-md text-sm font-semibold"
                >
                  Sign up
                </Link>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
