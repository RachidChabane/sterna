import { createFileRoute } from '@tanstack/react-router'
import { LegalLayout } from '@/components/legal/LegalLayout'
import { legalDocuments } from '@/content/legal'

export const Route = createFileRoute('/legal/privacy')({
  component: PrivacyPolicyPage,
})

function PrivacyPolicyPage() {
  return <LegalLayout document={legalDocuments.privacy} />
}
