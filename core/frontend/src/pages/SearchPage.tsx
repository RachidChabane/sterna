/**
 * Find in Chats Page
 *
 * Full-text search across all chat messages with premium UI.
 * Accessible via command palette (Cmd+K) - not in sidebar navigation.
 */

import { useState, useEffect, useMemo } from 'react'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { Loader2, ArrowLeft, User, MessagesSquare, Search, Bot } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { CachedAvatar } from '@/components/ui/CachedAvatar'
import { ModelIcon } from '@/components/models/ModelIcon'
import { conversationsAPI, type SearchResult } from '@/api/conversations'
import { cn } from '@/lib/utils'
import { useDebounce } from '@/hooks/useDebounce'
import useModelStore from '@/store/modelStore'
import { useAuthStore } from '@/store/authStore'

// Helper to format relative date
function formatRelativeDate(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) {
    return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  }
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays}d ago`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// Highlight matching text in snippet
function HighlightedSnippet({ text, query }: { text: string; query: string }) {
  if (!query.trim()) return <span>{text}</span>

  // Split text by query matches and render with highlights
  const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(`(${escapedQuery})`, 'gi')
  const parts = text.split(regex)

  return (
    <span>
      {parts.map((part, i) =>
        regex.test(part) ? (
          <mark key={i} className="bg-accent-brand/30 text-foreground rounded px-0.5">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </span>
  )
}

export function SearchPage() {
  const navigate = useNavigate()
  const { q: initialQuery } = useSearch({ from: '/search' })
  const { allModels, allModelsLoaded, fetchAllModels } = useModelStore()
  const user = useAuthStore((state) => state.user)

  const [query, setQuery] = useState(initialQuery || '')
  const [results, setResults] = useState<SearchResult[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [totalCount, setTotalCount] = useState(0)
  const [page, setPage] = useState(1)
  const [hasSearched, setHasSearched] = useState(false)

  const debouncedQuery = useDebounce(query, 300)

  // Ensure all models are loaded for icon lookup
  useEffect(() => {
    if (!allModelsLoaded) {
      fetchAllModels()
    }
  }, [allModelsLoaded, fetchAllModels])

  // Create model lookup map for icons
  const modelLookup = useMemo(() => {
    const map = new Map<string, typeof allModels[0]>()
    allModels.forEach(m => {
      // Store by model_id (which already includes provider prefix like "google/gemini-2.0-flash-001")
      map.set(m.model_id, m)
    })
    return map
  }, [allModels])

  // Get model info for display
  const getModelInfo = (modelId: string | null) => {
    if (!modelId) return null
    return modelLookup.get(modelId)
  }

  // Search when query changes
  useEffect(() => {
    if (!debouncedQuery.trim()) {
      setResults([])
      setTotalCount(0)
      setHasSearched(false)
      return
    }

    const search = async () => {
      setIsLoading(true)
      setHasSearched(true)
      try {
        const response = await conversationsAPI.searchConversations(debouncedQuery, page)
        if (page === 1) {
          setResults(response.results)
        } else {
          setResults(prev => [...prev, ...response.results])
        }
        setTotalCount(response.count)
      } catch (error) {
        console.error('Search failed:', error)
      } finally {
        setIsLoading(false)
      }
    }

    search()
  }, [debouncedQuery, page])

  // Reset page when query changes
  useEffect(() => {
    setPage(1)
  }, [debouncedQuery])

  // Update URL with query
  useEffect(() => {
    if (query !== initialQuery) {
      navigate({ to: '/search', search: { q: query || undefined }, replace: true })
    }
  }, [query, initialQuery, navigate])

  const handleResultClick = (conversationId: string) => {
    navigate({ to: '/chats', search: { conversation: conversationId } })
  }

  const handleLoadMore = () => {
    setPage(p => p + 1)
  }

  return (
    <div className="flex flex-col h-full bg-background">
      {/* Premium Header with glass effect */}
      <div className="flex-shrink-0 border-b border-border/50 bg-card/80 backdrop-blur-xl sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-4">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => navigate({ to: '/chats' })}
              className="flex-shrink-0 hover:bg-accent-brand/10 hover:text-accent-brand transition-colors"
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>

            <div className="flex-1">
              <div className="relative">
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Find in all your chats..."
                  className={cn(
                    "pl-4 pr-4 h-12 text-base bg-background/50 border-border/50",
                    "focus:border-accent-brand/50 focus:ring-accent-brand/20 focus:ring-2",
                    "placeholder:text-muted-foreground/60 transition-all"
                  )}
                  autoFocus
                />
                {isLoading && (
                  <div className="absolute right-4 top-1/2 -translate-y-1/2">
                    <Loader2 className="h-4 w-4 animate-spin text-accent-brand" />
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Results count - subtle */}
          {hasSearched && totalCount > 0 && !isLoading && (
            <p className="text-xs text-muted-foreground mt-3 ml-14">
              {totalCount} {totalCount === 1 ? 'chat' : 'chats'} with matches
            </p>
          )}
        </div>
      </div>

      {/* Results Area */}
      <ScrollArea className="flex-1">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6">
          {/* Initial state - no query */}
          {!hasSearched && !query && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="w-14 h-14 rounded-full bg-muted/50 flex items-center justify-center mb-5">
                <Search className="h-6 w-6 text-muted-foreground" />
              </div>
              <h2 className="text-xl font-semibold text-foreground mb-2">Find in your chats</h2>
              <p className="text-sm text-muted-foreground max-w-md leading-relaxed">
                Search through all your message history. Results show the matching text with context.
              </p>
              <p className="text-xs text-muted-foreground/60 mt-4">
                Tip: Use <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px] font-mono">⌘K</kbd> anytime to quickly access this
              </p>
            </div>
          )}

          {/* Loading state - first page */}
          {isLoading && page === 1 && (
            <div className="flex flex-col items-center justify-center py-16">
              <Loader2 className="h-8 w-8 animate-spin text-accent-brand mb-4" />
              <p className="text-sm text-muted-foreground">Searching your chats...</p>
            </div>
          )}

          {/* No results state */}
          {hasSearched && !isLoading && results.length === 0 && query && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="w-14 h-14 rounded-full bg-muted/50 flex items-center justify-center mb-4">
                <MessagesSquare className="h-6 w-6 text-muted-foreground" />
              </div>
              <h3 className="text-lg font-medium text-foreground mb-1">No matches found</h3>
              <p className="text-sm text-muted-foreground max-w-sm">
                No messages contain "<span className="text-foreground font-medium">{query}</span>"
              </p>
            </div>
          )}

          {/* Results list */}
          {results.length > 0 && (
            <div className="space-y-3">
              {results.map((result, index) => {
                const model = getModelInfo(result.message_model_id)
                const isUser = result.message_role === 'user'

                return (
                  <button
                    key={result.conversation.id}
                    onClick={() => handleResultClick(result.conversation.id)}
                    className={cn(
                      "w-full text-left group",
                      "rounded-xl border border-border/50 bg-card/50",
                      "hover:bg-card hover:border-accent-brand/30 hover:shadow-lg hover:shadow-accent-brand/5",
                      "focus:outline-none focus:ring-2 focus:ring-accent-brand/30",
                      "transition-all duration-200"
                    )}
                    style={{ animationDelay: `${index * 30}ms` }}
                  >
                    <div className="p-4">
                      {/* Header: Chat name + timestamp */}
                      <div className="flex items-start justify-between gap-3 mb-3">
                        <h3 className="font-medium text-foreground truncate group-hover:text-accent-brand transition-colors">
                          {result.conversation.name}
                        </h3>
                        <span className="text-xs text-muted-foreground/70 flex-shrink-0">
                          {formatRelativeDate(result.message_created_at)}
                        </span>
                      </div>

                      {/* Message preview with model/role info */}
                      <div className="flex gap-3">
                        {/* Avatar/Icon */}
                        <div className="flex-shrink-0 mt-0.5">
                          {isUser ? (
                            <CachedAvatar
                              src={user?.avatar_url}
                              alt={user?.first_name || 'You'}
                              className="h-7 w-7 bg-muted"
                              fallbackClassName="bg-primary/10 text-primary"
                              fallback={<User className="h-3.5 w-3.5" />}
                            />
                          ) : model ? (
                            <ModelIcon
                              modelName={model.name}
                              modelId={model.model_id}
                              provider={model.provider}
                              modelIconSlug={model.model_icon_slug}
                              modelIconUrl={model.model_icon_url}
                              providerIconSlug={model.provider_icon_slug}
                              providerIconUrl={model.provider_icon_url}
                              size={28}
                              showTooltip={false}
                            />
                          ) : (
                            <div className="w-7 h-7 rounded-full bg-muted flex items-center justify-center">
                              <Bot className="h-3.5 w-3.5 text-muted-foreground" />
                            </div>
                          )}
                        </div>

                        {/* Content */}
                        <div className="flex-1 min-w-0">
                          {/* Role + Model name */}
                          <div className="flex items-center gap-2 mb-1.5">
                            <span className="text-xs font-medium text-muted-foreground">
                              {isUser ? 'You' : model?.name || 'Assistant'}
                            </span>
                          </div>

                          {/* Snippet with highlighting */}
                          <div className="text-sm text-foreground/80 line-clamp-3 leading-relaxed">
                            <HighlightedSnippet text={result.snippet} query={query} />
                          </div>
                        </div>
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          )}

          {/* Load more */}
          {results.length > 0 && results.length < totalCount && (
            <div className="mt-8 flex justify-center">
              <Button
                variant="outline"
                onClick={handleLoadMore}
                disabled={isLoading}
                className={cn(
                  "min-w-[160px] border-border/50",
                  "hover:border-accent-brand/30 hover:bg-accent-brand/5 hover:text-accent-brand",
                  "transition-all"
                )}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Loading...
                  </>
                ) : (
                  <>Load more ({totalCount - results.length})</>
                )}
              </Button>
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
