/**
 * ImagesGalleryPage Component
 *
 * Displays a gallery of all AI-generated images for the current user.
 * Features:
 * - Premium hero section with ambient effects
 * - Responsive grid layout
 * - Click to preview in full-screen modal
 * - Shows generation prompt and model on hover
 * - Link to source conversation
 * - Pagination
 * - Group by: None, Date, Conversation, Model
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useNavigate } from '@tanstack/react-router'
import {
  Sparkles,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  LayoutGrid,
  CalendarDays,
  MessageSquare,
  Cpu,
  ChevronDown,
  Maximize2,
  RectangleHorizontal,
  Search,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { assetsAPI, type GalleryAsset } from '@/api/assets'
import { ImageDetailModal } from '@/components/images/ImageDetailModal'
import { AssetImage } from '@/components/models/AssetImage'
import { useNavigationStore } from '@/store/navigationStore'
import { PremiumMenuIcon } from '@/components/ui/premium-menu-icon'

const PAGE_SIZE = 24

type GroupBy = 'none' | 'date' | 'conversation' | 'model' | 'resolution' | 'aspect'

interface GroupedAssets {
  key: string
  label: string
  sublabel?: string
  assets: GalleryAsset[]
  sortKey?: number // For numeric sorting
}

const GROUP_OPTIONS: { value: GroupBy; label: string; icon: typeof LayoutGrid }[] = [
  { value: 'none', label: 'No grouping', icon: LayoutGrid },
  { value: 'date', label: 'By date', icon: CalendarDays },
  { value: 'conversation', label: 'By chat', icon: MessageSquare },
  { value: 'model', label: 'By model', icon: Cpu },
  { value: 'resolution', label: 'By resolution', icon: Maximize2 },
  { value: 'aspect', label: 'By aspect ratio', icon: RectangleHorizontal },
]

// Helper to get aspect ratio category
function getAspectRatioCategory(width: number | null, height: number | null): { key: string; label: string; sortKey: number } {
  if (!width || !height) return { key: 'unknown', label: 'Unknown', sortKey: 99 }

  const ratio = width / height

  if (Math.abs(ratio - 1) < 0.1) return { key: 'square', label: 'Square (1:1)', sortKey: 2 }
  if (ratio > 1) {
    if (ratio >= 1.7) return { key: 'widescreen', label: 'Widescreen (16:9)', sortKey: 4 }
    return { key: 'landscape', label: 'Landscape', sortKey: 3 }
  } else {
    if (ratio <= 0.6) return { key: 'tall', label: 'Tall (9:16)', sortKey: 0 }
    return { key: 'portrait', label: 'Portrait', sortKey: 1 }
  }
}

// Helper to get resolution category
function getResolutionCategory(width: number | null, height: number | null): { key: string; label: string; sortKey: number } {
  if (!width || !height) return { key: 'unknown', label: 'Unknown', sortKey: 99 }

  const pixels = width * height
  const megapixels = pixels / 1_000_000

  // Common AI image resolutions
  if (width === 1024 && height === 1024) return { key: '1024x1024', label: '1024×1024', sortKey: pixels }
  if (width === 1792 && height === 1024) return { key: '1792x1024', label: '1792×1024', sortKey: pixels }
  if (width === 1024 && height === 1792) return { key: '1024x1792', label: '1024×1792', sortKey: pixels }
  if (width === 512 && height === 512) return { key: '512x512', label: '512×512', sortKey: pixels }

  // Group by megapixel ranges
  if (megapixels >= 4) return { key: '4mp+', label: '4MP+ (Ultra HD)', sortKey: 4_000_000 }
  if (megapixels >= 2) return { key: '2-4mp', label: '2-4MP (HD)', sortKey: 2_000_000 }
  if (megapixels >= 1) return { key: '1-2mp', label: '1-2MP', sortKey: 1_000_000 }
  return { key: 'sub1mp', label: '< 1MP', sortKey: 500_000 }
}

export function ImagesGalleryPage({ embedded }: { embedded?: boolean }) {
  const navigate = useNavigate()
  const { openMobileSidebar } = useNavigationStore()
  const [images, setImages] = useState<GalleryAsset[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [hasNext, setHasNext] = useState(false)
  const [hasPrev, setHasPrev] = useState(false)

  // Group by state
  const [groupBy, setGroupBy] = useState<GroupBy>('none')
  const [groupDropdownOpen, setGroupDropdownOpen] = useState(false)
  const groupButtonRef = useRef<HTMLButtonElement>(null)

  // Search state
  const [searchQuery, setSearchQuery] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [isSearchOpen, setIsSearchOpen] = useState(false)

  // Debounce search query
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery)
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [searchQuery])

  // Detail modal state
  const [detailOpen, setDetailOpen] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(0)

  // Fetch images
  const fetchImages = useCallback(async () => {
    setLoading(true)
    try {
      const response = await assetsAPI.listUserGeneratedImages({
        page,
        page_size: PAGE_SIZE,
        ...(debouncedSearch && { search: debouncedSearch }),
      })
      setImages(response.results)
      setTotalCount(response.count)
      setHasNext(!!response.next)
      setHasPrev(!!response.previous)
    } catch (error) {
      console.error('Failed to fetch images:', error)
    } finally {
      setLoading(false)
    }
  }, [page, debouncedSearch])

  useEffect(() => {
    fetchImages()
  }, [fetchImages])

  // Handle image click - open detail modal
  const handleImageClick = useCallback((image: GalleryAsset) => {
    const index = images.findIndex(img => img.id === image.id)
    setSelectedIndex(index >= 0 ? index : 0)
    setDetailOpen(true)
  }, [images])

  // Handle image delete from detail modal
  const handleDelete = useCallback((imageId: string) => {
    setImages(prev => prev.filter(img => img.id !== imageId))
    setTotalCount(prev => prev - 1)
    // Close modal if we deleted the current image
    if (images[selectedIndex]?.id === imageId) {
      setDetailOpen(false)
    }
  }, [images, selectedIndex])

  const totalPages = Math.ceil(totalCount / PAGE_SIZE)

  // Images are filtered server-side via search param
  const filteredImages = images

  // Group images based on groupBy selection
  const groupedImages = useMemo((): GroupedAssets[] => {
    const imagesToGroup = filteredImages

    if (groupBy === 'none') {
      return [{ key: 'all', label: '', assets: imagesToGroup }]
    }

    const groups = new Map<string, GroupedAssets>()

    imagesToGroup.forEach(image => {
      let key: string
      let label: string
      let sublabel: string | undefined
      let sortKey: number | undefined

      switch (groupBy) {
        case 'date': {
          const date = new Date(image.created_at)
          const today = new Date()
          const yesterday = new Date(today)
          yesterday.setDate(yesterday.getDate() - 1)

          const isToday = date.toDateString() === today.toDateString()
          const isYesterday = date.toDateString() === yesterday.toDateString()

          key = date.toISOString().split('T')[0]
          if (isToday) {
            label = 'Today'
          } else if (isYesterday) {
            label = 'Yesterday'
          } else {
            label = date.toLocaleDateString('en-US', {
              weekday: 'long',
              month: 'long',
              day: 'numeric',
            })
          }
          break
        }
        case 'conversation':
          key = image.chat_id
          label = image.chat_name || 'Untitled Chat'
          break
        case 'model':
          key = image.generation_model || 'unknown'
          label = image.generation_model_display_name || image.generation_model || 'Unknown Model'
          break
        case 'resolution': {
          const res = getResolutionCategory(image.width, image.height)
          key = res.key
          label = res.label
          sortKey = res.sortKey
          break
        }
        case 'aspect': {
          const aspect = getAspectRatioCategory(image.width, image.height)
          key = aspect.key
          label = aspect.label
          sortKey = aspect.sortKey
          break
        }
        default:
          key = 'all'
          label = ''
      }

      if (!groups.has(key)) {
        groups.set(key, { key, label, sublabel, assets: [], sortKey })
      }
      groups.get(key)!.assets.push(image)
    })

    // Sort groups
    const sortedGroups = Array.from(groups.values())
    if (groupBy === 'date') {
      // Sort by date descending (newest first)
      sortedGroups.sort((a, b) => b.key.localeCompare(a.key))
    } else if (groupBy === 'conversation' || groupBy === 'model') {
      // Sort by name
      sortedGroups.sort((a, b) => a.label.localeCompare(b.label))
    } else if (groupBy === 'resolution') {
      // Sort by resolution descending (highest first)
      sortedGroups.sort((a, b) => (b.sortKey || 0) - (a.sortKey || 0))
    } else if (groupBy === 'aspect') {
      // Sort by predefined order
      sortedGroups.sort((a, b) => (a.sortKey || 99) - (b.sortKey || 99))
    }

    return sortedGroups
  }, [filteredImages, groupBy])

  // Get current group option
  const currentGroupOption = GROUP_OPTIONS.find(opt => opt.value === groupBy) || GROUP_OPTIONS[0]

  const paginationBar = !loading && totalPages > 1 ? (
    <div className="shrink-0 flex items-center justify-center gap-2 py-3 border-t border-border/30 bg-background">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setPage(p => p - 1)}
        disabled={!hasPrev}
        className="h-8 px-3"
      >
        <ChevronLeft className="h-4 w-4 mr-1" />
        Prev
      </Button>

      <div className="flex items-center gap-1 px-2">
        {Array.from({ length: Math.min(totalPages, 5) }).map((_, i) => {
          let pageNum: number
          if (totalPages <= 5) pageNum = i + 1
          else if (page <= 3) pageNum = i + 1
          else if (page >= totalPages - 2) pageNum = totalPages - 4 + i
          else pageNum = page - 2 + i

          return (
            <button
              key={pageNum}
              onClick={() => setPage(pageNum)}
              className={cn(
                'w-8 h-8 rounded-md text-sm font-medium transition-colors',
                page === pageNum
                  ? 'bg-foreground text-background'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/60'
              )}
            >
              {pageNum}
            </button>
          )
        })}
      </div>

      <Button
        variant="ghost"
        size="sm"
        onClick={() => setPage(p => p + 1)}
        disabled={!hasNext}
        className="h-8 px-3"
      >
        Next
        <ChevronRight className="h-4 w-4 ml-1" />
      </Button>
    </div>
  ) : null

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background">
      {/* Mobile header */}
      {!embedded && (
      <div className="md:hidden flex items-center justify-between px-4 py-3 border-b border-border/50 sticky top-0 z-40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <button
          onClick={openMobileSidebar}
          className="p-2 -ml-2 text-foreground transition-colors"
        >
          <PremiumMenuIcon size={18} />
        </button>
        <h1 className="text-base font-medium text-foreground">Images</h1>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => fetchImages()}
          disabled={loading}
          className="h-9 w-9 -mr-2"
        >
          <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
        </Button>
      </div>
      )}

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto">
        {/* Sticky desktop header */}
        <div className="sticky top-0 z-30 bg-background hidden md:block">
          <div className={cn("max-w-6xl mx-auto px-4 sm:px-6 pb-5", embedded ? "pt-4" : "pt-8")}>
            {/* Title row */}
            <div className="flex items-center justify-between gap-4">
              {!embedded && (
              <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                Images
              </h1>
              )}
              <div className={cn("flex items-center gap-2", embedded && "ml-auto")}>
                {/* Search toggle */}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setIsSearchOpen(!isSearchOpen)}
                  className={cn(
                    "h-9 px-3",
                    isSearchOpen && "bg-accent-brand/10 border-accent-brand/30 text-accent-brand"
                  )}
                >
                  <Search className="h-4 w-4" />
                </Button>

                {/* Group by dropdown */}
                <div className="relative">
                  <Button
                    ref={groupButtonRef}
                    variant="outline"
                    size="sm"
                    onClick={() => setGroupDropdownOpen(!groupDropdownOpen)}
                    className="h-9 px-3"
                  >
                    <currentGroupOption.icon className="h-4 w-4 mr-2" />
                    {currentGroupOption.label}
                    <ChevronDown className={cn("h-4 w-4 ml-2 transition-transform", groupDropdownOpen && "rotate-180")} />
                  </Button>

                  {groupDropdownOpen && groupButtonRef.current && (() => {
                    const rect = groupButtonRef.current.getBoundingClientRect()
                    return (
                      <>
                        <div className="fixed inset-0 z-40" onClick={() => setGroupDropdownOpen(false)} />
                        <div
                          className="fixed z-50 w-48 py-1 bg-background border border-border/50 rounded-lg shadow-lg max-h-80 overflow-y-auto"
                          style={{
                            top: rect.bottom + 4,
                            right: window.innerWidth - rect.right,
                          }}
                        >
                          {GROUP_OPTIONS.map(option => (
                            <button
                              key={option.value}
                              onClick={() => {
                                setGroupBy(option.value)
                                setGroupDropdownOpen(false)
                              }}
                              className={cn(
                                "w-full px-3 py-2 text-left text-sm flex items-center gap-2 transition-colors",
                                groupBy === option.value
                                  ? "bg-accent-brand/10 text-accent-brand"
                                  : "text-foreground hover:bg-muted/50"
                              )}
                            >
                              <option.icon className="h-4 w-4" />
                              {option.label}
                            </button>
                          ))}
                        </div>
                      </>
                    )
                  })()}
                </div>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => fetchImages()}
                  disabled={loading}
                  className="h-9 px-3"
                >
                  <RefreshCw className={cn("h-4 w-4 mr-2", loading && "animate-spin")} />
                  Refresh
                </Button>
              </div>
            </div>

            {/* Search bar - collapsible */}
            {isSearchOpen && (
              <div className="mt-4 flex items-center gap-2">
                <div className="relative flex-1 max-w-md">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search by prompt or model..."
                    className="w-full h-9 pl-9 pr-9 rounded-full bg-transparent border border-border/50 text-sm placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring transition-colors"
                    maxLength={500}
                    autoFocus
                  />
                  {searchQuery && (
                    <button
                      onClick={() => setSearchQuery('')}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Mobile filters — sticky below mobile header */}
        <div className="md:hidden px-4 py-2.5 space-y-2.5 border-b border-border/30 sticky top-0 z-20 bg-background">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search images..."
              className="w-full h-9 pl-9 pr-9 rounded-lg bg-muted/50 border border-border/50 text-sm placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring transition-colors"
              maxLength={500}
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-none pb-0.5">
            {GROUP_OPTIONS.map(option => (
              <button
                key={option.value}
                onClick={() => setGroupBy(option.value)}
                className={cn(
                  "px-2.5 py-1 text-xs rounded-full whitespace-nowrap transition-colors flex items-center gap-1.5",
                  groupBy === option.value
                    ? "bg-accent-brand/20 text-accent-brand"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                )}
              >
                <option.icon className="h-3 w-3" />
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {/* Grid content */}
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 pb-24 md:pb-10">
          {loading ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4">
              {Array.from({ length: PAGE_SIZE }).map((_, i) => (
                <div key={i} className="relative aspect-square rounded-xl overflow-hidden bg-muted/30">
                  <Skeleton className="absolute inset-0" />
                </div>
              ))}
            </div>
          ) : filteredImages.length === 0 && debouncedSearch ? (
            <div className="relative overflow-hidden rounded-2xl border border-dashed border-border/60 bg-gradient-to-br from-muted/20 to-muted/5">
              <div className="relative flex flex-col items-center justify-center py-16 px-6">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-muted/60 to-muted/30 flex items-center justify-center mb-5 shadow-inner">
                  <Search className="w-7 h-7 text-muted-foreground/50" />
                </div>
                <h3 className="text-base font-semibold text-foreground mb-2">No results found</h3>
                <p className="text-sm text-muted-foreground max-w-sm text-center mb-6">
                  No images match "{debouncedSearch}". Try a different search term.
                </p>
                <Button
                  onClick={() => setSearchQuery('')}
                  variant="outline"
                >
                  Clear search
                </Button>
              </div>
            </div>
          ) : images.length === 0 ? (
            <div className="relative overflow-hidden rounded-2xl border border-dashed border-border/60 bg-gradient-to-br from-muted/20 to-muted/5">
              <div className="relative flex flex-col items-center justify-center py-16 px-6">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-muted/60 to-muted/30 flex items-center justify-center mb-5 shadow-inner">
                  <Sparkles className="w-7 h-7 text-muted-foreground/50" />
                </div>
                <h3 className="text-base font-semibold text-foreground mb-2">
                  No images yet
                </h3>
                <p className="text-sm text-muted-foreground max-w-sm text-center mb-6">
                  Start a conversation and ask the AI to generate images. Your creations will appear here.
                </p>
                <Button
                  onClick={() => navigate({ to: '/chats' })}
                  variant="outline"
                  className="rounded-full text-brand-700 dark:text-brand-400 border-brand-300 dark:border-brand-700 hover:bg-brand-50 dark:hover:bg-brand-950/40 hover:text-brand-800 dark:hover:text-brand-300"
                >
                  Create Your First Image
                </Button>
              </div>
            </div>
          ) : groupBy === 'none' ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4">
              {filteredImages.map((image) => (
                <ImageCard
                  key={image.id}
                  image={image}
                  onClick={() => handleImageClick(image)}
                />
              ))}
            </div>
          ) : (
            <div className="space-y-8">
              {groupedImages.map(group => (
                <div key={group.key}>
                  <div className="flex items-center gap-3 mb-4">
                    <div className="flex items-center gap-2">
                      {groupBy === 'date' && <CalendarDays className="h-4 w-4 text-accent-brand" />}
                      {groupBy === 'conversation' && <MessageSquare className="h-4 w-4 text-purple-400" />}
                      {groupBy === 'model' && <Cpu className="h-4 w-4 text-cyan-400" />}
                      {groupBy === 'resolution' && <Maximize2 className="h-4 w-4 text-blue-400" />}
                      {groupBy === 'aspect' && <RectangleHorizontal className="h-4 w-4 text-emerald-400" />}
                      <h3 className="text-sm font-medium text-foreground">{group.label}</h3>
                    </div>
                    <div className="flex-1 h-px bg-border/50" />
                    <span className="text-xs text-muted-foreground">
                      {group.assets.length} image{group.assets.length !== 1 ? 's' : ''}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 sm:gap-4">
                    {group.assets.map((image) => (
                      <ImageCard
                        key={image.id}
                        image={image}
                        onClick={() => handleImageClick(image)}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Pagination inside scroll area on mobile when embedded */}
        {embedded && <div className="md:hidden pb-20">{paginationBar}</div>}
      </div>

      {/* Pagination pinned to bottom — always when standalone, desktop-only when embedded */}
      <div className={embedded ? "hidden md:block" : ""}>{paginationBar}</div>

      {/* Detail Modal */}
      <ImageDetailModal
        isOpen={detailOpen}
        onClose={() => setDetailOpen(false)}
        image={images[selectedIndex] || null}
        images={images}
        currentIndex={selectedIndex}
        onNavigate={setSelectedIndex}
        onDelete={handleDelete}
      />
    </div>
  )
}

// ============================================================================
// Image Card Component
// ============================================================================

interface ImageCardProps {
  image: GalleryAsset
  onClick: () => void
}

function ImageCard({ image, onClick }: ImageCardProps) {
  const [isHovered, setIsHovered] = useState(false)

  // Truncate prompt for display
  const shortPrompt = image.generation_prompt
    ? image.generation_prompt.length > 80
      ? image.generation_prompt.slice(0, 80) + '...'
      : image.generation_prompt
    : 'Generated image'

  return (
    <div
      className={cn(
        "group relative aspect-square rounded-xl overflow-hidden cursor-pointer",
        "bg-gradient-to-br from-muted/40 to-muted/20",
        "ring-1 ring-border/50 hover:ring-accent-brand/40",
        "shadow-sm hover:shadow-lg hover:shadow-accent-brand/10",
        "transform transition-all duration-300 ease-out",
        "hover:scale-[1.02] hover:-translate-y-0.5"
      )}
      onClick={onClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Image */}
      <AssetImage
        assetId={image.id}
        alt={image.generation_prompt || image.filename}
        className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
      />

      {/* Hover overlay with gradient */}
      <div
        className={cn(
          "absolute inset-0 transition-all duration-300 pointer-events-none",
          "bg-gradient-to-t from-black/80 via-black/30 to-transparent",
          "flex flex-col justify-end p-3",
          isHovered ? "opacity-100" : "opacity-0"
        )}
      >
        {/* Prompt preview */}
        <p className="text-xs text-white/90 line-clamp-2 leading-relaxed">
          {shortPrompt}
        </p>
      </div>

    </div>
  )
}
