import { createFileRoute } from '@tanstack/react-router'
import { LegalLayout } from '@/components/legal/LegalLayout'
import { legalDocuments } from '@/content/legal'

export const Route = createFileRoute('/legal/aup')({
  component: AcceptableUsePolicyPage,
})

function AcceptableUsePolicyPage() {
  return <LegalLayout document={legalDocuments.aup} />
}
