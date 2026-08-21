import { createFileRoute } from '@tanstack/react-router'
import { LegalLayout } from '@/components/legal/LegalLayout'
import { legalDocuments } from '@/content/legal'

export const Route = createFileRoute('/legal/dpa')({
  component: DataProcessingAgreementPage,
})

function DataProcessingAgreementPage() {
  return <LegalLayout document={legalDocuments.dpa} />
}
