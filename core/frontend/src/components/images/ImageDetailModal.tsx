/**
 * ImageDetailModal Component
 *
 * Full-screen lightbox for viewing images.
 * Desktop: Theater mode with centered image, floating toolbar, and toggleable info panel
 * Mobile: Bottom sheet pattern with swipe navigation
 */

import { useEffect, useCallback, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import {
  X,
  Download,
  ChevronLeft,
  ChevronRight,
  Info,
  MessageSquare,
  Trash2,
  Loader2,
  Share2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { AssetImage } from '@/components/models/AssetImage'
import { type GalleryAsset, assetsAPI } from '@/api/assets'
import { cn } from '@/lib/utils'
import { formatModelId } from '@/utils/modelNames'
import { ShareMenu, MobileShareSheet } from '@/components/share'
import { useSettingsStore } from '@/store/settingsStore'

interface ImageDetailModalProps {
  isOpen: boolean
  onClose: () => void
  image: GalleryAsset | null
  images: GalleryAsset[]
  currentIndex: number
  onNavigate: (index: number) => void
  onDelete?: (imageId: string) => void
}

/**
 * Format bytes to human readable size
 */
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * Get resolution label from dimensions
 */
function getResolutionLabel(width: number | null, height: number | null): string {
  if (!width || !height) return 'Unknown'

  const maxDim = Math.max(width, height)

  if (maxDim >= 3840) return '4K'
  if (maxDim >= 2560) return '2.5K'
  if (maxDim >= 1920) return '2K'
  if (maxDim >= 1280) return '1.5K'
  if (maxDim >= 1024) return '1K'
  return 'SD'
}


/**
 * Format date to readable string
 */
function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export function ImageDetailModal({
  isOpen,
  onClose,
  image,
  images,
  currentIndex,
  onNavigate,
  onDelete,
}: ImageDetailModalProps) {
  const navigate = useNavigate()
  // Start with UI visible so users see controls, tap to go immersive
  const [showInfo, setShowInfo] = useState(true)
  const [isDeleting, setIsDeleting] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showShareMenu, setShowShareMenu] = useState(false)

  // Get watermark settings from global settings
  const watermark = useSettingsStore((state) => state.watermark)

  const hasNext = currentIndex < images.length - 1
  const hasPrev = currentIndex > 0

  // Handle keyboard navigation
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      } else if (e.key === 'ArrowRight' && hasNext) {
        onNavigate(currentIndex + 1)
      } else if (e.key === 'ArrowLeft' && hasPrev) {
        onNavigate(currentIndex - 1)
      } else if (e.key === 'i') {
        setShowInfo(prev => !prev)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose, hasNext, hasPrev, currentIndex, onNavigate])

  // Lock body scroll when open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [isOpen])


  // Download image
  const handleDownload = useCallback(async () => {
    if (!image) return
    try {
      // Download with watermark settings from global settings
      const blob = await assetsAPI.download(image.id, {
        watermark: watermark.enabled,
        watermark_position: watermark.position,
      })
      if (!blob) return

      // Use name (generation_prompt) for download filename, sanitized
      // If watermark is enabled, always use .png extension since watermarked images are PNG
      const extension = watermark.enabled ? 'png' : (image.filename.split('.').pop() || 'png')
      const baseName = image.generation_prompt
        ? image.generation_prompt
            .slice(0, 50)
            .replace(/[^a-zA-Z0-9\s-]/g, '')
            .replace(/\s+/g, '_')
            .toLowerCase()
        : 'image'
      const downloadName = `${baseName}.${extension}`

      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = downloadName
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Failed to download:', err)
    }
  }, [image, watermark])

  // Navigate to conversation
  const handleViewConversation = useCallback(() => {
    if (!image || !image.conversation_id) return
    onClose()
    navigate({ to: '/chats', search: { conversation: image.conversation_id } })
  }, [image, navigate, onClose])

  // Delete image
  const handleDelete = useCallback(async () => {
    if (!image || !onDelete) return

    setIsDeleting(true)
    try {
      const success = await assetsAPI.delete(image.id)
      if (success) {
        onDelete(image.id)
        setShowDeleteConfirm(false)
      }
    } catch (error) {
      console.error('Failed to delete image:', error)
    } finally {
      setIsDeleting(false)
    }
  }, [image, onDelete])

  if (!isOpen || !image) return null

  const resolution = getResolutionLabel(image.width, image.height)
  const dimensions = image.width && image.height ? `${image.width} × ${image.height}` : null

  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/95"
        onClick={onClose}
      />

      {/* ============================================== */}
      {/* MOBILE LAYOUT - Immersive with toggleable UI */}
      {/* ============================================== */}
      <div className="lg:hidden h-full flex flex-col">
        {/* Tap zone for toggling UI - covers the image area */}
        <div
          className="absolute inset-0 z-10"
          onClick={() => setShowInfo(prev => !prev)}
        />

        {/* Mobile header - toggleable */}
        <div
          className={cn(
            "relative z-20 flex items-center justify-between px-4 py-3 transition-all duration-200",
            "bg-gradient-to-b from-black/60 to-transparent",
            showInfo ? "opacity-100 translate-y-0" : "opacity-0 -translate-y-full pointer-events-none"
          )}
        >
          <button
            onClick={(e) => { e.stopPropagation(); onClose() }}
            className="p-2 -ml-2 rounded-full text-white/90 active:bg-white/10"
          >
            <X className="h-6 w-6" />
          </button>

          {/* Image counter */}
          <span className="text-sm text-white/80 font-medium">
            {currentIndex + 1} / {images.length}
          </span>

          {/* View conversation */}
          <button
            onClick={(e) => { e.stopPropagation(); handleViewConversation() }}
            className="p-2 -mr-2 rounded-full text-white/90 active:bg-white/10"
          >
            <MessageSquare className="h-5 w-5" />
          </button>
        </div>

        {/* Image section - full screen */}
        <div className="absolute inset-0 flex items-center justify-center px-4">
          <AssetImage
            key={image.id}
            assetId={image.id}
            alt={image.generation_prompt || image.filename}
            className="max-w-full max-h-full object-contain"
          />
        </div>

        {/* Mobile navigation - edge tap zones (always active) */}
        <button
          onClick={(e) => { e.stopPropagation(); hasPrev && onNavigate(currentIndex - 1) }}
          className={cn(
            "absolute left-0 top-0 bottom-0 w-16 z-20",
            !hasPrev && "pointer-events-none"
          )}
          aria-label="Previous image"
        />
        <button
          onClick={(e) => { e.stopPropagation(); hasNext && onNavigate(currentIndex + 1) }}
          className={cn(
            "absolute right-0 top-0 bottom-0 w-16 z-20",
            !hasNext && "pointer-events-none"
          )}
          aria-label="Next image"
        />

        {/* Mobile bottom bar - toggleable */}
        <div
          className={cn(
            "absolute bottom-0 left-0 right-0 z-20 transition-all duration-200",
            "bg-gradient-to-t from-black/80 via-black/60 to-transparent",
            showInfo ? "opacity-100 translate-y-0" : "opacity-0 translate-y-full pointer-events-none"
          )}
        >
          {/* Image name/prompt */}
          {image.generation_prompt && (
            <div className="px-4 pt-8 pb-2">
              <p className="text-white/90 text-sm leading-relaxed line-clamp-2">
                {image.generation_prompt}
              </p>
            </div>
          )}

          {/* Compact metadata row */}
          <div className="px-4 pb-3 flex items-center gap-4 text-xs text-white/60">
            <span>{image.generation_model_display_name || formatModelId(image.generation_model)}</span>
            <span>{resolution}</span>
            <span>{formatFileSize(image.size_bytes)}</span>
          </div>

          {/* Actions */}
          <div className="px-4 pb-6 safe-area-bottom flex gap-3">
            <Button
              onClick={(e) => { e.stopPropagation(); handleDownload() }}
              className="flex-1 h-12 btn-premium"
            >
              <Download className="h-4 w-4 mr-2" />
              Download
            </Button>
            <Button
              onClick={(e) => { e.stopPropagation(); setShowShareMenu(true) }}
              variant="outline"
              className="h-12 px-4 border-white/20 text-white/80 hover:bg-white/10"
            >
              <Share2 className="h-4 w-4" />
            </Button>
            {onDelete && (
              <Button
                onClick={(e) => { e.stopPropagation(); setShowDeleteConfirm(true) }}
                variant="outline"
                className="h-12 px-4 border-white/20 text-white/80 hover:bg-red-500/20 hover:border-red-500/50 hover:text-red-400"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>

        {/* Tap hint - shows briefly when UI is hidden */}
        <div
          className={cn(
            "absolute bottom-8 left-1/2 -translate-x-1/2 z-10 transition-opacity duration-300",
            "text-xs text-white/40",
            !showInfo ? "opacity-100" : "opacity-0 pointer-events-none"
          )}
        >
          Tap for options
        </div>
      </div>

      {/* ============================================== */}
      {/* DESKTOP LAYOUT - Lightbox/Theater Mode */}
      {/* ============================================== */}
      <div className="hidden lg:flex h-full flex-col">
        {/* Top toolbar */}
        <div className="relative z-20 flex items-center justify-between px-6 py-4">
          {/* Left: Close and counter */}
          <div className="flex items-center gap-4">
            <button
              onClick={onClose}
              className="p-2 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors"
              title="Close (Esc)"
            >
              <X className="h-5 w-5" />
            </button>
            <span className="text-sm text-white/60 font-medium">
              {currentIndex + 1} of {images.length}
            </span>
          </div>

          {/* Right: Actions */}
          <TooltipProvider>
            <div className="flex items-center gap-2">
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => setShowInfo(prev => !prev)}
                    className={cn(
                      "p-2 rounded-lg transition-colors",
                      showInfo
                        ? "bg-white/20 text-white"
                        : "bg-white/10 hover:bg-white/20 text-white/80 hover:text-white"
                    )}
                  >
                    <Info className="h-5 w-5" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  <p>Toggle info <kbd className="ml-1 px-1 py-0.5 rounded bg-muted text-[10px]">I</kbd></p>
                </TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={handleDownload}
                    className="p-2 rounded-lg bg-white/10 hover:bg-white/20 text-white/80 hover:text-white transition-colors"
                  >
                    <Download className="h-5 w-5" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  <p>Download image</p>
                </TooltipContent>
              </Tooltip>

              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={handleViewConversation}
                    className="p-2 rounded-lg bg-white/10 hover:bg-white/20 text-white/80 hover:text-white transition-colors"
                  >
                    <MessageSquare className="h-5 w-5" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  <p>View conversation</p>
                </TooltipContent>
              </Tooltip>

              {/* Share dropdown */}
              <div className="relative">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => setShowShareMenu(prev => !prev)}
                      className={cn(
                        "p-2 rounded-lg transition-colors",
                        showShareMenu
                          ? "bg-white/20 text-white"
                          : "bg-white/10 hover:bg-white/20 text-white/80 hover:text-white"
                      )}
                    >
                      <Share2 className="h-5 w-5" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="bottom">
                    <p>Share</p>
                  </TooltipContent>
                </Tooltip>

                <ShareMenu
                  assetId={image.id}
                  isOpen={showShareMenu}
                  onClose={() => setShowShareMenu(false)}
                />
              </div>

              {onDelete && (
                <>
                  <div className="w-px h-6 bg-white/20 mx-1" />
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <button
                        onClick={() => setShowDeleteConfirm(true)}
                        className="p-2 rounded-lg bg-white/10 hover:bg-red-500/80 text-white/80 hover:text-white transition-colors"
                      >
                        <Trash2 className="h-5 w-5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="bottom">
                      <p>Delete image</p>
                    </TooltipContent>
                  </Tooltip>
                </>
              )}
            </div>
          </TooltipProvider>
        </div>

        {/* Main content area - clicking empty space closes */}
        <div
          className="flex-1 flex items-center justify-center relative min-h-0 px-20 cursor-pointer"
          onClick={onClose}
        >
          {/* Navigation arrows */}
          {hasPrev && (
            <button
              onClick={(e) => { e.stopPropagation(); onNavigate(currentIndex - 1) }}
              className="absolute left-6 top-1/2 -translate-y-1/2 z-10 p-3 rounded-full bg-white/10 hover:bg-white/20 text-white transition-all hover:scale-105"
              title="Previous (←)"
            >
              <ChevronLeft className="h-6 w-6" />
            </button>
          )}
          {hasNext && (
            <button
              onClick={(e) => { e.stopPropagation(); onNavigate(currentIndex + 1) }}
              className="absolute right-6 top-1/2 -translate-y-1/2 z-10 p-3 rounded-full bg-white/10 hover:bg-white/20 text-white transition-all hover:scale-105"
              title="Next (→)"
            >
              <ChevronRight className="h-6 w-6" />
            </button>
          )}

          {/* Image container - stop propagation to prevent close */}
          <div className="relative max-w-full max-h-full cursor-default" onClick={(e) => e.stopPropagation()}>
            <AssetImage
              key={image.id}
              assetId={image.id}
              alt={image.generation_prompt || image.filename}
              className="max-w-full max-h-[calc(100vh-160px)] object-contain rounded-lg shadow-2xl"
            />

            {/* Info panel overlay - slides up from bottom of image */}
            <div
              className={cn(
                "absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/90 via-black/70 to-transparent",
                "rounded-b-lg overflow-hidden transition-all duration-300 ease-out",
                showInfo ? "opacity-100 max-h-[300px] p-6 pt-12" : "opacity-0 max-h-0 p-0"
              )}
            >
              {/* Name/prompt */}
              {image.generation_prompt && (
                <p className="text-white/90 text-sm leading-relaxed mb-4 line-clamp-3">
                  {image.generation_prompt}
                </p>
              )}

              {/* Metadata row */}
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
                <div className="flex items-center gap-2">
                  <span className="text-white/50">Model</span>
                  <span className="text-white/90">{image.generation_model_display_name || formatModelId(image.generation_model)}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-white/50">Resolution</span>
                  <span className="text-white/90">
                    {resolution}
                    {dimensions && <span className="text-white/50 ml-1">({dimensions})</span>}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-white/50">Size</span>
                  <span className="text-white/90">{formatFileSize(image.size_bytes)}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-white/50">Created</span>
                  <span className="text-white/90">{formatDate(image.created_at)}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Keyboard hints */}
        <div className="relative z-10 flex items-center justify-center gap-6 py-4 text-xs text-white/30">
          <span>← → Navigate</span>
          <span>I Toggle info</span>
          <span>Esc Close</span>
        </div>
      </div>

      {/* Delete confirmation dialog */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setShowDeleteConfirm(false)}
          />
          <div className="relative bg-background rounded-2xl shadow-2xl border border-border/50 max-w-sm w-full p-6 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex flex-col items-center text-center">
              <div className="w-12 h-12 rounded-full bg-red-500/10 flex items-center justify-center mb-4">
                <Trash2 className="h-6 w-6 text-red-500" />
              </div>
              <h3 className="text-lg font-semibold text-foreground mb-2">
                Delete Image
              </h3>
              <p className="text-sm text-muted-foreground mb-6">
                Are you sure you want to delete this image? This action cannot be undone.
              </p>
              <div className="flex gap-3 w-full">
                <Button
                  variant="outline"
                  onClick={() => setShowDeleteConfirm(false)}
                  disabled={isDeleting}
                  className="flex-1"
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleDelete}
                  disabled={isDeleting}
                  className="flex-1 bg-red-500 hover:bg-red-600 text-white"
                >
                  {isDeleting ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Deleting...
                    </>
                  ) : (
                    'Delete'
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Share menu (mobile bottom sheet style) */}
      <MobileShareSheet
        assetId={image.id}
        isOpen={showShareMenu}
        onClose={() => setShowShareMenu(false)}
      />
    </div>
  )
}

export default ImageDetailModal
