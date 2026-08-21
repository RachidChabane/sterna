import { createRootRoute, Outlet, useRouterState } from '@tanstack/react-router'
import { Toaster } from 'sonner'
import { Sidebar } from '@/components/layout/Sidebar'
import { useAuthInit } from '@/hooks/useAuthInit'
import { NotFound } from '@/components/errors/NotFound'
import { GlobalCommandPalette } from '@/components/command-palette/GlobalCommandPalette'
import { setupCommandProviders } from '@/components/command-palette/providers'
import { AuthModal } from '@/components/auth/AuthModal'
import { EmailVerificationBanner } from '@/components/auth/EmailVerificationBanner'
import { VerificationGateModal } from '@/components/auth/VerificationGateModal'
import { PullToRefresh } from '@/components/ui/pull-to-refresh'
import { useEffect, useCallback, lazy, Suspense } from 'react'
import { useMediaQuery } from '@/hooks/useMediaQuery'
import { useSettingsEffects } from '@/hooks/useSettingsEffects'
import { useDataPrefetch } from '@/hooks/useDataPrefetch'
import { useUIStore } from '@/store/uiStore'
import { CookieBanner } from '@/components/consent/CookieBanner'
import { TooltipProvider } from '@/components/ui/tooltip'

// SettingsModal pulls in react-syntax-highlighter's full Prism/refractor
// language set (for the code-theme preview swatches) — a ~634KB chunk, the
// largest single dependency in the app. __root.tsx renders on every route,
// so a static import here would ship that weight on every page load
// whether or not Settings is ever opened. Split into its own chunk instead.
//
// Both this and HelpDrawer below stay unconditionally mounted here (as they
// were before) and manage their own open/closed state internally — gating
// the mount itself on that same state would unmount the dialog the instant
// it closes, before Radix's own close animation (data-[state=closed]
// animate-out) gets to play, which would be a visible regression.
// `fallback={null}` mirrors the closed dialog's existing "renders nothing"
// state, so no fallback UI flashes on pages where it's never opened.
const SettingsModal = lazy(() =>
  import('@/components/settings/SettingsModal').then((module) => ({
    default: module.SettingsModal,
  })),
)

// HelpDrawer statically imports react-markdown + remark-gfm to render FAQ
// articles — a ~200KB dependency chain that every page paid for even though
// the drawer is closed by default everywhere.
const HelpDrawer = lazy(() =>
  import('@/components/support/HelpDrawer').then((module) => ({
    default: module.HelpDrawer,
  })),
)

const MARKETING_PATHS = new Set(['/', '/pricing'])
const LEGAL_PREFIX = '/legal/'

function RootComponent() {
  useAuthInit()
  useSettingsEffects()
  useDataPrefetch()

  useEffect(() => {
    setupCommandProviders()
  }, [])

  const isMobile = useMediaQuery('(max-width: 767px)')
  const setMobile = useUIStore((state) => state.setMobile)

  useEffect(() => {
    setMobile(isMobile)
  }, [isMobile, setMobile])

  const handleRefresh = useCallback(async () => {
    window.location.reload()
  }, [])

  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const isMarketing = MARKETING_PATHS.has(pathname) || pathname.startsWith(LEGAL_PREFIX)

  if (isMarketing) {
    return (
      <TooltipProvider>
        <Outlet />
        <CookieBanner />
        <Toaster
          position="top-right"
          closeButton
          expand={false}
          duration={4000}
          gap={12}
          toastOptions={{
            style: {
              background: 'transparent',
            },
          }}
        />
      </TooltipProvider>
    )
  }

  return (
    <TooltipProvider>
      <div className="flex h-dvh bg-background overflow-hidden">
        <Sidebar />
        <div className="flex-1 flex flex-col overflow-hidden">
          <EmailVerificationBanner />
          {/* Mobile: pull-to-refresh with bottom nav padding */}
          {/* Desktop: simple overflow-auto main */}
          {isMobile ? (
            <PullToRefresh
              onRefresh={handleRefresh}
              className="flex-1 overscroll-bounce overflow-auto"
              style={{
                paddingTop: 'var(--safe-area-inset-top, 0px)',
              }}
            >
              <Outlet />
            </PullToRefresh>
          ) : (
            <main className="flex-1 overflow-auto">
              <Outlet />
            </main>
          )}
        </div>
      </div>
      <GlobalCommandPalette />
      <Suspense fallback={null}>
        <HelpDrawer />
      </Suspense>
      <CookieBanner />
      <AuthModal />
      <VerificationGateModal />
      <Suspense fallback={null}>
        <SettingsModal />
      </Suspense>
      <Toaster
        position="top-right"
        closeButton
        expand={false}
        duration={4000}
        gap={12}
        toastOptions={{
          style: {
            background: 'transparent',
          },
        }}
      />
    </TooltipProvider>
  )
}

export const Route = createRootRoute({
  component: RootComponent,
  notFoundComponent: NotFound,
})