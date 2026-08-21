import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { useSeoHead } from '@/hooks/useSeoHead'
import { BillingToggle } from '@/components/pricing/BillingToggle'
import { PricingCards } from '@/components/pricing/PricingCards'
import { ComparisonTable } from '@/components/pricing/ComparisonTable'
import { AllPlansInclude } from '@/components/pricing/AllPlansInclude'
import { FAQExcerpt } from '@/components/marketing/FAQExcerpt'

export const Route = createFileRoute('/_landing/pricing')({
  component: PricingPage,
})

function PricingPage() {
  useSeoHead({
    title: 'Pricing — Sterna',
    description:
      'Free, Plus ($20/mo), and Pro ($100/mo) plans. Bring your own key on any plan.',
  })
  const [billing, setBilling] = useState<'monthly' | 'yearly'>('monthly')
  return (
    <div className="container mx-auto py-16 px-4 space-y-16">
      <header className="text-center space-y-4">
        <h1 className="font-display text-4xl sm:text-5xl font-bold">Simple, transparent pricing</h1>
        <p className="text-muted-foreground text-lg max-w-xl mx-auto">
          Start free. Upgrade when you're ready. No hidden fees.
        </p>
        <BillingToggle value={billing} onChange={setBilling} />
      </header>
      <PricingCards billing={billing} />
      <AllPlansInclude />
      <ComparisonTable />
      <section className="text-center">
        <FAQExcerpt />
      </section>
      <p className="text-center text-sm text-muted-foreground">
        Prices exclude VAT; final price shown at checkout.
      </p>
    </div>
  )
}
