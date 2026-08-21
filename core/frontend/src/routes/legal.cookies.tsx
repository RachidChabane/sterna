import { createFileRoute } from '@tanstack/react-router'
import { LegalLayout } from '@/components/legal/LegalLayout'
import { legalDocuments } from '@/content/legal'

export const Route = createFileRoute('/legal/cookies')({
  component: CookiePolicyPage,
})

function CookiePolicyPage() {
  return <LegalLayout document={legalDocuments.cookies} />
}
