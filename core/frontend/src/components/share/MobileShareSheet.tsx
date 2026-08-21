/**
 * MobileShareSheet Component
 *
 * Mobile bottom sheet for creating and managing share links.
 * Creates a public share link via API and provides social sharing options.
 */

import { useState, useCallback, useEffect } from 'react'
import { Link, Check, Loader2, Copy, Clock, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { assetsAPI, type ShareLink } from '@/api/assets'
import { useSettingsStore } from '@/store/settingsStore'
import { cn } from '@/lib/utils'
import {
  SHARE_PLATFORMS,
  openSharePopup,
  triggerNativeShare,
  isNativeShareSupported,
  PlatformBadge,
} from '@/lib/sharing'

interface MobileShareSheetProps {
  assetId: string
  isOpen: boolean
  onClose: () => void
}

export function MobileShareSheet({ assetId, isOpen, onClose }: MobileShareSheetProps) {
  const [isLoading, setIsLoading] = useState(false)
  const [shareLink, setShareLink] = useState<ShareLink | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [linkCopied, setLinkCopied] = useState(false)

  // Get watermark settings from global settings
  const watermark = useSettingsStore((state) => state.watermark)

  // Create share link when sheet opens
  useEffect(() => {
    if (isOpen && !shareLink && !isLoading) {
      createShareLink()
    }
  }, [isOpen])

  // Reset state when closed
  useEffect(() => {
    if (!isOpen) {
      // Keep shareLink to avoid re-creating on re-open
      setLinkCopied(false)
      setError(null)
    }
  }, [isOpen])

  const createShareLink = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const link = await assetsAPI.createShareLink(assetId, {
        watermark_enabled: watermark.enabled,
        watermark_position: watermark.position,
      })
      setShareLink(link)
    } catch (err: any) {
      setError(err.message || 'Failed to create share link')
    } finally {
      setIsLoading(false)
    }
  }

  const handleCopyLink = useCallback(async () => {
    if (!shareLink) return
    try {
      await navigator.clipboard.writeText(shareLink.share_url)
      setLinkCopied(true)
      setTimeout(() => setLinkCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }, [shareLink])

  const handlePlatformShare = useCallback((platformId: string) => {
    if (!shareLink) return
    const platform = SHARE_PLATFORMS.find(p => p.id === platformId)
    if (platform) {
      openSharePopup(platform, shareLink.share_url)
      onClose()
    }
  }, [shareLink, onClose])

  const handleNativeShare = useCallback(async () => {
    if (!shareLink) return
    const success = await triggerNativeShare(shareLink.share_url)
    if (success) {
      onClose()
    }
  }, [shareLink, onClose])

  const handleRevokeLink = useCallback(async () => {
    if (!shareLink) return
    try {
      const success = await assetsAPI.revokeShareLink(shareLink.token)
      if (success) {
        setShareLink(null)
        onClose()
      }
    } catch (err) {
      console.error('Failed to revoke link:', err)
    }
  }, [shareLink, onClose])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-[60] lg:hidden">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Sheet */}
      <div className="absolute bottom-0 left-0 right-0 bg-background rounded-t-2xl shadow-2xl border-t border-border/50 animate-in slide-in-from-bottom duration-200">
        {/* Handle */}
        <div className="w-12 h-1 bg-muted rounded-full mx-auto mt-3" />

        {/* Title */}
        <h3 className="text-lg font-semibold text-foreground text-center py-3">Share</h3>

        {/* Loading state */}
        {isLoading && (
          <div className="px-4 pb-8 safe-area-bottom flex flex-col items-center justify-center py-8">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground mb-3" />
            <p className="text-sm text-muted-foreground">Creating share link...</p>
          </div>
        )}

        {/* Error state */}
        {error && !isLoading && (
          <div className="px-4 pb-8 safe-area-bottom">
            <div className="flex items-center gap-2 text-red-500 mb-3 justify-center">
              <XCircle className="h-5 w-5" />
              <span className="text-sm font-medium">Error</span>
            </div>
            <p className="text-sm text-muted-foreground text-center mb-4">{error}</p>
            <Button onClick={createShareLink} className="w-full">
              Try again
            </Button>
          </div>
        )}

        {/* Share link created */}
        {shareLink && !isLoading && !error && (
          <>
            {/* Link display */}
            <div className="px-4 pb-4">
              <div className="flex items-center gap-2 mb-2 justify-center">
                <Link className="h-4 w-4 text-green-500" />
                <span className="text-sm font-medium text-foreground">Share Link Created</span>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={shareLink.share_url}
                  readOnly
                  className="flex-1 px-3 py-2.5 text-sm bg-muted rounded-lg border-0 focus:ring-1 focus:ring-primary"
                  onClick={(e) => e.currentTarget.select()}
                />
                <Button
                  onClick={handleCopyLink}
                  variant={linkCopied ? "default" : "outline"}
                  size="icon"
                  className={cn(
                    "h-10 w-10 shrink-0",
                    linkCopied && "bg-green-500 hover:bg-green-600 text-white"
                  )}
                >
                  {linkCopied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
              </div>
              {linkCopied && (
                <p className="text-xs text-green-500 mt-2 text-center">Link copied to clipboard!</p>
              )}
            </div>

            {/* Social share grid */}
            <div className="px-4 pb-4">
              <div className="grid grid-cols-4 gap-3">
                {SHARE_PLATFORMS.map((platform) => (
                  <button
                    key={platform.id}
                    onClick={() => handlePlatformShare(platform.id)}
                    className="flex flex-col items-center gap-2 p-3 rounded-xl hover:bg-muted/50 active:bg-muted transition-colors"
                  >
                    <PlatformBadge platform={platform} size="lg" />
                    <span className="text-xs text-muted-foreground">{platform.displayName}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Native share (if supported) */}
            {isNativeShareSupported() && (
              <div className="px-4 pb-4">
                <Button
                  onClick={handleNativeShare}
                  variant="outline"
                  className="w-full h-12"
                >
                  More sharing options...
                </Button>
              </div>
            )}

            {/* Link info and revoke */}
            <div className="px-4 pb-6 safe-area-bottom border-t border-border/50 pt-3 bg-muted/30">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {shareLink.expires_at ? `Expires ${new Date(shareLink.expires_at).toLocaleDateString()}` : 'No expiration'}
                </span>
                <button
                  onClick={handleRevokeLink}
                  className="text-red-400 hover:text-red-500 transition-colors"
                >
                  Revoke link
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default MobileShareSheet
