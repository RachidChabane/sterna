import { createFileRoute, Outlet } from '@tanstack/react-router'
import { MarketingNav } from '@/components/marketing/MarketingNav'
import { MarketingFooter } from '@/components/marketing/MarketingFooter'

export const Route = createFileRoute('/_landing')({
  component: LandingLayout,
})

function LandingLayout() {
  // h-dvh + overflow-y-auto: the global app shell locks html/body/#root
  // (index.css), so marketing pages must be their own scroll container.
  return (
    <div className="h-dvh overflow-y-auto flex flex-col bg-background">
      <MarketingNav />
      <main className="flex-1">
        <Outlet />
      </main>
      <MarketingFooter />
    </div>
  )
}
