/**
 * VideosGalleryPage Component
 *
 * Displays a gallery of all AI-generated videos for the current user.
 * Features:
 * - Premium hero section with ambient effects
 * - Responsive grid layout
 * - Click to preview in full-screen modal
 * - Shows generation prompt and model on hover
 * - Link to source conversation
 * - Pagination
 * - Group by: None, Date, Conversation, Model, Resolution, Aspect Ratio, Duration
 */

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useNavigate } from '@tanstack/react-router'
import {
  Film,
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
  Timer,
  Search,
  X,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { assetsAPI, type GalleryAsset } from '@/api/assets'
import { VideoDetailModal } from '@/components/videos/VideoDetailModal'
import { VideoPlayer, VideoThumbnail } from '@/components/videos/VideoPlayer'
import { useNavigationStore } from '@/store/navigationStore'
import { PremiumMenuIcon } from '@/components/ui/premium-menu-icon'

const PAGE_SIZE = 12

type GroupBy = 'none' | 'date' | 'conversation' | 'model' | 'resolution' | 'aspect' | 'duration'

interface GroupedAssets {
  key: string
  label: string
  sublabel?: string
  assets: GalleryAsset[]
}

const GROUP_OPTIONS: { value: GroupBy; label: string; icon: typeof LayoutGrid }[] = [
  { value: 'none', label: 'No grouping', icon: LayoutGrid },
  { value: 'date', label: 'By date', icon: CalendarDays },
  { value: 'conversation', label: 'By chat', icon: MessageSquare },
  { value: 'model', label: 'By model', icon: Cpu },
  { value: 'resolution', label: 'By resolution', icon: Maximize2 },
  { value: 'aspect', label: 'By aspect ratio', icon: RectangleHorizontal },
  { value: 'duration', label: 'By duration', icon: Timer },
]

// Helper function to categorize videos by resolution
function getResolutionCategory(width: number | null, height: number | null): string {
  if (!width || !height) return 'Unknown'
  const pixels = width * height
  const maxDim = Math.max(width, height)

  if (maxDim >= 3840 || pixels >= 3840 * 2160) return '4K (2160p+)'
  if (maxDim >= 1920 || pixels >= 1920 * 1080) return 'Full HD (1080p)'
  if (maxDim >= 1280 || pixels >= 1280 * 720) return 'HD (720p)'
  if (maxDim >= 854 || pixels >= 854 * 480) return 'SD (480p)'
  return 'Low (< 480p)'
}

// Helper function to categorize videos by aspect ratio
function getAspectRatioCategory(width: number | null, height: number | null): string {
  if (!width || !height) return 'Unknown'
  const ratio = width / height

  if (Math.abs(ratio - 1) < 0.1) return 'Square (1:1)'
  if (Math.abs(ratio - 16 / 9) < 0.1) return 'Widescreen (16:9)'
  if (Math.abs(ratio - 9 / 16) < 0.1) return 'Vertical (9:16)'
  if (Math.abs(ratio - 4 / 3) < 0.1) return 'Standard (4:3)'
  if (Math.abs(ratio - 3 / 4) < 0.1) return 'Portrait (3:4)'
  if (Math.abs(ratio - 21 / 9) < 0.15) return 'Ultrawide (21:9)'
  if (ratio > 1.5) return 'Landscape'
  if (ratio < 0.67) return 'Portrait'
  return 'Other'
}

// Helper function to categorize videos by duration
function getDurationCategory(seconds: number | null): string {
  if (!seconds) return 'Unknown'
  if (seconds <= 5) return 'Very short (≤5s)'
  if (seconds <= 10) return 'Short (6-10s)'
  if (seconds <= 30) return 'Medium (11-30s)'
  if (seconds <= 60) return 'Long (31-60s)'
  return 'Very long (>60s)'
}

export function VideosGalleryPage({ embedded }: { embedded?: boolean }) {
  const navigate = useNavigate()
  const { openMobileSidebar } = useNavigationStore()
  const [videos, setVideos] = useState<GalleryAsset[]>([])
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

  // Fetch videos
  const fetchVideos = useCallback(async () => {
    setLoading(true)
    try {
      const response = await assetsAPI.listUserGeneratedVideos({
        page,
        page_size: PAGE_SIZE,
        ...(debouncedSearch && { search: debouncedSearch }),
      })
      setVideos(response.results)
      setTotalCount(response.count)
      setHasNext(!!response.next)
      setHasPrev(!!response.previous)
    } catch (error) {
      console.error('Failed to fetch videos:', error)
    } finally {
      setLoading(false)
    }
  }, [page, debouncedSearch])

  useEffect(() => {
    fetchVideos()
  }, [fetchVideos])

  // Handle video click - open detail modal
  const handleVideoClick = useCallback((video: GalleryAsset) => {
    const index = videos.findIndex(vid => vid.id === video.id)
    setSelectedIndex(index >= 0 ? index : 0)
    setDetailOpen(true)
  }, [videos])

  // Handle video delete from detail modal
  const handleDelete = useCallback((videoId: string) => {
    setVideos(prev => prev.filter(vid => vid.id !== videoId))
    setTotalCount(prev => prev - 1)
    // Close modal if we deleted the current video
    if (videos[selectedIndex]?.id === videoId) {
      setDetailOpen(false)
    }
  }, [videos, selectedIndex])

  const totalPages = Math.ceil(totalCount / PAGE_SIZE)

  // Videos are filtered server-side via search param
  const filteredVideos = videos

  // Group videos based on groupBy selection
  const groupedVideos = useMemo((): GroupedAssets[] => {
    const videosToGroup = filteredVideos

    if (groupBy === 'none') {
      return [{ key: 'all', label: '', assets: videosToGroup }]
    }

    const groups = new Map<string, GroupedAssets>()

    videosToGroup.forEach(video => {
      let key: string
      let label: string
      let sublabel: string | undefined

      switch (groupBy) {
        case 'date': {
          const date = new Date(video.created_at)
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
          key = video.chat_id
          label = video.chat_name || 'Untitled Chat'
          break
        case 'model':
          key = video.generation_model || 'unknown'
          label = video.generation_model_display_name || video.generation_model || 'Unknown Model'
          break
        case 'resolution':
          label = getResolutionCategory(video.width, video.height)
          key = label
          break
        case 'aspect':
          label = getAspectRatioCategory(video.width, video.height)
          key = label
          break
        case 'duration':
          label = getDurationCategory(video.duration_seconds)
          key = label
          break
        default:
          key = 'all'
          label = ''
      }

      if (!groups.has(key)) {
        groups.set(key, { key, label, sublabel, assets: [] })
      }
      groups.get(key)!.assets.push(video)
    })

    // Sort groups
    const sortedGroups = Array.from(groups.values())
    if (groupBy === 'date') {
      // Sort by date descending (newest first)
      sortedGroups.sort((a, b) => b.key.localeCompare(a.key))
    } else if (groupBy === 'conversation' || groupBy === 'model' || groupBy === 'aspect') {
      // Sort by name
      sortedGroups.sort((a, b) => a.label.localeCompare(b.label))
    } else if (groupBy === 'resolution') {
      // Sort by resolution (highest first)
      const resolutionOrder = ['4K (2160p+)', 'Full HD (1080p)', 'HD (720p)', 'SD (480p)', 'Low (< 480p)', 'Unknown']
      sortedGroups.sort((a, b) => resolutionOrder.indexOf(a.label) - resolutionOrder.indexOf(b.label))
    } else if (groupBy === 'duration') {
      // Sort by duration (shortest first)
      const durationOrder = ['Very short (≤5s)', 'Short (6-10s)', 'Medium (11-30s)', 'Long (31-60s)', 'Very long (>60s)', 'Unknown']
      sortedGroups.sort((a, b) => durationOrder.indexOf(a.label) - durationOrder.indexOf(b.label))
    }

    return sortedGroups
  }, [filteredVideos, groupBy])

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
        <h1 className="text-base font-medium text-foreground">Videos</h1>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => fetchVideos()}
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
                Videos
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
                  onClick={() => fetchVideos()}
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
              placeholder="Search videos..."
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
        <div className="max-w-6xl mx-auto px-3 sm:px-6 py-6 pb-24 md:pb-10">
          {loading ? (
            <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-6">
              {Array.from({ length: PAGE_SIZE }).map((_, i) => (
                <div key={i} className="space-y-2">
                  <div className="relative aspect-video rounded-lg sm:rounded-xl overflow-hidden bg-muted/30">
                    <Skeleton className="absolute inset-0" />
                  </div>
                  <Skeleton className="h-3 w-3/4 sm:hidden" />
                </div>
              ))}
            </div>
          ) : filteredVideos.length === 0 && debouncedSearch ? (
            <div className="relative overflow-hidden rounded-2xl border border-dashed border-border/60 bg-gradient-to-br from-muted/20 to-muted/5">
              <div className="relative flex flex-col items-center justify-center py-16 px-6">
                <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-muted/60 to-muted/30 flex items-center justify-center mb-5 shadow-inner">
                  <Search className="w-7 h-7 text-muted-foreground/50" />
                </div>
                <h3 className="text-base font-semibold text-foreground mb-2">No results found</h3>
                <p className="text-sm text-muted-foreground max-w-sm text-center mb-6">
                  No videos match "{debouncedSearch}". Try a different search term.
                </p>
                <Button
                  onClick={() => setSearchQuery('')}
                  variant="outline"
                >
                  Clear search
                </Button>
              </div>
            </div>
          ) : videos.length === 0 ? (
            <div className="relative overflow-hidden rounded-2xl border border-dashed border-border/60 bg-gradient-to-br from-muted/20 to-muted/5">
              <div className="relative flex flex-col items-center justify-center py-12 sm:py-16 px-4 sm:px-6">
                <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-2xl bg-gradient-to-br from-muted/60 to-muted/30 flex items-center justify-center mb-4 sm:mb-5 shadow-inner">
                  <Film className="w-6 h-6 sm:w-7 sm:h-7 text-muted-foreground/50" />
                </div>
                <h3 className="text-base font-semibold text-foreground mb-2">
                  No videos yet
                </h3>
                <p className="text-sm text-muted-foreground max-w-sm text-center mb-5 sm:mb-6">
                  Start a conversation and ask the AI to generate videos. Your creations will appear here.
                </p>
                <Button
                  onClick={() => navigate({ to: '/chats' })}
                  variant="outline"
                  className="rounded-full text-brand-700 dark:text-brand-400 border-brand-300 dark:border-brand-700 hover:bg-brand-50 dark:hover:bg-brand-950/40 hover:text-brand-800 dark:hover:text-brand-300"
                >
                  Create Your First Video
                </Button>
              </div>
            </div>
          ) : groupBy === 'none' ? (
            <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-6">
              {filteredVideos.map((video) => (
                <VideoCard
                  key={video.id}
                  video={video}
                  onClick={() => handleVideoClick(video)}
                />
              ))}
            </div>
          ) : (
            <div className="space-y-8">
              {groupedVideos.map(group => (
                <div key={group.key}>
                  <div className="flex items-center gap-3 mb-4">
                    <div className="flex items-center gap-2">
                      {groupBy === 'date' && <CalendarDays className="h-4 w-4 text-accent-brand" />}
                      {groupBy === 'conversation' && <MessageSquare className="h-4 w-4 text-purple-400" />}
                      {groupBy === 'model' && <Cpu className="h-4 w-4 text-cyan-400" />}
                      {groupBy === 'resolution' && <Maximize2 className="h-4 w-4 text-blue-400" />}
                      {groupBy === 'aspect' && <RectangleHorizontal className="h-4 w-4 text-pink-400" />}
                      {groupBy === 'duration' && <Timer className="h-4 w-4 text-green-400" />}
                      <h3 className="text-sm font-medium text-foreground">{group.label}</h3>
                    </div>
                    <div className="flex-1 h-px bg-border/50" />
                    <span className="text-xs text-muted-foreground">
                      {group.assets.length} video{group.assets.length !== 1 ? 's' : ''}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-6">
                    {group.assets.map((video) => (
                      <VideoCard
                        key={video.id}
                        video={video}
                        onClick={() => handleVideoClick(video)}
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
      <VideoDetailModal
        isOpen={detailOpen}
        onClose={() => setDetailOpen(false)}
        video={videos[selectedIndex] || null}
        videos={videos}
        currentIndex={selectedIndex}
        onNavigate={setSelectedIndex}
        onDelete={handleDelete}
      />
    </div>
  )
}

// ============================================================================
// Video Card Component
// ============================================================================

interface VideoCardProps {
  video: GalleryAsset
  onClick: () => void
}

function VideoCard({ video, onClick }: VideoCardProps) {
  const [isHovered, setIsHovered] = useState(false)

  // Truncate prompt for display - shorter on mobile
  const shortPrompt = video.generation_prompt
    ? video.generation_prompt.length > 60
      ? video.generation_prompt.slice(0, 60) + '...'
      : video.generation_prompt
    : 'Generated video'

  // Very short prompt for mobile card label
  const mobilePrompt = video.generation_prompt
    ? video.generation_prompt.length > 40
      ? video.generation_prompt.slice(0, 40) + '...'
      : video.generation_prompt
    : 'Generated video'

  // Format duration
  const formatDuration = (seconds: number | null) => {
    if (!seconds) return '0:00'
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  // Format relative time for mobile
  const formatRelativeTime = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

    if (diffDays === 0) return 'Today'
    if (diffDays === 1) return 'Yesterday'
    if (diffDays < 7) return `${diffDays}d ago`
    if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`
    return `${Math.floor(diffDays / 30)}mo ago`
  }

  return (
    <div className="space-y-2">
      {/* Video card */}
      <div
        className={cn(
          "group relative aspect-video rounded-lg sm:rounded-xl overflow-hidden cursor-pointer",
          "bg-gradient-to-br from-muted/40 to-muted/20",
          "ring-1 ring-border/50 sm:hover:ring-accent-brand/40",
          "shadow-sm sm:hover:shadow-lg sm:hover:shadow-accent-brand/10",
          "transform transition-all duration-300 ease-out",
          "active:scale-[0.98] sm:hover:scale-[1.02] sm:hover:-translate-y-0.5"
        )}
        onClick={onClick}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        {/* Video thumbnail/preview */}
        <div className="w-full h-full relative bg-black/20">
          {isHovered ? (
            <VideoPlayer
              assetId={video.id}
              autoPlay={true}
              loop={true}
              controls={false}
              className="w-full h-full"
            />
          ) : (
            <VideoThumbnail
              assetId={video.id}
              className="w-full h-full"
              alt={video.generation_prompt || 'Video thumbnail'}
            />
          )}
        </div>

        {/* Duration badge - adjusted for mobile */}
        <div className="absolute top-1.5 right-1.5 sm:top-2 sm:right-2 px-1.5 sm:px-2 py-0.5 sm:py-1 bg-black/70 backdrop-blur-sm rounded sm:rounded-md text-[10px] sm:text-xs font-mono text-white">
          {formatDuration(video.duration_seconds)}
        </div>


        {/* Play button overlay on mobile - always visible for better affordance */}
        <div className="absolute inset-0 flex items-center justify-center sm:hidden pointer-events-none">
          <div className="w-10 h-10 rounded-full bg-black/40 backdrop-blur-sm flex items-center justify-center">
            <div className="w-0 h-0 border-t-[6px] border-t-transparent border-l-[10px] border-l-white border-b-[6px] border-b-transparent ml-1" />
          </div>
        </div>

        {/* Hover overlay with gradient - desktop only */}
        <div
          className={cn(
            "absolute inset-0 transition-all duration-300 pointer-events-none hidden sm:flex",
            "bg-gradient-to-t from-black/80 via-black/30 to-transparent",
            "flex-col justify-end p-3",
            isHovered ? "opacity-100" : "opacity-0"
          )}
        >
          {/* Prompt preview */}
          <p className="text-xs text-white/90 line-clamp-2 leading-relaxed">
            {shortPrompt}
          </p>
        </div>

        {/* Subtle corner accent on hover - desktop only */}
        <div
          className={cn(
            "absolute top-0 right-0 w-12 h-12 transition-opacity duration-300 pointer-events-none hidden sm:block",
            "bg-gradient-to-bl from-accent-brand/20 to-transparent",
            isHovered ? "opacity-100" : "opacity-0"
          )}
        />
      </div>

      {/* Mobile metadata - shown below card */}
      <div className="sm:hidden px-0.5">
        <p className="text-[11px] text-foreground/80 line-clamp-2 leading-snug">
          {mobilePrompt}
        </p>
        <p className="text-[10px] text-muted-foreground mt-0.5">
          {formatRelativeTime(video.created_at)}
        </p>
      </div>
    </div>
  )
}

export default VideosGalleryPage
