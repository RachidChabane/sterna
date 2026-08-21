import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Switch } from '@/components/ui/switch'
import { useConsentStore } from '@/store/consentStore'
import type { ConsentCategories } from '@/api/types'

type Mode = 'modal' | 'page'

interface ConsentSettingsDialogProps {
  mode?: Mode
}

interface CategoryRowProps {
  label: string
  description: string
  switchId: string
  checked: boolean
  disabled?: boolean
  onCheckedChange?: (next: boolean) => void
}

function CategoryRow({
  label,
  description,
  switchId,
  checked,
  disabled,
  onCheckedChange,
}: CategoryRowProps) {
  return (
    <div className="flex items-start justify-between gap-4 py-3 border-b border-border last:border-b-0">
      <div className="flex flex-col gap-1">
        <label
          htmlFor={switchId}
          className="text-sm font-medium leading-none cursor-pointer"
        >
          {label}
        </label>
        <p className="text-xs text-muted-foreground leading-snug">{description}</p>
      </div>
      <Switch
        id={switchId}
        checked={checked}
        disabled={disabled}
        onCheckedChange={onCheckedChange}
        aria-label={label}
      />
    </div>
  )
}

function ConsentBody({
  draft,
  setDraft,
  onSave,
  onAcceptAll,
  onRejectAll,
  onCancel,
  isSaving,
  mode,
}: {
  draft: ConsentCategories
  setDraft: (next: ConsentCategories) => void
  onSave: () => void
  onAcceptAll: () => void
  onRejectAll: () => void
  onCancel?: () => void
  isSaving: boolean
  mode: Mode
}) {
  return (
    <div className="flex flex-col">
      <div className="px-1">
        <CategoryRow
          label="Essential"
          description="Required for sign-in and basic site function. Always on."
          switchId="consent-essential"
          checked={true}
          disabled
        />
        <CategoryRow
          label="Analytics"
          description="Help us understand how Sterna is used (page views, feature usage). No personal data is sold."
          switchId="consent-analytics"
          checked={draft.analytics}
          onCheckedChange={(next) => setDraft({ ...draft, analytics: next })}
        />
        <CategoryRow
          label="Marketing"
          description="Reserved for future use. Currently off and not used."
          switchId="consent-marketing"
          checked={draft.marketing}
          onCheckedChange={(next) => setDraft({ ...draft, marketing: next })}
        />
      </div>

      <div className="flex flex-col gap-3 pt-4 mt-4 border-t border-border sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onRejectAll}
            disabled={isSaving}
          >
            Reject all
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onAcceptAll}
            disabled={isSaving}
          >
            Accept all
          </Button>
        </div>
        <div className="flex gap-2 sm:justify-end">
          {mode === 'modal' && onCancel ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onCancel}
              disabled={isSaving}
            >
              Cancel
            </Button>
          ) : null}
          <Button
            type="button"
            size="sm"
            onClick={onSave}
            disabled={isSaving}
          >
            Save preferences
          </Button>
        </div>
      </div>
    </div>
  )
}

export function ConsentSettingsDialog({ mode = 'modal' }: ConsentSettingsDialogProps) {
  const isDialogOpen = useConsentStore((s) => s.isDialogOpen)
  const closeDialog = useConsentStore((s) => s.closeDialog)
  const storeCategories = useConsentStore((s) => s.categories)
  const saveCategories = useConsentStore((s) => s.saveCategories)
  const acceptAll = useConsentStore((s) => s.acceptAll)
  const rejectAll = useConsentStore((s) => s.rejectAll)

  const [draft, setDraft] = useState<ConsentCategories>(storeCategories)
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    setDraft(storeCategories)
  }, [storeCategories, isDialogOpen])

  const handleSave = async () => {
    setIsSaving(true)
    try {
      await saveCategories(draft)
    } finally {
      setIsSaving(false)
    }
  }

  const handleAcceptAll = async () => {
    setIsSaving(true)
    try {
      await acceptAll()
    } finally {
      setIsSaving(false)
    }
  }

  const handleRejectAll = async () => {
    setIsSaving(true)
    try {
      await rejectAll()
    } finally {
      setIsSaving(false)
    }
  }

  if (mode === 'page') {
    return (
      <div className="mx-auto w-full max-w-2xl px-4 py-8">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight">
            Cookie preferences
          </h1>
          <p className="text-sm text-muted-foreground mt-2">
            Choose which categories of cookies and similar storage Sterna
            may use. Essential storage is always required for sign-in and core
            site function.
          </p>
        </header>
        <ConsentBody
          draft={draft}
          setDraft={setDraft}
          onSave={handleSave}
          onAcceptAll={handleAcceptAll}
          onRejectAll={handleRejectAll}
          isSaving={isSaving}
          mode="page"
        />
      </div>
    )
  }

  return (
    <Dialog
      open={isDialogOpen}
      onOpenChange={(open) => {
        if (!open) closeDialog()
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Cookie preferences</DialogTitle>
          <DialogDescription>
            Choose which categories of cookies and similar storage Sterna
            may use.
          </DialogDescription>
        </DialogHeader>
        <ConsentBody
          draft={draft}
          setDraft={setDraft}
          onSave={handleSave}
          onAcceptAll={handleAcceptAll}
          onRejectAll={handleRejectAll}
          onCancel={closeDialog}
          isSaving={isSaving}
          mode="modal"
        />
        <DialogFooter />
      </DialogContent>
    </Dialog>
  )
}
