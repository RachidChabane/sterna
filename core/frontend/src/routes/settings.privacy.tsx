import { createFileRoute } from '@tanstack/react-router'
import { DataExportSection } from '@/components/privacy/DataExportSection'
import { DeleteAccountSection } from '@/components/privacy/DeleteAccountSection'

export const Route = createFileRoute('/settings/privacy')({
  component: PrivacySettingsPage,
})

function PrivacySettingsPage() {
  // task-17 ships a ConsentSettingsDialog component for the cookie/consent
  // surface. When that lands, render it above the GDPR sections here.
  return (
    <div className="max-w-3xl mx-auto p-6 space-y-8">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Privacy & data</h1>
        <p className="text-sm text-muted-foreground">
          Export a copy of your data, or permanently delete your account
          (7-day grace period).
        </p>
      </header>
      <DataExportSection />
      <DeleteAccountSection />
    </div>
  )
}
