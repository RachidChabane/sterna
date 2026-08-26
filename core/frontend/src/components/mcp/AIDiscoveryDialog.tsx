/**
 * AIDiscoveryDialog Component
 *
 * AI-powered MCP server discovery dialog.
 * User describes what they want, AI searches and recommends MCP servers.
 * Shows preconfigured servers first, then external ones from web search.
 * Search history is persisted in the database.
 */

import { useState, useEffect, useRef } from 'react'
import { Loader2, Package, Globe, ExternalLink, Check, Search, Star, History, X } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { useMediaQuery } from '@/hooks/use-media-query'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'
import { mcpApi, type MCPDiscoveredServer, type MCPDiscoveryHistoryEntry } from '@/api/mcp'
import { getApiErrorMessage } from '@/utils/errorMessages'
import { cn } from '@/lib/utils'

interface AIDiscoveryDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onServerSelected: (server: MCPDiscoveredServer) => void
}

export function AIDiscoveryDialog({
  open,
  onOpenChange,
  onServerSelected,
}: AIDiscoveryDialogProps) {
  const [query, setQuery] = useState('')
  const [isSearching, setIsSearching] = useState(false)
  const [preconfiguredResults, setPreconfiguredResults] = useState<MCPDiscoveredServer[]>([])
  const [externalResults, setExternalResults] = useState<MCPDiscoveredServer[]>([])
  const [hasSearched, setHasSearched] = useState(false)
  const [searchHistory, setSearchHistory] = useState<MCPDiscoveryHistoryEntry[]>([])
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const isMobile = useMediaQuery('(max-width: 640px)')

  // Fetch search history when dialog opens
  useEffect(() => {
    if (open) {
      fetchHistory()
    }
  }, [open])

  const fetchHistory = async () => {
    setIsLoadingHistory(true)
    try {
      const response = await mcpApi.getDiscoveryHistory()
      setSearchHistory(response.data)
    } catch (error) {
      console.error('Failed to fetch discovery history:', error)
    } finally {
      setIsLoadingHistory(false)
    }
  }

  const handleSearch = async () => {
    if (!query.trim()) {
      toast.error('Please describe what you want to do')
      return
    }

    setIsSearching(true)
    setHasSearched(true)

    try {
      const response = await mcpApi.aiDiscover(query.trim())
      setPreconfiguredResults(response.data.preconfigured)
      setExternalResults(response.data.external)

      const totalCount = response.data.preconfigured_count + response.data.external_count
      if (totalCount === 0) {
        toast.info('No MCP servers found. Try a different description.')
      }

      // Refresh history (new search was saved by backend)
      fetchHistory()
    } catch (error) {
      console.error('AI discovery failed:', error)
      const errorMsg = getApiErrorMessage(error, 'Discovery failed')
      toast.error(errorMsg)
      setPreconfiguredResults([])
      setExternalResults([])
    } finally {
      setIsSearching(false)
    }
  }

  const handleSelectHistory = (entry: MCPDiscoveryHistoryEntry) => {
    setQuery(entry.query)
    setPreconfiguredResults(entry.preconfigured_results)
    setExternalResults(entry.external_results)
    setHasSearched(true)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isSearching) {
      handleSearch()
    }
  }

  const handleSelectServer = (server: MCPDiscoveredServer) => {
    onServerSelected(server)
    onOpenChange(false)
  }

  const handleClose = () => {
    setQuery('')
    setPreconfiguredResults([])
    setExternalResults([])
    setHasSearched(false)
    onOpenChange(false)
  }

  const handleNewSearch = () => {
    setQuery('')
    setPreconfiguredResults([])
    setExternalResults([])
    setHasSearched(false)
  }

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return 'text-green-500'
    if (confidence >= 0.5) return 'text-yellow-500'
    return 'text-muted-foreground'
  }

  const totalResults = preconfiguredResults.length + externalResults.length

  const renderServerCard = (server: MCPDiscoveredServer, index: number, isPreconfigured: boolean) => (
    <div
      key={`${isPreconfigured ? 'pre' : 'ext'}-${index}`}
      className={cn(
        "border rounded-lg p-4 hover:border-accent-brand/50 hover:bg-muted/30 transition-colors cursor-pointer group",
        isPreconfigured ? "border-accent-brand/30 bg-accent-brand/5" : "border-border"
      )}
      onClick={() => handleSelectServer(server)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            {server.icon_url ? (
              <img
                src={server.icon_url}
                alt=""
                className={cn(
                  "h-4 w-4 shrink-0 object-contain",
                  server.icon_invert_in_dark_mode && "dark:invert"
                )}
              />
            ) : server.server_type === 'local' ? (
              <Package className="h-4 w-4 text-muted-foreground shrink-0" />
            ) : (
              <Globe className="h-4 w-4 text-muted-foreground shrink-0" />
            )}
            <h4 className="font-medium truncate">{server.name}</h4>
            <span className={cn('text-xs', getConfidenceColor(server.confidence))}>
              {Math.round(server.confidence * 100)}% match
            </span>
          </div>
          <p className="text-sm text-muted-foreground line-clamp-2">
            {server.description}
          </p>
          <div className="flex flex-wrap items-center gap-2 mt-2">
            {server.npm_package && (
              <code className="text-xs bg-muted px-1.5 py-0.5 rounded font-mono">
                {server.npm_package}
              </code>
            )}
            {server.remote_url && (
              <code className="text-xs bg-muted px-1.5 py-0.5 rounded font-mono truncate max-w-[200px]">
                {server.remote_url}
              </code>
            )}
            <Badge variant="outline" className="text-xs">
              {server.server_type === 'local' ? 'Local' : 'Remote'}
            </Badge>
            {server.auth_type !== 'none' && (
              <Badge variant="outline" className="text-xs">
                {server.auth_type === 'api_key' ? 'API Key' :
                 server.auth_type === 'bearer' ? 'Bearer' :
                 server.auth_type === 'oauth' ? 'OAuth' : server.auth_type}
              </Badge>
            )}
          </div>
        </div>
        <Button
          size="sm"
          variant="ghost"
          className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <Check className="h-4 w-4 mr-1" />
          Select
        </Button>
      </div>
      {server.source_url && !isPreconfigured && (
        <a
          href={server.source_url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="inline-flex items-center gap-1 text-xs text-accent-brand hover:underline mt-2"
        >
          <ExternalLink className="h-3 w-3" />
          View source
        </a>
      )}
    </div>
  )

  const contentBody = (
    <>

        {/* Search Input */}
        <div className="flex gap-2 mt-2">
          <Input
            ref={inputRef}
            placeholder="I want to manage my GitHub repositories..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isSearching}
            className="flex-1"
            autoFocus
          />
          <Button
            onClick={handleSearch}
            disabled={isSearching || !query.trim()}
            className="shrink-0"
            size={isMobile ? "icon" : "default"}
          >
            {isSearching ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            <span className="ml-2 hidden md:inline">Search</span>
          </Button>
        </div>

        {/* Search History or Example queries */}
        {!hasSearched && !isSearching && (
          <div className="mt-2">
            {isLoadingHistory ? (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                Loading history...
              </div>
            ) : searchHistory.length > 0 ? (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <History className="h-3.5 w-3.5 text-muted-foreground" />
                  <p className="text-xs text-muted-foreground">Recent searches</p>
                </div>
                <div className="space-y-1.5 max-h-48 overflow-y-auto">
                  {searchHistory.slice(0, 5).map((entry) => (
                    <button
                      key={entry.id}
                      onClick={() => handleSelectHistory(entry)}
                      className="w-full flex items-center justify-between gap-2 px-3 py-2 rounded-md bg-muted/50 hover:bg-muted text-left transition-colors group"
                    >
                      <span className="text-sm truncate">{entry.query}</span>
                      <span className="text-xs text-muted-foreground shrink-0">
                        {entry.total_results} result{entry.total_results !== 1 ? 's' : ''}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <>
                <p className="text-xs text-muted-foreground mb-2">Try these examples:</p>
                <div className="flex flex-wrap gap-2">
                  {[
                    'Connect to GitHub',
                    'Manage Slack messages',
                    'Search with Brave',
                    'Access Google Drive',
                    'Query PostgreSQL database',
                  ].map((example) => (
                    <button
                      key={example}
                      onClick={() => setQuery(example)}
                      className="text-xs px-2 py-1 rounded-md bg-muted hover:bg-muted/80 transition-colors"
                    >
                      {example}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {/* Loading State */}
        {isSearching && (
          <div className="flex-1 flex flex-col items-center justify-center py-12 gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-accent-brand" />
            <p className="text-sm text-muted-foreground">
              Searching for MCP servers...
            </p>
          </div>
        )}

        {/* Results */}
        {!isSearching && hasSearched && (
          <div className="flex-1 overflow-y-auto mt-4 space-y-4">
            {/* Back to search / New search */}
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground">
                Results for "<span className="font-medium text-foreground">{query}</span>"
              </p>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleNewSearch}
                className="h-7 text-xs gap-1"
              >
                <X className="h-3 w-3" />
                New Search
              </Button>
            </div>

            {totalResults === 0 ? (
              <div className="text-center py-12">
                <p className="text-muted-foreground">
                  No MCP servers found for your query.
                </p>
                <p className="text-sm text-muted-foreground mt-1">
                  Try describing what service you want to connect to.
                </p>
              </div>
            ) : (
              <>
                {/* Preconfigured Servers Section */}
                {preconfiguredResults.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <Star className="h-4 w-4 text-accent-brand" />
                      <h3 className="text-sm font-medium">From Our Catalog</h3>
                      <span className="text-xs text-muted-foreground">
                        ({preconfiguredResults.length} found)
                      </span>
                    </div>
                    {preconfiguredResults.map((server, index) =>
                      renderServerCard(server, index, true)
                    )}
                  </div>
                )}

                {/* External Servers Section */}
                {externalResults.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <Globe className="h-4 w-4 text-muted-foreground" />
                      <h3 className="text-sm font-medium">From the Web</h3>
                      <span className="text-xs text-muted-foreground">
                        ({externalResults.length} found)
                      </span>
                    </div>
                    {externalResults.map((server, index) =>
                      renderServerCard(server, index, false)
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        )}
    </>
  )

  if (isMobile) {
    return (
      <Sheet open={open} onOpenChange={handleClose}>
        <SheetContent side="bottom" className="h-[85vh] rounded-t-2xl p-0 flex flex-col [&>button]:hidden">
          <SheetHeader className="shrink-0 px-4 pt-4 pb-3 border-b border-border/30">
            <SheetTitle className="flex items-center gap-2">
              Discover MCP Servers with AI
            </SheetTitle>
          </SheetHeader>
          <div className="flex-1 overflow-hidden flex flex-col px-4 pt-3 pb-4">
            {contentBody}
          </div>
        </SheetContent>
      </Sheet>
    )
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent
        className="max-w-2xl overflow-hidden flex flex-col"
        style={{ maxHeight: '85vh' }}
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            Discover MCP Servers with AI
          </DialogTitle>
          <DialogDescription className="hidden md:block">
            Describe what you want to do, and AI will find the right MCP servers for you.
          </DialogDescription>
        </DialogHeader>
        {contentBody}
      </DialogContent>
    </Dialog>
  )
}
