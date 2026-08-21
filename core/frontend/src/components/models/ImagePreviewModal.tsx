/**
 * ImagePreviewModal Component
 *
 * Premium image preview matching PDF modal style:
 * - Contained modal with elegant backdrop
 * - Hover effect on image
 * - Download button appears on hover
 * - Gallery navigation for multiple images
 */

import { useEffect, useCallback, useState, useRef } from 'react'
import { createPortal } from 'react-dom'
import { X, Download, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { assetsAPI } from '@/api/assets'

interface ImagePreviewModalProps {
  isOpen: boolean
  onClose: () => void
  images: { src: string; alt: string }[]
  selectedIndex: number
  onIndexChange: (index: number) => void
}

/**
 * Extract asset ID from download URL if it's an asset URL
 */
function getAssetIdFromUrl(url: string): string | null {
  const match = url.match(/\/api\/workspaces\/assets\/([a-f0-9-]+)\/download\/?/)
  return match ? match[1] : null
}

export function ImagePreviewModal({
  isOpen,
  onClose,
  images,
  selectedIndex,
  onIndexChange,
}: ImagePreviewModalProps) {
  const [isHovered, setIsHovered] = useState(false)
  const [blobUrls, setBlobUrls] = useState<Map<number, string>>(new Map())
  const [loadingIndices, setLoadingIndices] = useState<Set<number>>(new Set())
  const loadingRef = useRef<Set<number>>(new Set())
  const currentImage = images[selectedIndex]
  const hasMultiple = images.length > 1
  const canGoPrev = selectedIndex > 0
  const canGoNext = selectedIndex < images.length - 1

  // Get the actual src to display - use blob URL if we've fetched it
  const assetId = currentImage ? getAssetIdFromUrl(currentImage.src) : null
  const hasBlobUrl = blobUrls.has(selectedIndex)
  // For asset URLs, only use the src after we've fetched the blob
  // For non-asset URLs (base64, regular URLs), use directly
  const currentSrc = hasBlobUrl ? blobUrls.get(selectedIndex) : (assetId ? undefined : currentImage?.src)
  // Show loading if: actively fetching OR need to fetch (asset URL without blob)
  const isLoading = loadingIndices.has(selectedIndex) || (!!assetId && !hasBlobUrl)

  // Fetch asset images that need authentication
  useEffect(() => {
    if (!isOpen || !currentImage) return

    const assetId = getAssetIdFromUrl(currentImage.src)
    // Skip if not an asset URL, already loaded, or already loading
    if (!assetId || blobUrls.has(selectedIndex) || loadingRef.current.has(selectedIndex)) return

    loadingRef.current.add(selectedIndex)
    setLoadingIndices(prev => new Set(prev).add(selectedIndex))

    assetsAPI.download(assetId).then(blob => {
      if (blob) {
        const url = URL.createObjectURL(blob)
        setBlobUrls(prev => new Map(prev).set(selectedIndex, url))
      }
    }).catch(err => {
      console.error('Failed to load asset:', err)
    }).finally(() => {
      loadingRef.current.delete(selectedIndex)
      setLoadingIndices(prev => {
        const next = new Set(prev)
        next.delete(selectedIndex)
        return next
      })
    })
  }, [isOpen, selectedIndex, currentImage?.src, blobUrls])

  // Cleanup blob URLs when modal closes or images change
  useEffect(() => {
    if (!isOpen) {
      blobUrls.forEach(url => URL.revokeObjectURL(url))
      setBlobUrls(new Map())
      loadingRef.current.clear()
      setLoadingIndices(new Set())
    }
  }, [isOpen])

  // Navigation handlers
  const goToPrev = useCallback(() => {
    if (canGoPrev) onIndexChange(selectedIndex - 1)
  }, [canGoPrev, selectedIndex, onIndexChange])

  const goToNext = useCallback(() => {
    if (canGoNext) onIndexChange(selectedIndex + 1)
  }, [canGoNext, selectedIndex, onIndexChange])

  // Download handler
  const handleDownload = useCallback(() => {
    if (!currentSrc) return
    const link = document.createElement('a')
    link.href = currentSrc
    link.download = currentImage?.alt || 'image'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }, [currentSrc, currentImage?.alt])

  // Keyboard navigation
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'Escape':
          onClose()
          break
        case 'ArrowLeft':
          goToPrev()
          break
        case 'ArrowRight':
          goToNext()
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose, goToPrev, goToNext])

  if (!isOpen || !currentImage) return null

  const modalContent = (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm animate-in fade-in-0 duration-200"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <div
          className="relative bg-background rounded-2xl overflow-hidden shadow-2xl border border-border pointer-events-auto animate-in zoom-in-95 fade-in-0 duration-200 max-w-3xl w-full"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-border">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <h2 className="text-base font-semibold text-foreground truncate">
                {currentImage.alt || 'Image Preview'}
              </h2>
              {hasMultiple && (
                <span className="text-sm text-muted-foreground flex-shrink-0">
                  {selectedIndex + 1} of {images.length}
                </span>
              )}
            </div>
            <button
              onClick={onClose}
              className="flex-shrink-0 p-2.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted active:bg-muted active:text-foreground active:scale-95 transition-colors touch-manipulation"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div
            className="p-6 flex flex-col items-center"
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
          >
            {/* Image container with hover effect */}
            <div className="relative">
              {/* Navigation arrows (for multiple images) */}
              {hasMultiple && (
                <>
                  <button
                    onClick={goToPrev}
                    disabled={!canGoPrev}
                    className={cn(
                      "absolute left-2 top-1/2 -translate-y-1/2 z-10 p-2.5 rounded-full transition-all touch-manipulation",
                      "bg-background/80 backdrop-blur-sm border border-border shadow-lg",
                      canGoPrev
                        ? "text-foreground hover:bg-background hover:scale-110 active:scale-95 active:bg-background"
                        : "text-muted-foreground/50 cursor-not-allowed",
                      // Always visible on touch, hover-reveal on desktop
                      "opacity-100 [@media(hover:hover)]:opacity-0",
                      isHovered && "[@media(hover:hover)]:opacity-100"
                    )}
                  >
                    <ChevronLeft className="h-5 w-5" />
                  </button>
                  <button
                    onClick={goToNext}
                    disabled={!canGoNext}
                    className={cn(
                      "absolute right-2 top-1/2 -translate-y-1/2 z-10 p-2.5 rounded-full transition-all touch-manipulation",
                      "bg-background/80 backdrop-blur-sm border border-border shadow-lg",
                      canGoNext
                        ? "text-foreground hover:bg-background hover:scale-110 active:scale-95 active:bg-background"
                        : "text-muted-foreground/50 cursor-not-allowed",
                      // Always visible on touch, hover-reveal on desktop
                      "opacity-100 [@media(hover:hover)]:opacity-0",
                      isHovered && "[@media(hover:hover)]:opacity-100"
                    )}
                  >
                    <ChevronRight className="h-5 w-5" />
                  </button>
                </>
              )}

              {/* Image - clickable to download on desktop only */}
              <div
                role="button"
                tabIndex={0}
                onClick={handleDownload}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') handleDownload() }}
                className="relative focus:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded-lg pointer-events-none [@media(hover:hover)]:pointer-events-auto [@media(hover:hover)]:cursor-pointer"
                aria-label="Click to download image"
              >
                <div
                  className={cn(
                    "relative rounded-lg overflow-hidden transition-all duration-300 ease-out ring-1 ring-border",
                    "shadow-lg",
                    isHovered && "shadow-xl ring-primary/50"
                  )}
                  style={{
                    transform: isHovered ? 'scale(1.02)' : 'scale(1)',
                    transition: 'transform 0.3s ease-out, box-shadow 0.3s ease-out',
                  }}
                >
                  {isLoading ? (
                    <div className="flex items-center justify-center bg-muted/30 min-w-[200px] min-h-[200px]">
                      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                    </div>
                  ) : (
                    <img
                      src={currentSrc}
                      alt={currentImage.alt}
                      className="max-w-full max-h-[60vh] object-contain bg-muted/30"
                      draggable={false}
                    />
                  )}
                </div>
              </div>
            </div>

            {/* Thumbnail navigation / Download button area */}
            <div className="mt-6 relative h-10 flex items-center justify-center">
              {hasMultiple ? (
                // Thumbnail dots for multiple images - hidden on touch, visible on hover-capable when not hovered
                <div
                  className={cn(
                    "flex items-center gap-2 transition-all duration-300",
                    "hidden [@media(hover:hover)]:flex",
                    isHovered ? "opacity-0 scale-95" : "opacity-100 scale-100"
                  )}
                >
                  {images.map((_, idx) => (
                    <button
                      key={idx}
                      onClick={() => onIndexChange(idx)}
                      className={cn(
                        "w-2 h-2 rounded-full transition-all touch-manipulation",
                        idx === selectedIndex
                          ? "bg-primary w-6"
                          : "bg-muted-foreground/30 hover:bg-muted-foreground/50 active:bg-muted-foreground/50"
                      )}
                    />
                  ))}
                </div>
              ) : (
                // File type for single image - hidden on touch, visible on hover-capable when not hovered
                <span
                  className={cn(
                    "text-sm text-muted-foreground transition-all duration-300",
                    "hidden [@media(hover:hover)]:block",
                    isHovered ? "opacity-0 scale-95" : "opacity-100 scale-100"
                  )}
                >
                  {(() => {
                    // Try to get extension from filename
                    const filename = currentImage.alt || ''
                    const extMatch = filename.match(/\.([a-zA-Z0-9]+)$/i)
                    if (extMatch) return extMatch[1].toUpperCase()
                    // Try to detect from data URL
                    if (currentImage.src.startsWith('data:image/')) {
                      const mimeMatch = currentImage.src.match(/data:image\/([a-zA-Z0-9]+)/i)
                      if (mimeMatch) return mimeMatch[1].toUpperCase()
                    }
                    return 'Image'
                  })()}
                </span>
              )}

              {/* Download button - always visible on touch, hover-reveal on desktop */}
              <button
                onClick={handleDownload}
                className={cn(
                  "flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg",
                  "bg-primary hover:bg-primary/90 active:bg-primary/80 active:scale-95 text-primary-foreground text-sm font-medium",
                  "transition-all duration-300 absolute touch-manipulation",
                  // Always visible on touch devices, hover-controlled on desktop
                  "opacity-100 scale-100",
                  "[@media(hover:hover)]:opacity-0 [@media(hover:hover)]:scale-95 [@media(hover:hover)]:pointer-events-none",
                  isHovered && "[@media(hover:hover)]:opacity-100 [@media(hover:hover)]:scale-100 [@media(hover:hover)]:pointer-events-auto"
                )}
              >
                <Download className="h-4 w-4 flex-shrink-0" />
                <span>Download</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  )

  return createPortal(modalContent, document.body)
}
