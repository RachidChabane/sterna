/**
 * PreconfiguredServersList Component
 *
 * Displays a compact, categorized list of preconfigured MCP servers.
 * Premium design with category pills, icon cards, and smooth interactions.
 */

import { useState, useEffect, useMemo, useCallback } from 'react'
import {
  Globe,
  Search,
  Loader2,
  Plus,
  Check,
  Briefcase,
  Code2,
  Cloud,
  Users,
  DollarSign,
  Brain,
  Database,
  Lock,
  Key,
  Shield,
  Sparkles,
  MessageSquare,
  Workflow,
  Palette,
  ShoppingCart,
  Wrench,
  MapPin,
  Zap,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { toast } from 'sonner'
import { mcpApi, type MCPPreconfiguredServer, type MCPServerCategory } from '@/api/mcp'
import { cn } from '@/lib/utils'
import { useThemeStore } from '@/store/themeStore'
import { ServerDetailModal } from './ServerDetailModal'


interface PreconfiguredServersListProps {
  onServerConnect?: (server: MCPPreconfiguredServer) => void
  connectedServerIds?: string[]
  highlightServerName?: string | null  // Auto-open modal for this server
  onAIDiscover?: () => void  // Open AI discovery dialog
  initialSearchQuery?: string  // Pre-fill search from URL
}

// Category configuration with icons and display order
const CATEGORY_CONFIG: Record<MCPServerCategory, {
  label: string
  icon: typeof Briefcase
  order: number
}> = {
  productivity: { label: 'Productivity', icon: Briefcase, order: 1 },
  communication: { label: 'Communication', icon: MessageSquare, order: 2 },
  developer: { label: 'Developer', icon: Code2, order: 3 },
  automation: { label: 'Automation', icon: Workflow, order: 4 },
  cloud: { label: 'Cloud', icon: Cloud, order: 5 },
  data: { label: 'Data', icon: Database, order: 6 },
  crm: { label: 'CRM', icon: Users, order: 7 },
  finance: { label: 'Finance', icon: DollarSign, order: 8 },
  ai: { label: 'AI', icon: Brain, order: 9 },
  design: { label: 'Design', icon: Palette, order: 10 },
  ecommerce: { label: 'E-commerce', icon: ShoppingCart, order: 11 },
  utilities: { label: 'Utilities', icon: Wrench, order: 12 },
}

export function PreconfiguredServersList({
  onServerConnect,
  connectedServerIds = [],
  highlightServerName,
  onAIDiscover,
  initialSearchQuery = '',
}: PreconfiguredServersListProps) {
  const theme = useThemeStore((state) => state.theme)
  const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)

  const [servers, setServers] = useState<MCPPreconfiguredServer[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState(initialSearchQuery)
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [failedIcons, setFailedIcons] = useState<Set<string>>(new Set())
  const [selectedServer, setSelectedServer] = useState<MCPPreconfiguredServer | null>(null)
  const [activeCategory, setActiveCategory] = useState<MCPServerCategory | null>(null)
  const [showOfficialOnly, setShowOfficialOnly] = useState(false)
  const [showInstantOnly, setShowInstantOnly] = useState(false)

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  // Fetch all servers
  useEffect(() => {
    fetchServers()
  }, [])

  // Auto-open modal when highlightServerName is provided
  useEffect(() => {
    if (highlightServerName && servers.length > 0 && !selectedServer) {
      const matchingServer = servers.find(
        s => s.name.toLowerCase() === highlightServerName.toLowerCase()
      )
      if (matchingServer) {
        setSelectedServer(matchingServer)
        // Also switch to the matching category
        if (matchingServer.category) {
          setActiveCategory(matchingServer.category)
        }
      }
    }
  }, [highlightServerName, servers])

  const fetchServers = async () => {
    try {
      setIsLoading(true)
      const response = await mcpApi.listPreconfiguredServers({
        page: 1,
        page_size: 200, // Get all
      })
      setServers(response.data.results)
    } catch (error) {
      console.error('Failed to fetch preconfigured servers:', error)
      toast.error('Failed to load available servers')
    } finally {
      setIsLoading(false)
    }
  }

  // Filter and group servers by category
  const { groupedServers, categories } = useMemo(() => {
    let filtered = servers

    // Filter by official status
    if (showOfficialOnly) {
      filtered = filtered.filter((s) => s.is_official !== false)
    }

    // Filter by instant connect (OAuth only - no config needed)
    if (showInstantOnly) {
      filtered = filtered.filter((s) => s.auth_type === 'oauth')
    }

    // Filter by search query
    if (debouncedSearch) {
      filtered = filtered.filter(
        (s) =>
          s.name.toLowerCase().includes(debouncedSearch.toLowerCase()) ||
          s.description.toLowerCase().includes(debouncedSearch.toLowerCase())
      )
    }

    const groups: Record<MCPServerCategory, MCPPreconfiguredServer[]> = {
      productivity: [], communication: [], developer: [], automation: [],
      cloud: [], data: [], crm: [], finance: [],
      ai: [], design: [], ecommerce: [], utilities: [],
    }

    filtered.forEach((server) => {
      const category = server.category || 'utilities'
      groups[category]?.push(server) || groups.utilities.push(server)
    })

    const sortedCategories = (Object.entries(groups) as [MCPServerCategory, MCPPreconfiguredServer[]][])
      .filter(([_, servers]) => servers.length > 0)
      .sort(([a], [b]) => (CATEGORY_CONFIG[a]?.order ?? 99) - (CATEGORY_CONFIG[b]?.order ?? 99))

    return { groupedServers: groups, categories: sortedCategories }
  }, [servers, debouncedSearch, showOfficialOnly, showInstantOnly])

  // Auto-select first category, or switch if current category has no results
  useEffect(() => {
    if (categories.length === 0) return

    // If no active category, select the first one
    if (!activeCategory) {
      setActiveCategory(categories[0][0])
      return
    }

    // If active category has no results (not in the filtered categories), switch to first available
    const activeCategoryHasResults = categories.some(([cat]) => cat === activeCategory)
    if (!activeCategoryHasResults) {
      setActiveCategory(categories[0][0])
    }
  }, [categories, activeCategory])

  const activeServers = activeCategory ? groupedServers[activeCategory] : []

  const handleConnect = (server: MCPPreconfiguredServer) => {
    if (onServerConnect) {
      onServerConnect(server)
    }
  }

  const isConnected = (serverId: string) => connectedServerIds.includes(serverId)

  const handleIconError = (serverId: string) => {
    setFailedIcons((prev) => new Set(prev).add(serverId))
  }

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-4">
        <div className="relative">
          <div className="w-10 h-10 rounded-full border-2 border-accent-brand/20 border-t-accent-brand animate-spin" />
        </div>
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Search & Filters — sticky on mobile, absorbs parent py-6/sm:py-8 padding */}
      <div className="space-y-3 sticky top-0 z-20 bg-background -mt-6 pt-6 sm:-mt-8 sm:pt-8 pb-1 md:static md:mt-0 md:pt-0 md:pb-0">
        {/* Row 1: Search + AI Search */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/60" />
            <Input
              placeholder="Search connectors..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 h-9 bg-muted/20 border-border/40 text-sm placeholder:text-muted-foreground/50 focus-visible:ring-accent-brand/30"
            />
          </div>
          {onAIDiscover && (
            <Button
              variant="outline"
              size="sm"
              onClick={onAIDiscover}
              className="h-9 px-3 gap-1.5 text-xs font-medium border-accent-brand/30 text-accent-brand hover:bg-accent-brand/10 hover:text-accent-brand"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">AI Search</span>
            </Button>
          )}
        </div>

        {/* Row 2: Filter toggles */}
        <div className="flex items-center gap-3">
          <span className="text-xs text-muted-foreground">Filter:</span>
          <TooltipProvider delayDuration={300}>
            <div className="flex items-center gap-2">
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => setShowInstantOnly(!showInstantOnly)}
                    className={cn(
                      "flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium whitespace-nowrap transition-all border",
                      showInstantOnly
                        ? "bg-purple-500/15 text-purple-400 border-purple-500/30"
                        : "text-muted-foreground border-border/50 hover:bg-muted/40 hover:text-foreground hover:border-border"
                    )}
                  >
                    <Zap className="w-3 h-3" />
                    Instant
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="max-w-[200px]">
                  <p className="text-xs">Connect with one click — no API keys or configuration needed</p>
                </TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => setShowOfficialOnly(!showOfficialOnly)}
                    className={cn(
                      "flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium whitespace-nowrap transition-all border",
                      showOfficialOnly
                        ? "bg-purple-500/15 text-purple-400 border-purple-500/30"
                        : "text-muted-foreground border-border/50 hover:bg-muted/40 hover:text-foreground hover:border-border"
                    )}
                  >
                    <Shield className="w-3 h-3" />
                    Official
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom" className="max-w-[200px]">
                  <p className="text-xs">Servers maintained by the service provider</p>
                </TooltipContent>
              </Tooltip>
            </div>
          </TooltipProvider>
        </div>

        {/* Row 3: Category Pills - scrollable on both mobile and desktop */}
        <div className="relative">
          {/* Fade indicator on right edge when scrollable (desktop only) */}
          <div className="absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-background to-transparent pointer-events-none z-10 hidden md:block" />
          <div className="flex items-center gap-2 overflow-x-auto scrollbar-none-mobile pb-1">
          {categories.map(([category, categoryServers]) => {
            const config = CATEGORY_CONFIG[category]
            const CategoryIcon = config.icon
            const isActive = activeCategory === category

            return (
              <button
                key={category}
                onClick={() => setActiveCategory(category)}
                className={cn(
                  "flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-all",
                  isActive
                    ? "bg-accent-brand/15 text-accent-brand"
                    : "text-muted-foreground hover:bg-muted/40 hover:text-foreground"
                )}
              >
                <CategoryIcon className="w-3.5 h-3.5" />
                {config.label}
                <span className={cn(
                  "text-[10px] px-1.5 py-0.5 rounded-full font-semibold",
                  isActive ? "bg-accent-brand/20" : "bg-muted/60"
                )}>
                  {categoryServers.length}
                </span>
              </button>
            )
          })}
          </div>
        </div>
      </div>

      {/* Server Grid */}
      {activeServers.length === 0 ? (
        <div className="text-center py-12 text-sm text-muted-foreground">
          {debouncedSearch ? 'No connectors match your search' : 'No connectors in this category'}
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
          {activeServers.map((server, index) => {
            const connected = isConnected(server.id)
            const showFallback = !server.icon_url || failedIcons.has(server.id)
            const requiresAuth = server.requires_auth

            return (
              <div
                key={server.id}
                onClick={() => setSelectedServer(server)}
                className={cn(
                  "group relative flex flex-col items-center p-4 rounded-xl border cursor-pointer transition-colors",
                  "bg-card/30 border-border/40",
                  "hover:bg-card/50 hover:border-border/60",
                  connected && "ring-1 ring-accent-brand/40 bg-accent-brand/5"
                )}
              >
                {/* Icon container with subtle gradient */}
                <div className="relative w-12 h-12 mb-3 rounded-xl bg-gradient-to-br from-muted/40 to-muted/20 flex items-center justify-center">
                  {showFallback ? (
                    <Globe className="w-6 h-6 text-muted-foreground/50" />
                  ) : (
                    <img
                      src={server.icon_url}
                      alt=""
                      className={cn(
                        "w-6 h-6 object-contain",
                        isDark && server.icon_invert_in_dark_mode && "invert"
                      )}
                      onError={() => handleIconError(server.id)}
                    />
                  )}

                  {/* Auth indicator */}
                  {requiresAuth && (
                    <div className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-background border border-border/50 flex items-center justify-center">
                      {server.auth_type === 'oauth' ? (
                        <Lock className="w-2.5 h-2.5 text-amber-500" />
                      ) : (
                        <Key className="w-2.5 h-2.5 text-amber-500" />
                      )}
                    </div>
                  )}
                </div>

                {/* Name */}
                <h3 className="text-xs font-medium text-center text-foreground line-clamp-2 leading-tight min-h-[2rem]">
                  {server.name}
                </h3>

                {/* Community badge - top left corner */}
                {server.is_official === false && (
                  <div className="absolute top-1.5 left-1.5 px-1 py-0.5 rounded text-[8px] font-medium bg-amber-500/10 text-amber-600/70 dark:text-amber-400/70">
                    Community
                  </div>
                )}

                {/* Hover overlay */}
                <div className={cn(
                  "absolute inset-0 flex items-center justify-center rounded-xl bg-background/95 backdrop-blur-sm opacity-0 transition-opacity pointer-events-none",
                  "group-hover:opacity-100"
                )}>
                  {connected ? (
                    <div className="flex items-center gap-1.5 text-xs text-accent-brand px-3 py-1.5 rounded-md bg-accent-brand/10">
                      <Check className="w-3 h-3" />
                      <span className="font-medium">Connected</span>
                    </div>
                  ) : (
                    <Button
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleConnect(server)
                      }}
                      className="h-8 text-xs font-medium pointer-events-auto shadow-sm bg-accent-brand hover:bg-accent-brand/90 text-white"
                    >
                      <Plus className="w-3 h-3 mr-1.5" />
                      Connect
                    </Button>
                  )}
                </div>

                {/* Connected indicator */}
                {connected && (
                  <div className="absolute top-2 right-2 w-2 h-2 rounded-full bg-accent-brand shadow-sm shadow-accent-brand/50" />
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Detail Modal */}
      <ServerDetailModal
        isOpen={!!selectedServer}
        onClose={() => setSelectedServer(null)}
        server={selectedServer}
        onConnect={handleConnect}
        isConnected={selectedServer ? isConnected(selectedServer.id) : false}
      />
    </div>
  )
}
