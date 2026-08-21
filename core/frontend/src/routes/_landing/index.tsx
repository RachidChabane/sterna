import { createFileRoute, redirect } from '@tanstack/react-router'
import { useAuthStore } from '@/store/authStore'
import { useSeoHead } from '@/hooks/useSeoHead'
import { Hero } from '@/components/marketing/Hero'
import { FeatureGrid } from '@/components/marketing/FeatureGrid'
import { BYOKCallout } from '@/components/marketing/BYOKCallout'
import { PricingTeaser } from '@/components/marketing/PricingTeaser'
import { FAQExcerpt } from '@/components/marketing/FAQExcerpt'

export const Route = createFileRoute('/_landing/')({
  beforeLoad: () => {
    const { isAuthenticated } = useAuthStore.getState()
    if (isAuthenticated) {
      throw redirect({ to: '/chats' })
    }
  },
  component: LandingPage,
})

function LandingPage() {
  useSeoHead({
    title: 'Sterna — Your AI, Your Rules',
    description:
      'Chat, code, create, and discover with every top AI model. Bring your own key. Own your data.',
  })
  return (
    <>
      <Hero />
      <FeatureGrid />
      <BYOKCallout />
      <PricingTeaser />
      <FAQExcerpt />
    </>
  )
}
