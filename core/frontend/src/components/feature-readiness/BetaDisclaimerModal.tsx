import { useCallback } from 'react'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { BetaBadge } from './BetaBadge'
import { SITE_CONFIG } from '@/config/site'

interface BetaDisclaimerModalProps {
  featureName: string
  featureKey: string
  limitations: string[]
  open: boolean
  onContinue: () => void
  onCancel: () => void
}

export function BetaDisclaimerModal({
  featureName,
  featureKey,
  limitations,
  open,
  onContinue,
  onCancel,
}: BetaDisclaimerModalProps) {
  const handleContinue = useCallback(() => {
    // sessionStorage resets each tab/window open — "once per session" means per browser tab
    try {
      sessionStorage.setItem(`betaDisclaimerSeen:${featureKey}`, '1')
    } catch {
      // sessionStorage may throw in test environments or private browsing
    }
    onContinue()
  }, [featureKey, onContinue])

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onCancel() }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2 mb-1">
            <DialogTitle>{featureName} is in Beta</DialogTitle>
            <BetaBadge variant="beta" />
          </div>
          <DialogDescription>
            This feature is functional but still being refined. You may encounter
            occasional failures.
          </DialogDescription>
        </DialogHeader>

        {limitations.length > 0 && (
          <ul className="text-sm text-muted-foreground space-y-1 list-disc list-inside">
            {limitations.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        )}

        <p className="text-sm text-muted-foreground">
          <a
            href={`mailto:${SITE_CONFIG.supportEmail}?subject=Beta+Feedback`}
            className="underline underline-offset-2 hover:text-foreground"
            // TODO Task 24: replace with in-app support form
          >
            Report a problem
          </a>
        </p>

        <div className="flex justify-end gap-2 mt-2">
          <Button variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleContinue}>
            Got it, continue
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** Returns true if the user has already dismissed the disclaimer for this feature this session. */
export function hasBetaDisclaimerBeenSeen(featureKey: string): boolean {
  try {
    return sessionStorage.getItem(`betaDisclaimerSeen:${featureKey}`) === '1'
  } catch {
    return false
  }
}
