import { useState, useCallback } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Zap, Image, Video, Rocket } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { SparksPage } from '@/components/sparks/SparksPage'
import { ImagesGalleryPage } from '@/components/images/ImagesGalleryPage'
import { VideosGalleryPage } from '@/components/videos/VideosGalleryPage'
import { AppsGalleryPage } from '@/components/apps/AppsGalleryPage'
import { useNavigationStore } from '@/store/navigationStore'
import { PremiumMenuIcon } from '@/components/ui/premium-menu-icon'
import { Route } from '@/routes/creations'

type TabValue = 'sparks' | 'images' | 'videos' | 'apps'

const TABS = [
  { value: 'sparks' as const, label: 'Sparks', icon: Zap },
  { value: 'apps' as const, label: 'Apps', icon: Rocket },
  { value: 'images' as const, label: 'Images', icon: Image },
  { value: 'videos' as const, label: 'Videos', icon: Video },
]

export function CreationsPage() {
  const navigate = useNavigate()
  const { openMobileSidebar } = useNavigationStore()
  const { tab } = Route.useSearch()
  const activeTab: TabValue = tab || 'sparks'

  const [visited, setVisited] = useState<Set<TabValue>>(() => new Set([activeTab]))

  const handleTabChange = useCallback((value: string) => {
    const tab = value as TabValue
    setVisited(prev => {
      if (prev.has(tab)) return prev
      return new Set(prev).add(tab)
    })
    navigate({ to: '/creations', search: { tab }, replace: true })
  }, [navigate])

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background">
      <Tabs value={activeTab} onValueChange={handleTabChange} className="flex flex-col h-full">
        {/* Mobile header */}
        <div className="md:hidden flex items-center justify-between px-4 py-3 border-b border-border/50 sticky top-0 z-40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <button
            onClick={openMobileSidebar}
            className="p-2 -ml-2 text-foreground transition-colors"
          >
            <PremiumMenuIcon size={18} />
          </button>
          <h1 className="text-base font-medium text-foreground">Creations</h1>
          <div className="w-8" />
        </div>

        {/* Desktop header with tabs */}
        <div className="hidden md:block sticky top-0 z-30 bg-background border-b border-border/30">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 pt-8 pb-0">
            <div className="flex items-center justify-between gap-4 mb-5">
              <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                Creations
              </h1>
            </div>
            <TabsList className="bg-transparent h-auto rounded-none p-0 gap-1">
              {TABS.map(({ value, label, icon: Icon }) => (
                <TabsTrigger
                  key={value}
                  value={value}
                  className="rounded-none border-b-2 border-transparent px-4 py-2.5 text-sm font-medium data-[state=active]:border-accent-brand data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:text-accent-brand"
                >
                  <Icon className="h-4 w-4 mr-2" />
                  {label}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
        </div>

        {/* Tab content with lazy mount + state preservation */}
        <div className="flex-1 overflow-hidden">
          {visited.has('sparks') && (
            <TabsContent value="sparks" forceMount className={cn("h-full mt-0", activeTab !== 'sparks' && "hidden")}>
              <SparksPage embedded />
            </TabsContent>
          )}
          {visited.has('images') && (
            <TabsContent value="images" forceMount className={cn("h-full mt-0", activeTab !== 'images' && "hidden")}>
              <ImagesGalleryPage embedded />
            </TabsContent>
          )}
          {visited.has('apps') && (
            <TabsContent value="apps" forceMount className={cn("h-full mt-0", activeTab !== 'apps' && "hidden")}>
              <AppsGalleryPage embedded />
            </TabsContent>
          )}
          {visited.has('videos') && (
            <TabsContent value="videos" forceMount className={cn("h-full mt-0", activeTab !== 'videos' && "hidden")}>
              <VideosGalleryPage embedded />
            </TabsContent>
          )}
        </div>

        {/* Mobile Bottom Navigation */}
        <div className="md:hidden fixed bottom-0 left-0 right-0 z-20 bg-background/95 backdrop-blur-xl border-t border-border/50 safe-area-bottom">
          <div className="flex items-center">
            {TABS.map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                onClick={() => handleTabChange(value)}
                className={cn(
                  "flex-1 flex flex-col items-center gap-1 py-3 transition-colors",
                  activeTab === value
                    ? "text-accent-brand"
                    : "text-muted-foreground"
                )}
              >
                <Icon className="w-5 h-5" />
                <span className="text-xs font-medium">{label}</span>
              </button>
            ))}
          </div>
        </div>
      </Tabs>
    </div>
  )
}

export default CreationsPage
