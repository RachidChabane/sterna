import { createFileRoute } from '@tanstack/react-router'
import { LegalLayout } from '@/components/legal/LegalLayout'
import { legalDocuments } from '@/content/legal'

export const Route = createFileRoute('/legal/refunds')({
  component: RefundPolicyPage,
})

function RefundPolicyPage() {
  return <LegalLayout document={legalDocuments.refunds} />
}
