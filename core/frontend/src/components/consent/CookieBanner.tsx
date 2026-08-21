import { useEffect } from 'react'
import { Link } from '@tanstack/react-router'

import { Button } from '@/components/ui/button'
import { useConsentStore } from '@/store/consentStore'

import { ConsentSettingsDialog } from './ConsentSettingsDialog'

export function CookieBanner() {
  const initialize = useConsentStore((s) => s.initialize)
  const isBannerOpen = useConsentStore((s) => s.isBannerOpen)
  const openDialog = useConsentStore((s) => s.openDialog)
  const acceptAll = useConsentStore((s) => s.acceptAll)
  const rejectAll = useConsentStore((s) => s.rejectAll)

  useEffect(() => {
    void initialize()
  }, [initialize])

  return (
    <>
      <ConsentSettingsDialog mode="modal" />
      {isBannerOpen ? (
        <aside
          role="region"
          aria-label="Cookie consent"
          tabIndex={0}
          className="fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80 shadow-lg"
        >
          <div className="mx-auto max-w-5xl px-4 py-4 sm:py-5">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div className="text-sm text-foreground/90 leading-relaxed max-w-2xl">
                <p>
                  Sterna uses essential cookies to keep you signed in. With
                  your permission, we'd also like to use analytics to
                  understand how the product is used. You can change this any
                  time at{' '}
                  <Link
                    to="/settings/privacy"
                    className="underline underline-offset-2 hover:text-foreground"
                  >
                    /settings/privacy
                  </Link>
                  .{' '}
                  <Link
                    to="/legal/cookies"
                    className="underline underline-offset-2 hover:text-foreground"
                  >
                    Read our Cookie Policy
                  </Link>
                  .
                </p>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-2 md:flex-shrink-0">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={openDialog}
                  aria-label="Customize cookie preferences"
                >
                  Customize
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void rejectAll()}
                  aria-label="Reject non-essential cookies"
                >
                  Reject all
                </Button>
                <Button
                  type="button"
                  size="sm"
                  onClick={() => void acceptAll()}
                  aria-label="Accept all cookies"
                >
                  Accept all
                </Button>
              </div>
            </div>
          </div>
        </aside>
      ) : null}
    </>
  )
}
