import { createFileRoute } from '@tanstack/react-router'
import { LegalLayout } from '@/components/legal/LegalLayout'
import { legalDocuments } from '@/content/legal'

export const Route = createFileRoute('/legal/terms')({
  component: TermsOfServicePage,
})

function TermsOfServicePage() {
  return <LegalLayout document={legalDocuments.terms} />
}
